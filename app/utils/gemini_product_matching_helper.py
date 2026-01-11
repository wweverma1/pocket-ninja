import os
import json
import textwrap
from typing import Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from datetime import datetime


# --- Product Category Enum (reuse your existing one) ---

class ProductCategory(str, Enum):
    BEVERAGES = "beverages"
    ALCOHOL = "alcohol"
    SNACKS = "snacks"
    FRESH_PRODUCE = "fresh produce"
    DAIRY = "dairy"
    MEAT_SEAFOOD = "meat seafood"
    FROZEN_FOODS = "frozen foods"
    BAKERY = "bakery"
    HOUSEHOLD_GOODS = "household goods"
    TOBACCO = "tobacco"
    PREPARED_FOODS = "prepared foods"
    CONDIMENTS = "condiments"
    GRAINS_STAPLES = "grains staples"
    HEALTH_BEAUTY = "health beauty"
    OTHER = "other"


# --- Pydantic Models for Matching ---

class ExistingProduct(BaseModel):
    """Product already in database"""
    index: int = Field(description="Database product index (1, 2, 3, ...)")
    name: str = Field(description="Japanese product name")
    english_name: str = Field(description="English translation/romanization")
    category: ProductCategory = Field(description="Product category")
    avg_price: float = Field(description="Average price from historical data")
    aliases: list[str] = Field(default=[], description="Known alternative names for this product")


class ReceiptProduct(BaseModel):
    """Product extracted from receipt"""
    name: str = Field(description="Japanese product name from receipt")
    english_name: str = Field(description="English translation/romanization")
    category: ProductCategory = Field(description="Product category")
    price: float = Field(description="Price from this receipt")


class EnrichmentAction(str, Enum):
    """Type of enrichment to apply to existing product"""
    NO_CHANGE = "no_change"
    UPDATE_NAME = "update_name"
    ADD_ALIAS = "add_alias"
    MERGE_INFORMATION = "merge_information"


class MatchDecision(BaseModel):
    """Decision for a single receipt product"""
    is_match: bool = Field(description="True if matches existing product, False if new product")

    matched_product_index: Optional[int] = Field(
        description="Database product index (1, 2, 3, ...). Null if is_match=False"
    )

    enrichment_action: EnrichmentAction = Field(
        description="How to enrich existing product data based on this match"
    )

    canonical_name_ja: str = Field(
        description="Best Japanese name. For matches: choose more complete/specific name. For new: standardized receipt name"
    )

    canonical_name_en: str = Field(
        description="Best English name. For matches: choose more complete/specific name. For new: standardized receipt name"
    )


class ProductMatchingResult(BaseModel):
    """Complete matching results for all receipt products"""
    matches: list[MatchDecision] = Field(description="Match decision for each receipt product in order")


def get_matching_instruction():
    """
    Optimized prompt for faster LLM response while maintaining accuracy.
    Removes verbose output requirements to reduce token generation.
    """

    matching_instruction = textwrap.dedent("""
        You are a Product Matching Expert for Japanese grocery retail. Match receipt products to database products and identify enrichment opportunities.

        ## Matching Rules

        ### 1. Semantic Equivalence (Priority Order)
        **A. Brand/Manufacturer** (最重要)
        - Match regardless of script: "コカコーラ" = "Coca Cola" = "ｺｶｺｰﾗ"
        - Common: サントリー/Suntory, キリン/Kirin, アサヒ/Asahi, 明治/Meiji

        **B. Core Product Type**
        - Fundamental product: ペットボトル茶, 牛乳, パン
        - Minor descriptor differences ignored if core matches

        **C. Variant/Flavor**
        - Must match: 緑茶 ≠ 烏龍茶, プレーン ≠ イチゴ

        **D. Size/Volume/Weight**
        - Must match: 500ml ≠ 2L, 100g ≠ 200g
        - Tolerate OCR: 500ml ≈ 500ｍｌ ≈ 500ML

        **E. Quantity per Package**
        - "6個入り" ≠ single item

        ### 2. Price Validation
        - Within ±30% of avg_price → supports match
        - >2x or <0.5x → review carefully (different size likely)
        - Fresh/seasonal items: wider variance acceptable

        ### 3. Category
        - Must match or be compatible

        ### 4. Decision Logic
        **MATCH (is_match=true)** when:
        - Brand + Type + Variant + Size semantically equivalent
        - Price reasonable vs avg_price
        - Category matches
        - Effective confidence ≥0.6

        **NEW (is_match=false)** when:
        - Critical attribute differs
        - No existing product shares brand + type
        - Price + attributes conflicting

        ### 5. Enrichment Actions

        **UPDATE_NAME** when:
        - Receipt has size but DB doesn't: "コカコーラ" → "コカコーラ 1.5L"
        - Receipt has variant: "明治牛乳" → "明治おいしい牛乳 1L"
        - Receipt fixes truncation or adds brand detail
        - Receipt cleaner: "ｺｶｺｰﾗ500" → "コカコーラ 500ml"

        **ADD_ALIAS** when:
        - Both complete, different conventions
        - Store-specific abbreviation
        - Valid alternative name

        **MERGE_INFORMATION** when:
        - DB has good English, receipt has better Japanese
        - Receipt has size, DB has better brand format
        - Combine best of both

        **NO_CHANGE** when:
        - DB already more complete
        - Receipt truncated/has OCR errors
        - DB follows best practices

        ### 6. Canonical Name Format
        Prefer: [Brand] [Product Type] [Variant] [Size]
        - Good: "サントリー 天然水 550ml"
        - Bad: "天然水" (vague), "ｻﾝﾄﾘｰ500" (truncated)

        For new products: standardize by converting half-width to full-width, fixing OCR errors, expanding truncations.

        ## Special Cases
        - Generic products (卵, 牛乳, 食パン): match if type + size similar
        - Seasonal (限定, 季節): treat as new unless exact repeat
        - Bundles (3個セット): different from single
        - Fresh/prepared: focus on type + unit size

        ## Output
        Return one MatchDecision per receipt product in order. Choose enrichment_action to improve database quality. Be conservative: when uncertain, create new product.
    """)

    return matching_instruction


def match_products_with_gemini(
    existing_products: list[dict],
    receipt_products: list[dict]
) -> Optional[dict]:
    """
    Matches receipt products against existing database products using Gemini.
    Optimized for speed by reducing output verbosity.

    Args:
        existing_products: List of dicts with keys: index, name, english_name, category, avg_price, aliases (optional)
        receipt_products: List of dicts with keys: name, english_name, category, price
        temperature: Controls consistency (0.1-0.3 recommended). Lower = more consistent.

    Returns:
        Parsed JSON matching ProductMatchingResult schema, or None on error

    Example usage:
        existing = [
            {
                "index": 1,
                "name": "コカコーラ",
                "english_name": "Coca Cola",
                "category": "beverages",
                "avg_price": 138.5,
                "aliases": []
            }
        ]

        receipt = [
            {
                "name": "コカコーラ 500ml",
                "english_name": "Coca Cola 500ml", 
                "category": "beverages",
                "price": 140.0
            }
        ]

        result = deduplicate_products_with_gemini(existing, receipt)

        # result['matches'][0]['is_match'] = True
        # result['matches'][0]['matched_product_index'] = 1
        # result['matches'][0]['enrichment_action'] = "update_name"
        # result['matches'][0]['canonical_name_ja'] = "コカコーラ 500ml"
    """

    api_key = os.getenv("GEMINI_PRODUCT_MATCHING_API_KEY")
    if not api_key:
        print("Error: GEMINI_PRODUCT_MATCHING_API_KEY is not set.")
        return None

    instruction = get_matching_instruction()

    # Prepare compact context
    context_str = f"""## Database Products
        {json.dumps(existing_products, ensure_ascii=False)}

        ## Receipt Products
        {json.dumps(receipt_products, ensure_ascii=False)}

        Match each receipt product (in order) to database products. Return MatchDecision for each.
    """

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                instruction,
                context_str
            ],
            config={
                "response_mime_type": "application/json",
                "response_schema": ProductMatchingResult,
                "temperature": 0.1,
            }
        )

        return json.loads(response.text)

    except Exception as e:
        print(f"Gemini Product Matching Error: {e}")
        return None
