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
        You are an receipt analysis expert for {target_city}, Japan.
        
        **Objective**: Extract structured data from the receipt image and help in deduplication of product catalog.
        
        **Context**:
        - Target City: {target_city}
        - Valid Date Range: {valid_start_date} to {valid_end_date} (inclusive).
        - Known Stores: {stores_list_str}
        - Catalog: {products_list_str} 
          (Catalog items contain 'min_match_price' and 'max_match_price' along with name to help with fuzzy matching).

        **Step 1: Validation (Set error_code)**
        - **Code 1 (Not Receipt)**: Image is not a receipt.
        - **Code 2 (Edited)**: Image shows digital manipulation, photoshop, or is edited.
        - **Code 3 (Date Invalid)**: Date on receipt is NOT within {valid_start_date} and {valid_end_date}.
        - **Code 4 (Unsupported Store)**: Receipt is NOT from a Convenience Store (Konbini), Supermarket, or Drug Store. (Reject Clothing, Electronics, Restaurants).
        - **Code 5 (Location)**: Store address is clearly outside {target_city}.
        - **Code 0 (Success)**: Valid receipt. Proceed to extraction.

        **Step 2: Extraction (If Code 0)**
        1. **Date**: Extract YYYY-MM-DD.
        2. **Store**: Identify Brand and Branch.
        3. **Products (Extraction & Matching Rules)**:
           For each item on the receipt, follow this logic tree:
           
           **A. Attempt Match against Catalog:**
             - **Criteria 1 (Name)**: Does the receipt text roughly match the Catalog Name (represent same real word product)?
             - **Criteria 2 (Price)**: Is the receipt price between 'min_match_price' and 'max_match_price' of that Catalog item?
             
             - **MATCH DECISION**:
               - If Name is EXACT MATCH -> **MATCH**.
               - If Name is SIMILAR (brand, product name, varient/ flavour are same but unsure about size/ capacity) + Price is IN RANGE -> **MATCH**.
               - If Name is SIMILAR + Price is OUT OF RANGE -> **NO MATCH** (Different size/ capacity).

           **B. Output Format:**
             - **CASE: MATCH FOUND**: 
               - Set 'name' = EXACT Catalog Name.
               - If the Catalog Name contains typos/issues and receipt is clear or you think name can be improved for future matching: Set 'updated_name' = Better Name.
             
             - **CASE: NO MATCH (New Product)**:
               - Set 'name' = Cleaned Name from Receipt (Fix typos, expand '...', e.g. 'Coca-Co' -> 'Coca-Cola', remove noise).
               - Set 'updated_name' = NULL.

        4. **Price**: Extract the maximum/tax-included price line for the item. Ignore any discounts.

        **Output**: JSON strictly matching the schema.
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
            }
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini Analysis Error: {e}")
        return None
