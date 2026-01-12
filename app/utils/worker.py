import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any

from flask import Flask
from app.models.collections.receipt import Receipt
from app.models.collections.product import Product
from app.utils.gemini_product_matching_helper import match_products_with_gemini


def _parse_purchase_date(date_input: Any) -> datetime:
    default_date = datetime.now(timezone.utc) - timedelta(days=3)

    if not date_input:
        return default_date

    try:
        if isinstance(date_input, str):
            dt = datetime.strptime(date_input, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)

        if isinstance(date_input, datetime):
            return date_input.astimezone(timezone.utc) if date_input.tzinfo else date_input.replace(tzinfo=timezone.utc)

        return default_date
    except Exception as e:
        print(f"Date parsing failed ({date_input}): {e}. Using default.")
        return default_date


def _prepare_catalog_context(full_catalog: List[Dict]) -> tuple[List[Dict], Dict[int, Any]]:
    gemini_context_products = []
    index_map = {}

    for idx, prod in enumerate(full_catalog):
        prod_index = idx + 1
        index_map[prod_index] = prod.get('_id')

        gemini_context_products.append({
            "index": prod_index,
            "name": prod.get('name'),
            "english_name": prod.get('english_name'),
            "category": prod.get('category'),
            "avg_price": prod.get('avg_price'),
        })

    return gemini_context_products, index_map


def _process_single_receipt(app: Flask, receipt: Dict) -> None:
    receipt_id = receipt['_id']
    print(f"Processing receipt {receipt_id} for product matching...")

    receipt_products = receipt.get('productsFound', [])
    if not receipt_products:
        print(f"Receipt {receipt_id} has no products. Marking processed.")
        Receipt.mark_as_processed(receipt_id)
        return

    store_name = receipt.get('storeName')
    purchase_date = _parse_purchase_date(receipt.get('purchaseDate'))

    full_catalog = Product.get_full_catalog()
    existing_products_ctx, index_id_map = _prepare_catalog_context(full_catalog)

    result = match_products_with_gemini(existing_products_ctx, receipt_products)

    if not result or 'matches' not in result:
        print(f"No valid decisions from Gemini for {receipt_id}. Skipping.")
        return

    final_matches = []
    gemini_matches = result['matches']

    for idx, match_decision in enumerate(gemini_matches):
        match_decision['price'] = receipt_products[idx].get('price')

        if match_decision.get('is_match'):
            suggested_idx = match_decision.get('matched_product_index')

            if suggested_idx in index_id_map:
                match_decision['matched_product_index'] = index_id_map[suggested_idx]
            else:
                print(
                    f"Warning: Gemini returned invalid index {suggested_idx} "
                    f"for receipt {receipt_id}. Treating as NEW."
                )
                match_decision['is_match'] = False
                match_decision['matched_product_index'] = None
                match_decision['category'] = receipt_products[idx].get('category')
        else:
            match_decision['category'] = receipt_products[idx].get('category')

        final_matches.append(match_decision)

    Product.add_products(final_matches, store_name, purchase_date)
    Receipt.mark_as_processed(receipt_id)
    print(f"Successfully processed receipt {receipt_id}.")


def product_sync_worker(app: Flask):
    print("Background Product Sync Worker Started.")

    with app.app_context():
        while True:
            try:
                receipt = Receipt.get_unprocessed_receipt()

                if not receipt:
                    time.sleep(5 * 60)
                    continue

                _process_single_receipt(app, receipt)

            except Exception as e:
                print(f"Critical Error in Product Sync Worker: {e}")
                time.sleep(5 * 60)


def start_product_sync_thread(app: Flask):
    thread = threading.Thread(target=product_sync_worker, args=(app,), daemon=True)
    thread.start()
