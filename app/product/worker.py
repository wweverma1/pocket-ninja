import threading
import time
from datetime import datetime, timedelta, timezone
from flask import Flask
from app.models.collections.receipt import Receipt
from app.models.collections.product import Product
from app.utils.gemini_product_matching_helper import match_products_with_gemini

def product_sync_worker(app: Flask):
    print("Background Product Sync Worker Started.")
    
    # We must push the app context to access MongoDB via PyMongo
    with app.app_context():
        while True:
            try:
                # 1. Fetch the next unprocessed, successful receipt
                receipt = Receipt.get_unprocessed_receipt()
                
                if not receipt:
                    time.sleep(60)
                    continue
                
                print(f"Processing receipt {receipt['_id']} for product catalog...")
                
                # 2. Extract Data
                receipt_products = receipt.get('productsFound', [])
                if not receipt_products:
                    Receipt.mark_as_processed(receipt['_id'])
                    continue

                store_name = receipt.get('storeName')
                purchase_date = receipt.get('purchaseDate')
                
                jst_tz = timezone(timedelta(hours=9))
                
                # Ensure purchase_date is datetime
                if isinstance(purchase_date, str):
                    try:
                        purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d")
                    except:
                        purchase_date = datetime.now(jst_tz) - timedelta(days=3)
                elif not isinstance(purchase_date, datetime):
                    purchase_date = datetime.now(jst_tz) - timedelta(days=3)

                # 3. Get Existing Catalog Context
                # Fetch full catalog including _id to map back later
                full_catalog = Product.get_full_catalog()
                
                # ADDED: Enumerate catalog to provide the 'index' field required by the LLM helper
                # We create a lightweight list for the LLM to save tokens, but keep full_catalog for the ID mapping
                catalog_for_llm = []
                for idx, prod in enumerate(full_catalog):
                    prod['index'] = idx + 1 # 1-based index for LLM
                    catalog_for_llm.append({
                        "index": prod['index'],
                        "name": prod.get('name'),
                        "english_name": prod.get('english_name'),
                        "category": prod.get('category'),
                        "avg_price": prod.get('avg_price'),
                        "aliases": prod.get('aliases', [])
                    })

                # 4. Call Gemini for Deduplication
                # Note: Corrected function name to match your helper import
                result = match_products_with_gemini(catalog_for_llm, receipt_products)
                
                if not result or 'matches' not in result:
                    print(f"No valid decisions returned for receipt {receipt['_id']}. Skipping.")
                    Receipt.mark_as_processed(receipt['_id'])
                    continue

                decisions = result['matches']

                # 5. Apply Updates to Product Collection
                # We pass 'full_catalog' because it contains the real Mongo _ids corresponding to the indices
                Product.add_products(decisions, full_catalog, receipt_products, store_name, purchase_date)
                
                # 6. Mark Receipt as Processed
                Receipt.mark_as_processed(receipt['_id'])
                print(f"Successfully processed receipt {receipt['_id']}.")
                
            except Exception as e:
                print(f"Error in Product Sync Worker: {e}")
                time.sleep(60)

def start_product_sync_thread(app: Flask):
    thread = threading.Thread(target=product_sync_worker, args=(app,), daemon=True)
    thread.start()