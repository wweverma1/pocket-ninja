from app import db
from datetime import datetime
from bson.objectid import ObjectId


class Product:
    @staticmethod
    def get_collection():
        if db is None:
            return None
        return db['products']

    @staticmethod
    def get_full_catalog():
        collection = Product.get_collection()
        if collection is None:
            return []

        cursor = collection.find({}, {
            "name": 1,
            "englishName": 1,
            "category": 1,
            "avgPrice": 1,
            "aliases": 1
        })

        catalog = []
        for doc in cursor:
            catalog.append({
                "_id": doc['_id'],
                "name": doc.get('name', ''),
                "english_name": doc.get('englishName', ''),
                "category": doc.get('category', 'other'),
                "avg_price": doc.get('avgPrice', 0),
                "aliases": doc.get('aliases', [])
            })

        return catalog

    @staticmethod
    def add_products(product_matches: list, store_name: str, purchase_date: datetime):
        collection = Product.get_collection()
        if collection is None:
            return

        for product_match in enumerate(product_matches):
            try:
                is_match = product_match.get('is_match')
                matched_product_index = product_match.get('matched_product_index')
                enrichment_action = product_match.get('enrichment_action')
                canonical_ja = product_match.get('canonical_name_ja')
                canonical_en = product_match.get('canonical_name_en')

                # --- CASE 1: NEW PRODUCT ---
                if not is_match or matched_product_index is None:
                    # Insert New
                    new_doc = {
                        "name": canonical_ja,
                        "englishName": canonical_en,
                        "category": product_match.get('category', 'other'),
                        "avgPrice": price,
                        "aliases": [],
                        "prices": {
                            store_name: {
                                "price": price,
                                "date": purchase_date
                            }
                        },
                        "lastUpdated": datetime.now()
                    }
                    collection.insert_one(new_doc)
                    print(f"Inserted NEW: {canonical_ja}")
                    continue

                # --- CASE 2: MATCH EXISTING ---
                existing_product_data = get_db_product_by_index(matched_index)
                if not existing_product_data:
                    print(f"Error: Invalid match index {matched_index}")
                    continue

                product_id = existing_product_data['_id']

                update_ops = {
                    "$set": {"lastUpdated": datetime.now()},
                    "$addToSet": {}
                }

                # A. Handle Enrichment
                if enrichment_action == "update_name":
                    update_ops["$set"]["name"] = canonical_ja
                    update_ops["$set"]["englishName"] = canonical_en

                elif enrichment_action == "add_alias":
                    # Add the raw receipt name as an alias if it differs from canonical
                    raw_name = receipt_item.get('name')
                    if raw_name and raw_name != existing_product_data['name']:
                        update_ops["$addToSet"]["aliases"] = raw_name

                elif enrichment_action == "merge_information":
                    # Update names if the new canonical is "better" (handled by LLM choice)
                    update_ops["$set"]["name"] = canonical_ja
                    if canonical_en:
                        update_ops["$set"]["englishName"] = canonical_en

                # B. Update Price Logic (Standard Avg Calc)
                # We need to fetch the fresh document to calculate avg accurately
                # (context might be stale if multiple updates happen in one batch)
                fresh_doc = collection.find_one({"_id": product_id})
                if fresh_doc:
                    current_avg = fresh_doc.get('avgPrice', price)
                    prices_dict = fresh_doc.get('prices', {})
                    store_entry = prices_dict.get(store_name)
                    store_count = len(prices_dict)

                    should_update_price = False
                    new_avg = current_avg

                    if store_entry:
                        # Existing store: Update only if newer
                        last_date = store_entry.get('date')
                        if not isinstance(last_date, datetime) or last_date < purchase_date:
                            should_update_price = True
                            # Avg update approximation
                            price_diff = price - store_entry.get('price')
                            safe_count = store_count if store_count > 0 else 1
                            new_avg = round(current_avg + (price_diff / safe_count))
                    else:
                        # New store for this product
                        should_update_price = True
                        new_avg = round((current_avg * store_count + price) / (store_count + 1))

                    if should_update_price:
                        update_ops["$set"]["avgPrice"] = new_avg
                        update_ops["$set"][f"prices.{store_name}"] = {
                            "price": price,
                            "date": purchase_date
                        }

                # Cleanup empty operators
                if not update_ops["$addToSet"]:
                    del update_ops["$addToSet"]

                collection.update_one({"_id": product_id}, update_ops)
                print(f"Updated {product_id} with action {enrichment_action}")

            except Exception as e:
                print(f"Error applying product_match for index {i}: {e}")
