import threading
import time
from datetime import datetime, timedelta, timezone
from flask import Flask
from app.models.collections.receipt import Receipt
from app.models.collections.product import Product
from app.utils.gemini_product_matching_helper import match_products_with_gemini


def product_sync_worker(app: Flask):
    print("Background Product Sync Worker Started.")

    with app.app_context():
        while True:
            try:
                receipt = Receipt.get_unprocessed_receipt()

                if not receipt:
                    time.sleep(60)
                    continue

                print(f"Processing receipt {receipt['_id']} for product catalog...")

                receipt_products = receipt.get('productsFound', [])
                if not receipt_products:
                    Receipt.mark_as_processed(receipt['_id'])
                    continue

                store_name = receipt.get('storeName')
                purchase_date = receipt.get('purchaseDate')

                jst_tz = timezone(timedelta(hours=9))

                if isinstance(purchase_date, str):
                    try:
                        purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d")
                    except:
                        purchase_date = datetime.now(jst_tz) - timedelta(days=3)
                elif not isinstance(purchase_date, datetime):
                    purchase_date = datetime.now(jst_tz) - timedelta(days=3)

                full_catalog = Product.get_full_catalog()

                existing_products = []
                catalog_index_id_map = {}
                for idx, prod in enumerate(full_catalog):
                    prod_index = idx + 1

                    catalog_index_id_map[prod_index] = prod.get('_id')

                    existing_products.append({
                        "index": prod_index,
                        "name": prod.get('name'),
                        "english_name": prod.get('english_name'),
                        "category": prod.get('category'),
                        "avg_price": prod.get('avg_price'),
                        "aliases": prod.get('aliases', [])
                    })

                result = match_products_with_gemini(existing_products, receipt_products)

                if not result or 'matches' not in result:
                    print(f"No valid decisions returned for receipt {receipt['_id']}. Skipping.")
                    Receipt.mark_as_processed(receipt['_id'])
                    continue

                product_matches = result['matches']

                for idx, product in enumerate(product_matches):
                    product['price'] = receipt_products[idx].get('price')

                    if product.get('is_match') and product.get('matched_product_index') is not None:
                        product['matched_product_index'] = catalog_index_id_map[product['matched_product_index']]
                    else:
                        product['category'] = receipt_products[idx].get('category')

                Product.add_products(product_matches, store_name, purchase_date)

                Receipt.mark_as_processed(receipt['_id'])
                print(f"Successfully processed receipt {receipt['_id']}.")

            except Exception as e:
                print(f"Error in Product Sync Worker: {e}")
                time.sleep(60)


def start_product_sync_thread(app: Flask):
    thread = threading.Thread(target=product_sync_worker, args=(app,), daemon=True)
    thread.start()
