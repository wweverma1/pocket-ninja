from app import db
from datetime import datetime


class Product:
    @staticmethod
    def get_collection():
        if db is None:
            return None
        return db['products']

    @staticmethod
    def get_all_product_names():
        """Fetches a list of all available products from the database."""
        collection = Product.get_collection()
        if collection is None:
            return []

        # Return _id: 0 so we get a clean list of dicts: [{'name': '...', 'englishName': '...'}]
        cursor = collection.find({}, {"_id": 0, "name": 1, "englishName": 1})
        return list(cursor)

    @staticmethod
    def bulk_upsert(purchase_date: datetime, store_name: str, products_data: list):
        """
        Updates product prices based on exact name match.
        """
        collection = Product.get_collection()
        if collection is None:
            return 0

        # --- Index Creation ---
        try:
            collection.create_index([("name", 1)])
            collection.create_index([("prices", 1)])
        except Exception as e:
            print(f"Error creating product indexes: {e}")

        updated_count = 0

        for item in products_data:
            input_name = item.get('name')
            english_name = item.get('english_name')
            price = item.get('price')

            if not input_name or price is None:
                continue

            try:
                # --- STEP 1: Find Canonical Product (Exact Match Only) ---
                existing_product = collection.find_one({"name": input_name})

                if existing_product:
                    # Case: Product Exists
                    prices = existing_product.get('prices', {})
                    existing_store_data = prices.get(store_name)
                    should_update = False

                    if existing_store_data:
                        # Store exists, check date
                        last_date = existing_store_data.get('date')
                        # Update only if the stored date is older than the new purchase_date
                        if isinstance(last_date, datetime) and last_date < purchase_date:
                            should_update = True
                        elif not isinstance(last_date, datetime):
                            # If date format is invalid/missing, force update
                            should_update = True
                    else:
                        # Store does not exist in prices list
                        should_update = True

                    if should_update:
                        update_fields = {
                            f"prices.{store_name}": {
                                "price": price,
                                "date": purchase_date
                            },
                            "englishName": english_name
                        }
                        
                        collection.update_one(
                            {"_id": existing_product["_id"]},
                            {"$set": update_fields}
                        )
                        updated_count += 1

                else:
                    # Case: Brand New Product
                    collection.insert_one({
                        "name": input_name,
                        "englishName": english_name,
                        "prices": {
                            store_name: {
                                "price": price,
                                "date": purchase_date
                            }
                        }
                    })
                    updated_count += 1

            except Exception as e:
                print(f"Error upserting product {input_name}: {e}")

        return updated_count