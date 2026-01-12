from app import db
from datetime import datetime, timezone
from bson.objectid import ObjectId


class Receipt:
    @staticmethod
    def get_collection():
        if db is None:
            return None
        return db['receipts']

    @staticmethod
    def create_receipt(user_id: str):
        collection = Receipt.get_collection()
        if collection is None:
            return None

        try:
            collection.create_index([("userId", 1), ("submittedAt", -1)])
            # Index for worker
            collection.create_index([("status", 1), ("processed", 1)])
        except Exception as e:
            print(f"Error creating receipt index: {e}")

        document = {
            "userId": ObjectId(user_id),
            "submittedAt": datetime.now(timezone.utc),
            "status": "PENDING",
            "statusMessage": None,
            "purchaseDate": None,
            "storeName": None,
            "storeIdentifier": None,
            "totalAmount": None,
            "productsFound": None,
            "processed": "FALSE"
        }

        result = collection.insert_one(document)
        return result.inserted_id

    @staticmethod
    def update_receipt_status(receipt_id, status: str, status_message: dict, purchase_date: datetime = None, store_name: str = None, store_identifier: dict = None, total_amount: float = None, products_found: list[dict] = None):
        collection = Receipt.get_collection()
        if collection is None:
            return

        update_fields = {
            "status": status,
            "statusMessage": status_message
        }

        if status == "SUCCESS":
            update_fields["purchaseDate"] = purchase_date
            update_fields["storeName"] = store_name
            update_fields["storeIdentifier"] = store_identifier
            update_fields["totalAmount"] = total_amount
            update_fields["productsFound"] = products_found
            # Ensure it is ready for processing
            update_fields["processed"] = "FALSE"

        collection.update_one(
            {"_id": receipt_id},
            {"$set": update_fields}
        )

    @staticmethod
    def get_unprocessed_receipt():
        collection = Receipt.get_collection()
        if collection is None:
            return None

        # Find SUCCESS receipts that are NOT processed ("FALSE")
        query = {
            "status": "SUCCESS",
            "processed": "FALSE"
        }
        return collection.find_one(query, sort=[("submittedAt", 1)])

    @staticmethod
    def mark_as_processed(receipt_id):
        """
        Marks a receipt as processed by the background worker.
        """
        collection = Receipt.get_collection()
        if collection is None:
            return

        collection.update_one(
            {"_id": receipt_id},
            {"$set": {"processed": "TRUE"}}
        )

    @staticmethod
    def get_by_user(user_id: str, month: str = None):
        collection = Receipt.get_collection()
        if collection is None:
            return []

        if month is None:
            month = datetime.now(timezone.utc).strftime("%Y-%m")

        try:
            dt_start_naive = datetime.strptime(month, "%Y-%m")
            dt_start = dt_start_naive.replace(tzinfo=timezone.utc)

            if dt_start.month == 12:
                dt_end = dt_start.replace(year=dt_start.year + 1, month=1)
            else:
                dt_end = dt_start.replace(month=dt_start.month + 1)

            query = {
                "userId": ObjectId(user_id),
                "submittedAt": {
                    "$gte": dt_start,
                    "$lt": dt_end
                }
            }
        except ValueError:
            print(f"Invalid month format provided: {month}")
            return []

        projection = {"_id": 0, "userId": 0}
        cursor = collection.find(query, projection).sort("submittedAt", -1)

        results = []
        for doc in cursor:
            results.append(doc)
        return results
