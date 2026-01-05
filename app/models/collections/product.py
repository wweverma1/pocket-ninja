from app import db
from datetime import datetime


class Product:
    @staticmethod
    def get_collection():
        if db is None:
            return None
        return db['products']

    @staticmethod
    def get_product_catalog():
        collection = Product.get_collection()
        if collection is None:
            return []

        cursor = collection.find({}, {"name": 1, "avgPrice": 1, "_id": 0})

        catalog = []
        for doc in cursor:
            avg_price = doc.get('avgPrice')

            catalog.append({
                "name": doc['name'],
                "min_match_price": round(0.8 * avg_price),
                "max_match_price": round(1.2 * avg_price)
            })

        return catalog

    @staticmethod
    def bulk_upsert(purchase_date: datetime, store_name: str, products_data: list):
        collection = Product.get_collection()
        if collection is None:
            return 0

        try:
            collection.create_index([("name", 1)])
        except Exception as e:
            print(f"Error creating product indexes: {e}")

        updated_count = 0

        for item in products_data:
            name = item.get('name')
            english_name = item.get('english_name')
            price = item.get('price')

            updated_name = item.get('updated_name')
            updated_english_name = item.get('updated_english_name')

            if not name or price is None:
                continue

            price = round(price)

            try:
                existing_product = collection.find_one({"name": name})

                if existing_product:
                    prices = existing_product.get('prices', {})
                    existing_store_data = prices.get(store_name)

                    current_avg = existing_product.get('avgPrice')
                    store_count = len(prices)

                    set_fields = {}

                    should_update_price = False

                    if existing_store_data:
                        last_update_date = existing_store_data.get('date')

                        if not isinstance(last_update_date, datetime) or last_update_date < purchase_date:
                            should_update_price = True

                            price_diff = price - existing_store_data.get('price')
                            new_avg = round(current_avg + (price_diff / store_count))
                            set_fields["avgPrice"] = new_avg

                    else:
                        should_update_price = True

                        new_avg = round((current_avg * store_count + price) / (store_count + 1))
                        set_fields["avgPrice"] = new_avg

                    if should_update_price:
                        set_fields[f"prices.{store_name}"] = {
                            "price": price,
                            "date": purchase_date
                        }
                        updated_count += 1

                    if updated_name and isinstance(updated_name, str) and updated_name.strip():
                        set_fields["name"] = updated_name.strip()

                    if updated_english_name and isinstance(updated_english_name, str) and updated_english_name.strip():
                        set_fields["englishName"] = updated_english_name.strip()

                    if set_fields:
                        collection.update_one(
                            {"_id": existing_product["_id"]},
                            {"$set": set_fields}
                        )

                else:
                    collection.insert_one({
                        "name": name,
                        "englishName": english_name,
                        "avgPrice": price,
                        "prices": {
                            store_name: {
                                "price": price,
                                "date": purchase_date
                            }
                        }
                    })
                    updated_count += 1

            except Exception as e:
                print(f"Error upserting product {name}: {e}")

        return updated_count
