from app import db
from datetime import datetime
from typing import List, Dict


class Product:
    @staticmethod
    def get_collection():
        if db is None:
            return None
        return db['products']

    @staticmethod
    def get_full_catalog() -> List[Dict]:
        collection = Product.get_collection()
        if collection is None:
            return []

        cursor = collection.find({}, {
            "name": 1,
            "englishName": 1,
            "category": 1,
            "avgPrice": 1,
        })

        catalog = []
        for doc in cursor:
            catalog.append({
                "_id": doc['_id'],
                "name": doc.get('name', ''),
                "english_name": doc.get('englishName', ''),
                "category": doc.get('category', 'other'),
                "avg_price": doc.get('avgPrice', 0)
            })

        return catalog

    @staticmethod
    def _sanitize_store_key(store_name: str) -> str:
        if not store_name:
            return "unknown_store"
        return store_name.replace(".", "").replace("$", "")

    @staticmethod
    def _create_new_product(collection, match_data: Dict, store_name: str, purchase_date: datetime):
        safe_store = Product._sanitize_store_key(store_name)
        price = match_data.get('price', 0)

        new_doc = {
            "name": match_data.get('canonical_name_ja'),
            "englishName": match_data.get('canonical_name_en'),
            "category": match_data.get('category', 'other'),
            "avgPrice": price,
            "prices": {
                safe_store: {
                    "price": price,
                    "date": purchase_date
                }
            }
        }
        collection.insert_one(new_doc)

    @staticmethod
    def _update_existing_product(
        collection,
        existing_product: Dict,
        match_data: Dict,
        store_name: str,
        purchase_date: datetime
    ):
        safe_store = Product._sanitize_store_key(store_name)
        price = match_data.get('price', 0)
        canonical_ja = match_data.get('canonical_name_ja')
        canonical_en = match_data.get('canonical_name_en')

        prices = existing_product.get('prices', {})
        existing_store_data = prices.get(safe_store)

        current_avg = existing_product.get('avgPrice', 0)
        store_count = len(prices)

        set_fields = {}
        should_update_price = False

        if existing_store_data:
            last_update_date = existing_store_data.get('date')

            if not isinstance(last_update_date, datetime) or last_update_date < purchase_date:
                should_update_price = True
                price_diff = price - existing_store_data.get('price', 0)
                count = max(store_count, 1)
                new_avg = round(current_avg + (price_diff / count))
                set_fields["avgPrice"] = new_avg
        else:
            should_update_price = True
            new_avg = round((current_avg * store_count + price) / (store_count + 1))
            set_fields["avgPrice"] = new_avg

        if should_update_price:
            set_fields[f"prices.{safe_store}"] = {
                "price": price,
                "date": purchase_date
            }

        if canonical_ja and isinstance(canonical_ja, str) and canonical_ja.strip():
            set_fields["name"] = canonical_ja.strip()

        if canonical_en and isinstance(canonical_en, str) and canonical_en.strip():
            set_fields["englishName"] = canonical_en.strip()

        if set_fields:
            collection.update_one(
                {"_id": existing_product["_id"]},
                {"$set": set_fields}
            )

    @staticmethod
    def add_products(product_matches: List[Dict], store_name: str, purchase_date: datetime):
        collection = Product.get_collection()
        if collection is None:
            return

        for product_match in product_matches:
            try:
                is_match = product_match.get('is_match')
                matched_product_index = product_match.get('matched_product_index')

                if not is_match or matched_product_index is None:
                    Product._create_new_product(collection, product_match, store_name, purchase_date)

                else:
                    existing_product = collection.find_one({"_id": matched_product_index})
                    if existing_product:
                        Product._update_existing_product(collection, existing_product,
                                                         product_match, store_name, purchase_date)

            except Exception as e:
                print(f"Error updating products collection: {e}")
