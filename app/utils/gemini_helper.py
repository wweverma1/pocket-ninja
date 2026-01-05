import os
import json
import textwrap
from typing import Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


# --- Pydantic Models for Structured Output ---

class StoreIdentifier(BaseModel):
    ja: str = Field(description="Japanese name of the specific branch/location (e.g., 'サツドラ北8条店')")
    en: str = Field(description="English romanization of the branch/location (e.g., 'Satudora Kita 8-jo')")


class Product(BaseModel):
    name: str = Field(description="The product name. If matched with the provided list, use the EXACT list name. If new, use the name on receipt.")
    english_name: Optional[str] = Field(description="English translation. Optional if the product is matched with the provided list.")
    price: float = Field(description="Price of the product excluding discounts.")
    
    # New fields for database improvement
    updated_name: Optional[str] = Field(description="Proposed better/cleaner name for the product if the existing list name is vague or contains typos.")
    updated_english_name: Optional[str] = Field(description="English translation of the proposed updated_name.")


class ReceiptAnalysis(BaseModel):
    error_code: int = Field(
        description="0 for success. 1: Invalid Image. 2: Edited/Tampered. 3: Date Invalid (>3 days old/future). 4: Date Missing. 5: Location Invalid. 6: Location Missing. 7: Store Name Missing.")
    
    purchase_date: str = Field(description="The purchase date found on the receipt in YYYY-MM-DD format.")
    
    store_name: Optional[str] = Field(description="The canonical store brand name (e.g., 'Lawson'). Null if error_code != 0.")
    store_identifier: Optional[StoreIdentifier] = Field(description="Specific branch/store location details. Optional.")
    
    total_amount: Optional[float] = Field(description="The total amount paid. 0.0 if error_code != 0.")
    products: list[Product] = Field(description="List of extracted and matched products. Empty if error_code != 0.")


def get_receipt_analysis_instruction(date_str, target_city, available_stores: list[str], product_names: list[str]):
    stores_list_str = json.dumps(available_stores, ensure_ascii=False)
    # Join the first 500 products to avoid hitting context limits if list is huge, 
    # or pass all if feasible. Assuming standard receipt context window handles ~10k tokens easily.
    products_list_str = json.dumps(product_names, ensure_ascii=False)

    receipt_analysis_instruction = textwrap.dedent(f"""
        Instructions:
        You are an expert receipt analysis AI for Sapporo, Japan. Analyze the receipt image and extract data into JSON.
        
        Context Data:
        - Reference Date: {date_str}
        - Target City: {target_city}
        - Known Stores: {stores_list_str}
        - Known Products Catalog: {products_list_str}

        Validation Steps (Set 'error_code'):
        1. **Image Check**: Must be a real, unedited photo of a receipt from a Convenience Store, Supermarket, or Drug Store. (Else 1 or 2).
        2. **Date Check**: Extract date of purchase from the receipt (usually YYYY-MM-DD). Must be within 3 days before inclusive of {date_str}. (e.g., if Ref is 2026-01-01, valid range is 2025-12-29 to 2026-01-01). If old/future: code 3. If unreadable: code 4.
        3. **Location Check**: Store must be in {target_city}. If clearly outside: code 5. If unreadable: code 6.
        4. **Store Name**: Identify brand (e.g., "Seicomart", "FamilyMart"). If missing: code 7.

        Extraction Logic (Only if error_code == 0):
        1. **Store Identifier**: Extract the specific branch name, not complete but atleast with 1 important identifier (e.g., "Kita 34-jo branch") in 'ja' and 'en'.
        2. **Product Matching (Crucial)**: 
           - Compare each item on the receipt against the 'Known Products Catalog'. Check if both represent same real-world product. Check for brand, product, varient/ flavour, size (if available)
           - **If Match Found**: Use the EXACT name from the catalog as 'name'. You may omit 'english_name'.
             - *Improvement*: If the catalog name has typos or is vague, and the receipt is clearer, or can be improved for future matchings, provide the better name in 'updated_name' (and its translation in 'updated_english_name').
           - **If No Match**: Extract the text exactly as 'name' and provide a translation in 'english_name'.
        3. **Prices**: Extract price excluding tax.

        Output: Return strict JSON matching the ReceiptAnalysis schema.
    """)
    return receipt_analysis_instruction


def analyze_receipt_with_gemini(image_bytes: bytes, instruction: str):
    """
    Sends the image and instruction to Gemini via the Google Gen AI SDK.
    Enforces structured output using Pydantic.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        return None

    try:
        # Initialize Client
        client = genai.Client(api_key=api_key)

        # Call Gemini 2.5 Flash
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