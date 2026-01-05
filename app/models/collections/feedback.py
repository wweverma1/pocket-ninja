from app import db
from datetime import datetime, timezone
from bson.objectid import ObjectId


class Feedback:
    """
    Model class to handle database operations for the 'feedback' collection.
    """

    @staticmethod
    def get_collection():
        if db is None:
            return None
        return db['feedback']

    @staticmethod
    def upsert_feedback(user_id: str, rating: int = None, message: str = None):
        """
        Updates an existing feedback or creates a new one.
        - Updates rating if provided.
        - Appends new message to existing message if provided (not empty/whitespace).
        """
        collection = Feedback.get_collection()
        if collection is None:
            return None

        # Ensure unique index on userId and index on rating for aggregation
        collection.create_index([("userId", 1)], unique=True)
        collection.create_index([("rating", 1)])

        now = datetime.now(timezone.utc)
        uid = ObjectId(user_id)

        # Prepare the message string (if valid)
        clean_message = message.strip() if message else None

        existing_doc = collection.find_one({"userId": uid})

        if existing_doc:
            # --- Update Logic ---
            update_fields = {"lastUpdated": now}

            # Update rating only if provided (using explicit None check)
            if rating is not None:
                update_fields["rating"] = rating

            # Append message if provided
            if clean_message:
                old_msg = existing_doc.get("message", "")
                # Append with timestamp separator
                timestamp_str = now.strftime("%Y-%m-%d")
                if old_msg:
                    new_full_msg = f"{old_msg}\n\n[{timestamp_str}] {clean_message}"
                else:
                    new_full_msg = f"[{timestamp_str}] {clean_message}"

                update_fields["message"] = new_full_msg

            collection.update_one({"_id": existing_doc["_id"]}, {"$set": update_fields})
            return True

        else:
            # --- Insert Logic ---
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
        """Calculates the average rating across all feedbacks (skipping None)."""
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