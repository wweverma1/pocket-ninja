import os
import json
import textwrap
from typing import Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


# --- Pydantic Models ---

class StoreIdentifier(BaseModel):
    ja: str = Field(description="Japanese name of the specific branch (e.g., 'サツドラ北8条店')")
    en: str = Field(description="English romanization of the branch (e.g., 'Satudora Kita 8-jo')")


class Product(BaseModel):
    name: str = Field(
        description="The product name. Rules: 1. If MATCHED with Catalog, use the EXACT Catalog Name. 2. If UNMATCHED, use the text from receipt but Clean/Correct it (fix typos, remove noise '...', etc.).")
    english_name: Optional[str] = Field(
        description="English translation. Required for unmatched products.")
    price: float = Field(description="Price of the product (Highest value/Tax included).")

    # DB Improvement (Only for Matched Products)
    updated_name: Optional[str] = Field(
        description="Only use if MATCHED. Proposed cleaner name for the Existing Catalog Item if the current Catalog Name is vague/wrong or can be improved. Null if Unmatched.")
    updated_english_name: Optional[str] = Field(description="English translation of updated_name.")


class ReceiptAnalysis(BaseModel):
    error_code: int = Field(
        description="0: Success. 1: Not a Receipt. 2: Edited/Tampered. 3: Date Out of Range. 4: Unsupported Store Type. 5: Outside Target City.")

    purchase_date: Optional[str] = Field(
        description="Purchase date in YYYY-MM-DD. Null if not found.")

    store_name: Optional[str] = Field(
        description="The canonical store brand name (e.g., 'Lawson').")
    store_identifier: Optional[StoreIdentifier] = Field(
        description="Specific branch details.")

    total_amount: Optional[float] = Field(description="The total amount paid.")
    products: list[Product] = Field(description="List of extracted products.")


def get_receipt_analysis_instruction(target_city, valid_start_date, valid_end_date, available_stores: list[str], product_catalog: list[dict]):
    stores_list_str = json.dumps(available_stores, ensure_ascii=False)
    products_list_str = json.dumps(product_catalog, ensure_ascii=False)

    receipt_analysis_instruction = textwrap.dedent(f"""
        You are a receipt data extraction specialist for Japanese retail stores in {target_city}.

        **Your Task**: Analyze this receipt image, validate it, extract structured data, and help in deduplication by matching products against an existing catalog.

        ## Context Information

        **Target City**: {target_city}
        **Valid Date Range**: {valid_start_date} to {valid_end_date} (inclusive)
        **Supported Store Types**: Convenience stores (konbini), supermarkets, drug stores ONLY
        **Known Store Brands**: {stores_list_str}
        **Product Catalog**: {products_list_str}

        Note: Each catalog item has 'name', 'min_match_price', and 'max_match_price' for fuzzy matching.

        ## Step 1: Receipt Validation

        Examine the image and set the appropriate error_code:

        - **error_code: 0** = Valid receipt, proceed to extraction
        - **error_code: 1** = Not a receipt (e.g., invoice, ticket, document, blank image)
        - **error_code: 2** = Receipt shows signs of digital editing, manipulation, or photoshopping
        - **error_code: 3** = Purchase date is outside the valid range ({valid_start_date} to {valid_end_date})
        - **error_code: 4** = Receipt is from an unsupported store type (reject: clothing stores, electronics retailers, restaurants, cafes, bars)
        - **error_code: 5** = Store address clearly indicates location outside {target_city}

        If error_code is NOT 0, stop here and return the response with null values for other fields.

        ## Step 2: Data Extraction (Only if error_code = 0)

        ### A. Date Extraction
        - Extract purchase date in YYYY-MM-DD format
        - Common Japanese date formats: "YYYY年MM月DD日", "YY/MM/DD", "YYYY.MM.DD"
        - Receipt dates are typically near the top or bottom of the receipt

        ### B. Store Identification
        - **store_name**: Extract the store brand name (e.g., "ローソン", "セブンイレブン", "AEON")
        - **store_identifier**: 
          - ja: Full branch name in Japanese (e.g., "セブンイレブン札幌北8条店")
          - en: Romanized English version (e.g., "Seven-Eleven Sapporo Kita 8-jo")
        - Store name typically appears at the top of the receipt

        ### C. Total Amount
        - Extract the final total amount paid (generally 税込 or 合計金額)
        - This is usually at the bottom of the receipt
        - Ignore subtotals (generally 商品合計) and focus on the final total after tax

        ### D. Product Extraction and Matching

        For each product line item on the receipt, follow this process:

        **Step D1: Read Receipt Text**
        - Japanese receipts often truncate product names (e.g., "コカコー..." for "コカコーラ")
        - Extract the visible text but infer the full product name when truncation is obvious
        - Watch for quantity indicators: "×2", "2個", "2本" (may appear after the product name)
        - Price is typically right-aligned on the receipt

        **Step D2: Match Against Catalog**

        For each product, attempt to find a match in the provided catalog to help in deduplication:

        **Matching Criteria:**
        1. **Name Similarity**: Does the receipt text represent the same real-world product as the catalog entry?
           - Consider: Same brand + same product line + same variant/flavor
           - Ignore minor OCR errors, truncation, spacing differences
           - Account for size/capacity variations (e.g., "500ml" vs "1L" = different products)

        2. **Price Range Check**: Is the receipt price within [min_match_price, max_match_price] of the catalog item?

        **Matching Decision Logic:**
        - **EXACT NAME MATCH** → MATCH (use catalog name)
        - **SIMILAR NAME + PRICE IN RANGE** → MATCH (use catalog name)
        - **SIMILAR NAME + PRICE OUT OF RANGE** → NO MATCH (likely different size/quantity)
        - **DIFFERENT NAME** → NO MATCH (new product)

        **Step D3: Output Format**

        **If MATCH found:**
        - name: Use the EXACT catalog name (copy it precisely)
        - english_name: null (catalog already has this)
        - price: The price from the receipt
        - updated_name: Only set this if the catalog name has obvious issues (typos, unclear naming, missing brand info) AND the receipt shows a clearer version. Otherwise null.
        - updated_english_name: English version of updated_name if applicable, otherwise null

        **If NO MATCH (new product):**
        - name: Cleaned Japanese name from receipt
          - Fix OCR errors (e.g., "コカコー..." → "コカコーラ")
          - Remove noise characters, extra spaces
          - Expand obvious truncations
          - Keep brand name if visible (e.g., "森永製菓 ハイチュウ グレープ")
        - english_name: Provide English translation/romanization
        - price: The price from the receipt  
        - updated_name: null
        - updated_english_name: null

        ### Important Notes for Product Extraction:
        - Extract ONLY purchasable products (ignore tax lines, discount lines, payment method lines)
        - Use the tax-included price if both tax-included and tax-excluded prices are shown
        - If the same product appears multiple times, list it once with the single unit price
        - Do not invent products that aren't clearly visible on the receipt

        ## Output Format

        Return valid JSON matching the provided schema exactly. All string values must preserve Japanese characters properly.
    """)
    return receipt_analysis_instruction


def analyze_receipt_with_gemini(image_bytes: bytes, instruction: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        return None

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type='image/webp',
                ),
                instruction
            ],
            config={
                "response_mime_type": "application/json",
                "response_schema": ReceiptAnalysis,
                "temperature": 0.2,  # Lower temperature for more deterministic output
            }
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini Analysis Error: {e}")
        return None