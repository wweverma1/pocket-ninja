import os
import time
import json
import textwrap
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


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


class StoreIdentifier(BaseModel):
    ja: str = Field(description="Japanese branch name only, excluding store brand (e.g., '北8条店', '札幌駅前店')")
    en: str = Field(description="English romanization of branch location only (e.g., 'Kita 8-jo', 'Sapporo Ekimae')")


class Product(BaseModel):
    name: str = Field(description="Japanese product name from receipt. Clean OCR errors and expand truncations.")
    english_name: str = Field(description="English translation or romanization of extracted name")
    category: ProductCategory = Field(description="Product category from predefined list")
    price: float = Field(description="Unit price (tax-included). If multiple quantity, divide by quantity.")


class ReceiptAnalysis(BaseModel):
    error_code: int = Field(
        description="0: Success. 1: Not a Receipt. 2: Edited/Tampered. 3: Date Out of Range. 4: Unsupported Store Type. 5: Outside Target City.")

    purchase_date: Optional[str] = Field(description="Purchase date in YYYY-MM-DD format. Null if not found.")

    store_name: Optional[str] = Field(
        description="Store brand name in English (e.g., 'Lawson', '7-Eleven', 'FamilyMart', 'AEON'). Null if error.")
    store_identifier: Optional[StoreIdentifier] = Field(
        description="Specific branch location details (excluding store brand name). Null if error.")

    total_amount: Optional[float] = Field(description="Final total amount paid including tax. Null if error.")
    products: list[Product] = Field(description="List of extracted products. Empty list if error.")


def get_receipt_analysis_instruction(target_city: str, valid_start_date: str, valid_end_date: str, available_stores: list[str]):
    stores_list_str = ", ".join(available_stores)

    receipt_analysis_instruction = textwrap.dedent(f"""
        Extract structured data from Japanese receipt images.

        ## Validation Context
        - **Target City**: {target_city}
        - **Valid Date Range**: {valid_start_date} to {valid_end_date}
        - **Supported Stores**: Convenience stores (konbini), supermarkets and drugstores ONLY
        - **Known Brands**: {stores_list_str}

        ## Task: Validate and Extract

        ### Step 1: Validation (Assign error_code)
        - **0** = Valid receipt → proceed to extraction
        - **1** = Not a receipt (invoice, ticket, menu, blank/unreadable)
        - **2** = Shows digital editing or tampering
        - **3** = Date outside valid range
        - **4** = Unsupported store type (clothing, electronics, restaurants, cafes, etc.)
        - **5** = Location outside {target_city}

        **If error_code ≠ 0**: Stop. Return null values and empty products list.

        ### Step 2: Extract Data (Only if error_code = 0)

        **A. Purchase Date**
        - Format: YYYY-MM-DD
        - Common formats: "YYYY年MM月DD日", "YY/MM/DD", "YYYY.MM.DD"

        **B. Store Identification**
        - **store_name**: English brand name (e.g., "Lawson", "7-Eleven", "AEON")
        - **store_identifier**: Branch location only
          - **ja**: Japanese branch name (e.g., "北8条店")
          - **en**: Romanized English (e.g., "Kita 8-jo")

        **C. Total Amount**
        - Extract final total (税込/合計), not subtotal (小計)

        **D. Products**
        For each product:
        - **name**: Japanese product name from receipt. Clean OCR errors, expand truncations (e.g., "コカコー..." → "コカコーラ"), and remove non-product text such as:
            - Promotional labels: セール (sale), お買得 (bargain), 特 (special)
            Keep only the core product name with brand and essential descriptors (e.g., size, flavor)
        - **english_name**: English translation/romanization of the extracted name
        - **category**: Classify into: beverages, alcohol, snacks, fresh produce, dairy, meat seafood, frozen foods, bakery, household goods, tobacco, prepared foods, condiments, grains staples, health beauty, other
        - **price**: Unit price (tax-included). If multiple quantity shown (×2, 2個), divide total by quantity

        **Rules**:
        - Extract only purchasable products (ignore tax lines, discounts, payment methods)
        - Maintain receipt order
    """)
    return receipt_analysis_instruction


def analyze_receipt_with_gemini(image_bytes: bytes, target_city: str, valid_start_date: str, valid_end_date: str, available_stores: list[str]):
    api_key = os.getenv("GEMINI_RECEIPT_ANALYSIS_API_KEY")
    if not api_key:
        print("Error: GEMINI_RECEIPT_ANALYSIS_API_KEY is not set.")
        return None

    instruction = get_receipt_analysis_instruction(target_city, valid_start_date, valid_end_date, available_stores)

    try:
        start_time = time.time()

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
                "temperature": 0.1,
            }
        )

        elapsed_time = time.time() - start_time
        print(f"Gemini Receipt Analysis completed in {elapsed_time:.2f} seconds")

        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini Receipt Analysis Error: {e}")
        return None
