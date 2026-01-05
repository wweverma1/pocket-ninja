from app import db


class Store:
    @staticmethod
    def get_collection():
        if db is None:
            return None
        return db['stores']

    @staticmethod
    def get_all_store_names():
        """Fetches a list of all available store names from the database."""
        collection = Store.get_collection()
        if collection is None:
            return []

        # Check if collection is empty (or doesn't exist yet)
        if collection.count_documents({}) == 0:
            default_stores = [
                "FamilyMart", "Lawson", "7-Eleven",
                "Seicomart", "AEON", "Co-op", "Satudora"
            ]
            try:
                collection.insert_many([{"name": s} for s in default_stores])
                print("Seeded 'stores' collection with default values.")
            except Exception as e:
                print(f"Error seeding stores: {e}")
                return default_stores

        cursor = collection.find({}, {"name": 1, "_id": 0})
        return [doc['name'] for doc in cursor if 'name' in doc]

    @staticmethod
    def add_store_if_not_exists(store_name: str):
        """Adds a new store to the collection if it doesn't already exist."""
        collection = Store.get_collection()
        if collection is None or not store_name:
            return

        try:
            # Ensure unique index on store name
            collection.create_index([("name", 1)], unique=True)

            # Upsert: If name exists, do nothing. If not, insert it.
            collection.update_one(
                {"name": store_name},
                {"$setOnInsert": {"name": store_name}},
                upsert=True
            )
        except Exception as e:
            print(f"Error adding new store '{store_name}': {e}")