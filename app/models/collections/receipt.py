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
        """
        Creates a new receipt record with 'PENDING' status.
        Returns the new receipt_id (ObjectId).
        """
        collection = Receipt.get_collection()
        if collection is None:
            return None

        # Add Index
        try:
            # Compound index: Optimizes 'get_by_user' which filters by userId and sorts by submittedAt
            collection.create_index([("userId", 1), ("submittedAt", -1)])
        except Exception as e:
            print(f"Error creating receipt index: {e}")

        document = {
            "userId": ObjectId(user_id),
            "submittedAt": datetime.now(timezone.utc),
            "status": "PENDING",  # Options: PENDING, SUCCESS, FAILED
            "statusMessage": None,
            "purchaseDate": None,
            "storeName": None,
            "storeIdentifier": None,
            "totalAmount": None,
            "productsFound": None,
            "productsAdded": "FALSE"
        }

        result = collection.insert_one(document)
        return result.inserted_id

    @staticmethod
    def update_receipt_status(receipt_id, status: str, status_message: dict, purchase_date: datetime = None, store_name: str = None, store_identifier: dict = None, total_amount: float = None, products_found: list[dict] = None):
        """
        Updates the receipt status and details after analysis.
        """
        collection = Receipt.get_collection()
        if collection is None:
            return

        update_fields = {
            "status": status,
            "statusMessage": status_message
        }

        # Only update metadata if operation was successful
        if status == "SUCCESS":
            update_fields["purchaseDate"] = purchase_date
            update_fields["storeName"] = store_name
            update_fields["storeIdentifier"] = store_identifier
            update_fields["totalAmount"] = total_amount
            update_fields["productsFound"] = products_found

        collection.update_one(
            {"_id": receipt_id, "status": "PENDING"},
            {"$set": update_fields}
        )

    @staticmethod
    def get_by_user(user_id: str, month: str = None):
        """
        Fetches recent receipts for a user, filtered by month.

        :param user_id: The ID of the user.
        :param month: String in "YYYY-MM" format. Defaults to current UTC month if None.
        """
        collection = Receipt.get_collection()
        if collection is None:
            return []

        # Default to current month if not provided
        if month is None:
            month = datetime.now(timezone.utc).strftime("%Y-%m")

        try:
            # Parse the month string "YYYY-MM"
            dt_start_naive = datetime.strptime(month, "%Y-%m")

            # Make it timezone aware (UTC) to match database storage
            dt_start = dt_start_naive.replace(tzinfo=timezone.utc)

            # Calculate the start of the next month for the upper bound
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

        # Projection to exclude unnecessary fields if needed,
        # but returning full doc (minus internal IDs) is usually fine for this view
        projection = {"_id": 0, "userId": 0}

        cursor = collection.find(query, projection).sort("submittedAt", -1)

        # Convert ObjectId to str for JSON serialization if needed later
        results = []
        for doc in cursor:
            results.append(doc)
        return results
