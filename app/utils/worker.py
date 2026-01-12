from typing import Dict, List, Any
from datetime import datetime

from app.models.collections.receipt import Receipt
from app.models.collections.product import Product
from app.utils.gemini_product_matching_helper import match_products_with_gemini


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


def process_receipt_products(receipt_id, products_found: List[Dict], store_name: str, purchase_date: datetime) -> None:
    print(f"Processing receipt {receipt_id} for product catalog...")

    if not products_found:
        print(f"Receipt {receipt_id} has no products. Marking processed.")
        Receipt.mark_as_processed(receipt_id)
        return

    try:
        full_catalog = Product.get_full_catalog()
        existing_products_ctx, index_id_map = _prepare_catalog_context(full_catalog)

        result = match_products_with_gemini(existing_products_ctx, products_found)

        if not result or 'matches' not in result:
            print(f"No valid decisions from Gemini for {receipt_id}. Skipping.")
            Receipt.mark_as_processed(receipt_id)
            return

        final_matches = []
        gemini_matches = result['matches']

        limit = min(len(gemini_matches), len(products_found))

        for idx in range(limit):
            match_decision = gemini_matches[idx]
            receipt_product = products_found[idx]

            match_decision['price'] = receipt_product.get('price')

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
                    match_decision['category'] = receipt_product.get('category')
            else:
                match_decision['category'] = receipt_product.get('category')

            final_matches.append(match_decision)

        if final_matches:
            Product.add_products(final_matches, store_name, purchase_date)

        Receipt.mark_as_processed(receipt_id)
        print(f"Successfully processed receipt {receipt_id}.")

    except Exception as e:
        print(f"Error in process_receipt_products for {receipt_id}: {e}")
