from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from bson.objectid import ObjectId
from app import db


class Receipt:
    @staticmethod
    def get_collection():
        if db is None:
            return None
        return db['receipts']

    @staticmethod
    def create_receipt(user_id: str) -> Optional[ObjectId]:
        collection = Receipt.get_collection()
        if collection is None:
            return None

        try:
            collection.create_index([("userId", 1), ("submittedAt", -1)])
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
            "processed": False
        }

        result = collection.insert_one(document)
        return result.inserted_id

    @staticmethod
    def update_receipt_status(
        receipt_id: ObjectId,
        status: str,
        status_message: Optional[dict],
        purchase_date: Optional[datetime] = None,
        store_name: Optional[str] = None,
        store_identifier: Optional[dict] = None,
        total_amount: Optional[float] = None,
        products_found: Optional[List[dict]] = None
    ) -> None:
        collection = Receipt.get_collection()
        if collection is None:
            return

        update_fields = {
            "status": status,
            "statusMessage": status_message
        }

        if status == "SUCCESS":
            update_fields.update({
                "purchaseDate": purchase_date,
                "storeName": store_name,
                "storeIdentifier": store_identifier,
                "totalAmount": total_amount,
                "productsFound": products_found,
                "processed": False
            })

        collection.update_one(
            {"_id": receipt_id},
            {"$set": update_fields}
        )

    @staticmethod
    def get_unprocessed_receipt() -> Optional[Dict[str, Any]]:
        collection = Receipt.get_collection()
        if collection is None:
            return None

        query = {
            "status": "SUCCESS",
            "processed": False
        }
        return collection.find_one(query, sort=[("submittedAt", 1)])

    @staticmethod
    def mark_as_processed(receipt_id: ObjectId, final_matches: List[Dict]) -> None:
        collection = Receipt.get_collection()
        if collection is None:
            return

        collection.update_one(
            {"_id": receipt_id},
            {
                "$set": {
                    "processed": True,
                    "matchingResult": final_matches
                }
            }
        )

    @staticmethod
    def get_by_user(user_id: str, month: Optional[str] = None) -> List[Dict[str, Any]]:
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
                "status": "SUCCESS",
                "submittedAt": {
                    "$gte": dt_start,
                    "$lt": dt_end
                }
            }
        except ValueError:
            print(f"Invalid month format provided: {month}")
            return []

        projection = {"_id": 0, "userId": 0, "submittedAt": 0, "processed": 0, "matchingResult": 0}
        cursor = collection.find(query, projection).sort("purchaseDate", -1)

        return list(cursor)
