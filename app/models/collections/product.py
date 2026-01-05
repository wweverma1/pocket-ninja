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

        cursor = collection.find({}, {"name": 1, "_id": 0, "englishName": 0, "prices": 0})
        return [doc['name'] for doc in cursor if 'name' in doc]

    @staticmethod
    def bulk_upsert(purchase_date: datetime, store_name: str, products_data: list):
        """
        Updates product prices based on exact name match.
        Handles 'updated_name' and 'updated_english_name' for existing products.
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
            english_name = item.get('english_name')  # Present only if product doesn't exist
            price = item.get('price')

            # Fields specifically for updating existing products
            updated_name = item.get('updated_name')
            updated_english_name = item.get('updated_english_name')

            if not input_name or price is None:
                continue

            try:
                # --- STEP 1: Find Canonical Product (Exact Match Only) ---
                existing_product = collection.find_one({"name": input_name})

                if existing_product:
                    # Case: Product Exists
                    prices = existing_product.get('prices', {})
                    existing_store_data = prices.get(store_name)

                    set_fields = {}

                    # --- Price Update Logic ---
                    should_update_price = False
                    if existing_store_data:
                        # Store exists, check date
                        last_date = existing_store_data.get('date')
                        # Update only if the stored date is older than the new purchase_date
                        if isinstance(last_date, datetime) and last_date < purchase_date:
                            should_update_price = True
                        elif not isinstance(last_date, datetime):
                            # If date format is invalid/missing, force update
                            should_update_price = True
                    else:
                        # Store does not exist in prices list
                        should_update_price = True

                    if should_update_price:
                        set_fields[f"prices.{store_name}"] = {
                            "price": price,
                            "date": purchase_date
                        }
                        updated_count += 1

                    # --- Name/Details Update Logic ---
                    # Check for updated_name
                    if updated_name and isinstance(updated_name, str) and updated_name.strip():
                        set_fields["name"] = updated_name.strip()

                    # Check for updated_english_name
                    if updated_english_name and isinstance(updated_english_name, str) and updated_english_name.strip():
                        set_fields["englishName"] = updated_english_name.strip()

                    # Apply Updates if any fields are set
                    if set_fields:
                        collection.update_one(
                            {"_id": existing_product["_id"]},
                            {"$set": set_fields}
                        )

                else:
                    # Case: Brand New Product
                    collection.insert_one({
                        "name": input_name,
                        "englishName": english_name,  # Use the creation-time english name
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
