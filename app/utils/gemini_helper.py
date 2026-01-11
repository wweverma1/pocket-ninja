import os
import json
import textwrap
from typing import Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


# --- Pydantic Models ---

class StoreIdentifier(BaseModel):
    ja: str = Field(description="Japanese location/branch name only, excluding store brand (e.g., '北8条店', '札幌駅前店')")
    en: str = Field(description="English romanization of branch location only (e.g., 'Kita 8-jo', 'Sapporo Ekimae')")


class Product(BaseModel):
    name: str = Field(description="Product name in Japanese as shown on receipt. Clean OCR errors and expand obvious truncations (e.g., 'コカコー...' → 'コカコーラ'). Remove noise characters.")
    english_name: str = Field(description="English translation or romanization of the product name.")
    price: float = Field(description="Price per single unit (tax-included). If multiple quantity shown, divide price by quantity to get unit price.")


class ReceiptAnalysis(BaseModel):
    error_code: int = Field(
        description="0: Success. 1: Not a Receipt. 2: Edited/Tampered. 3: Date Out of Range. 4: Unsupported Store Type. 5: Outside Target City.")
    
    purchase_date: Optional[str] = Field(description="Purchase date in YYYY-MM-DD format. Null if not found.")
    
    store_name: Optional[str] = Field(description="Store brand name in English (e.g., 'Lawson', 'Seven-Eleven', 'FamilyMart', 'AEON'). Null if error.")
    store_identifier: Optional[StoreIdentifier] = Field(description="Specific branch location details (excluding store brand name). Null if error.")
    
    total_amount: Optional[float] = Field(description="Final total amount paid including tax. Null if error.")
    products: list[Product] = Field(description="List of extracted products. Empty list if error.")


def get_receipt_analysis_instruction(target_city: str, valid_start_date: str, valid_end_date: str, available_stores: list[str]):
    """
    Generates optimized prompt for Gemini using SI → RI → QI structure.
    Based on Google's best practices for accuracy and consistency.
    """
    stores_list_str = ", ".join(available_stores)
    
    receipt_analysis_instruction = textwrap.dedent(f"""
        You are a receipt data extraction specialist for Japanese retail stores.
        
        ## Your Role
        
        Extract structured data from receipt images with high accuracy. Your primary task is to use your vision capabilities to read the receipt directly. Prioritize what you see in the image over any OCR artifacts.
        
        ## Validation Context
        
        - **Target City**: {target_city}
        - **Valid Date Range**: {valid_start_date} to {valid_end_date} (inclusive)
        - **Supported Store Types**: Convenience stores (konbini) and supermarkets ONLY
        - **Known Store Brands**: {stores_list_str}
        
        ## Task: Validate and Extract Receipt Data
        
        ### Step 1: Receipt Validation
        
        Examine the image carefully and assign the appropriate error_code:
        
        - **0** = Valid receipt from supported store type → proceed to extraction
        - **1** = Not a receipt (invoice, ticket, menu, document, blank/unreadable image)
        - **2** = Shows signs of digital editing, manipulation, or tampering
        - **3** = Purchase date falls outside {valid_start_date} to {valid_end_date}
        - **4** = Unsupported store type (clothing stores, electronics retailers, restaurants, cafes, bars, drug stores)
        - **5** = Store location is clearly outside {target_city}
        
        **Important**: If error_code is NOT 0, stop immediately. Return the response with null values for all other fields and an empty products list.
        
        ### Step 2: Data Extraction (Only if error_code = 0)
        
        #### A. Purchase Date
        - Extract the purchase date and convert to **YYYY-MM-DD** format
        - Common Japanese formats: "YYYY年MM月DD日", "YY/MM/DD", "YYYY.MM.DD"
        - Typically located near top or bottom of receipt
        
        #### B. Store Identification
        - **store_name**: Extract store brand name in **English** (e.g., "Lawson", "Seven-Eleven", "FamilyMart", "AEON", "MaxValu")
        - **store_identifier**: Extract branch location details ONLY (exclude store brand name)
          - **ja**: Branch location in Japanese (e.g., "北8条店", "駅前店", "札幌中央店")
          - **en**: Romanized English version (e.g., "Kita 8-jo", "Ekimae", "Sapporo Chuo")
        
        #### C. Total Amount
        - Extract the **final total amount paid** (税込 or 合計)
        - This is the amount after tax, usually at the bottom
        - Ignore subtotals (小計 or 商品合計)
        
        #### D. Product Extraction
        
        For each product line item:
        
        1. **Read product name**: Japanese receipts often truncate names (e.g., "コカコー..." for "コカコーラ")
           - Extract visible text and infer full name when truncation is obvious
           - Clean OCR errors and noise characters
           - Remove extra spaces or ellipsis ("...")
        
        2. **Handle quantities**: Watch for quantity indicators like "×2", "2個", "2本"
           - If multiple quantity is shown, extract the **unit price** (divide line total by quantity if needed)
           - Report price for single unit, not total for multiple units
        
        3. **Price extraction**: Use tax-included price (税込) if both prices shown
           - Price is typically right-aligned on receipt
        
        4. **Output format**:
           - **name**: Cleaned Japanese product name
           - **english_name**: English translation or romanization
           - **price**: Single unit price (tax-included)
        
        **Extraction Rules**:
        - Extract ONLY purchasable products (ignore tax lines, discounts, payment methods)
        - If same product appears multiple times, list each occurrence separately with unit price
        - Do not invent products that aren't clearly visible
        - Maintain the order products appear on the receipt
        
        ## Output Requirements
        
        Return valid JSON matching the provided schema exactly. Preserve all Japanese characters properly. Ensure all required fields are present with appropriate null values when error_code is not 0.
    """)
    return receipt_analysis_instruction


def analyze_receipt_with_gemini(image_bytes: bytes, target_city: str, valid_start_date: str, valid_end_date: str, available_stores: list[str]):
    """
    Analyzes receipt using Gemini 2.5 Flash with structured output.
    Returns parsed JSON matching ReceiptAnalysis schema.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        return None
    
    instruction = get_receipt_analysis_instruction(target_city, valid_start_date, valid_end_date, available_stores)

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
                "temperature": 0.1,  # Very low for maximum consistency and accuracy
            }
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini Analysis Error: {e}")
        return None
