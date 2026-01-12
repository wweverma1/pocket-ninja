from app import db
from datetime import datetime, timezone
from bson.objectid import ObjectId


class Feedback:

    @staticmethod
    def get_collection():
        if db is None:
            return None
        return db['feedback']

    @staticmethod
    def upsert_feedback(user_id: str, rating: int = None, message: str = None):
        collection = Feedback.get_collection()
        if collection is None:
            return None

        collection.create_index([("userId", 1)], unique=True)
        collection.create_index([("rating", 1)])

        now = datetime.now(timezone.utc)
        uid = ObjectId(user_id)

        clean_message = message.strip() if message else None

        existing_doc = collection.find_one({"userId": uid})

        if existing_doc:
            update_fields = {"lastUpdated": now}

            if rating is not None:
                update_fields["rating"] = rating

            if clean_message:
                old_msg = existing_doc.get("message", "")
                timestamp_str = now.strftime("%Y-%m-%d")
                if old_msg:
                    new_full_msg = f"{old_msg}\n\n[{timestamp_str}] {clean_message}"
                else:
                    new_full_msg = f"[{timestamp_str}] {clean_message}"

                update_fields["message"] = new_full_msg

            collection.update_one({"_id": existing_doc["_id"]}, {"$set": update_fields})
            return True

        else:
            initial_message = ""
            if clean_message:
                initial_message = f"[{now.strftime('%Y-%m-%d')}] {clean_message}"

            document = {
                "userId": uid,
                "rating": rating,
                "message": initial_message,
                "submittedAt": now,
                "lastUpdated": now
            }
            collection.insert_one(document)
            return True

    @staticmethod
    def get_avg_rating():
        collection = Feedback.get_collection()
        if collection is None:
            return None

        pipeline = [
            {"$match": {"rating": {"$ne": None}}},
            {"$group": {"_id": None, "avgRating": {"$avg": "$rating"}}}
        ]

        result = list(collection.aggregate(pipeline))

        if result:
            return round(result[0]['avgRating'], 2)
        return None

    @staticmethod
    def get_by_user_id(user_id: str):
        collection = Feedback.get_collection()
        if collection is None:
            return None
        return collection.find_one({"userId": ObjectId(user_id)})
