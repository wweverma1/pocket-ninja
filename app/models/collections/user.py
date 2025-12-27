from app import db
from datetime import datetime, timezone, timedelta
from bson.objectid import ObjectId
from pymongo import ReturnDocument

import random


class User:
    """
    Model class to handle database operations for the 'users' collection.
    Includes base rating of 5, monthly stat tracking, and rank growth monitoring.
    """

    @staticmethod
    def get_collection():
        """Helper to get the MongoDB collection or None if DB is not ready."""
        if db is None:
            return None
        return db['users']

    @staticmethod
    def create_user(username: str, line_account_id: str = None, google_account_id: str = None, yahoo_account_id: str = None):
        """Creates a new user document with initialized lifetime and monthly stats."""
        collection = User.get_collection()
        if collection is None:
            return None

        now = datetime.now(timezone.utc)
        current_month_key = now.strftime("%Y-%m")

        user_data = {
            "username": username,
            "joinedAt": now,

            "userAvatarId": random.randint(1, 8),
            "preferredStoreProximity": 0.5,

            # Rank System
            "rankScore": 0,
            "lastRankIncrement": 0,  # Tracks the points gained in the most recent action

            # Global Lifetime Stats
            "totalContributions": 0,
            "totalExpenditure": 0.0,
            "estimatedTotalSavings": 0.0,

            # Rating System (Start with 5.0 base)
            "userRating": {
                "totalScore": 5,
                "ratedByUsers": []
            },

            # Monthly Stat Tracking
            "statsMonth": current_month_key,
            "monthlyContributions": 0,
            "monthlyExpenditure": 0.0,
            "monthlySavings": 0.0,

            # Tracking bad uploads
            "consecutiveBadUploads": 0,
            "bannedUntil": None
        }

        if line_account_id:
            user_data["lineAccountId"] = line_account_id
        if google_account_id:
            user_data["googleAccountId"] = google_account_id
        if yahoo_account_id:
            user_data["yahooAccountId"] = yahoo_account_id

        try:
            # --- Indexes ---
            collection.create_index([("username", 1)], unique=True)

            # Index for Leaderboard (Monthly Contributions DESC, JoinedAt ASC)
            collection.create_index([("monthlyContributions", -1), ("joinedAt", 1)])

            # Index for Rating Score
            collection.create_index([("userRating.totalScore", -1)])

            for field in ["lineAccountId", "googleAccountId", "yahooAccountId"]:
                if field in user_data:
                    collection.create_index([(field, 1)], unique=True,
                                            partialFilterExpression={field: {"$exists": True}})

            result = collection.insert_one(user_data)
            return result.inserted_id
        except Exception as e:
            print(f"Error creating user: {e}")
            return None

    @staticmethod
    def check_and_reset_monthly_stats(user_id: str):
        """Resets monthly stats if the calendar month has changed."""
        collection = User.get_collection()
        if collection is None:
            return

        now_month = datetime.now(timezone.utc).strftime("%Y-%m")

        collection.update_one(
            {"_id": ObjectId(user_id), "statsMonth": {"$ne": now_month}},
            {
                "$set": {
                    "statsMonth": now_month,
                    "monthlyContributions": 0,
                    "monthlyExpenditure": 0.0,
                    "monthlySavings": 0.0
                }
            }
        )

    @staticmethod
    def update_user_stats(user_id: str, rank_increment: int = 0, contribution: int = 0, expenditure: float = 0.0, savings: float = 0.0):
        """
        Updates lifetime and monthly stats, and stores the latest rank gain.
        """
        collection = User.get_collection()
        if collection is None:
            return False

        User.check_and_reset_monthly_stats(user_id)

        result = collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$inc": {
                    "rankScore": rank_increment,
                    "totalContributions": contribution,
                    "monthlyContributions": contribution,
                    "totalExpenditure": expenditure,
                    "monthlyExpenditure": expenditure,
                    "estimatedTotalSavings": savings,
                    "monthlySavings": savings
                },
                "$set": {
                    "lastRankIncrement": rank_increment,  # Overwrites with newest gain
                    "consecutiveBadUploads": 0,
                    "bannedUntil": None
                }
            }
        )
        return result.modified_count == 1

    @staticmethod
    def add_user_rating(target_user_id: str, rater_user_id: str, score: int):
        """Adds a rating score (1-5) if the rater hasn't rated this user before."""
        collection = User.get_collection()
        if collection is None:
            return False
        if not (1 <= score <= 5):
            return False

        result = collection.update_one(
            {
                "_id": ObjectId(target_user_id),
                "userRating.ratedByUsers": {"$ne": ObjectId(rater_user_id)}
            },
            {
                "$push": {"userRating.ratedByUsers": ObjectId(rater_user_id)},
                "$inc": {"userRating.totalScore": score}
            }
        )
        return result.modified_count == 1

    @staticmethod
    def get_id_and_username_by_social_account_id(social_id: str, provider: str):
        collection = User.get_collection()
        if collection is None:
            return (None, None)

        field_map = {'google': 'googleAccountId', 'line': 'lineAccountId', 'yahoo': 'yahooAccountId'}
        field = field_map.get(provider)
        if not field:
            return (None, None)

        user = collection.find_one({field: social_id}, {"_id": 1, "username": 1})
        return (user['_id'], user['username']) if user else (None, None)

    @staticmethod
    def update_username(user_id: str, chosen_username: str):
        collection = User.get_collection()
        if collection is None or not ObjectId.is_valid(user_id):
            return 2

        # 1. Length Restriction
        if len(chosen_username) > 20:
            return 3  # Error code 3: Username too long

        existing_user = collection.find_one({
            "username": chosen_username,
            "_id": {"$ne": ObjectId(user_id)}
        })
        if existing_user:
            return 1

        result = collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"username": chosen_username}}
        )
        return 0 if result.matched_count > 0 else 2

    @staticmethod
    def update_avatar_id(user_id: str, avatar_id: int):
        collection = User.get_collection()
        if collection is None or not ObjectId.is_valid(user_id):
            return False

        result = collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"userAvatarId": avatar_id}}
        )
        return result.matched_count > 0

    @staticmethod
    def update_proximity(user_id: str, proximity: float):
        collection = User.get_collection()
        if collection is None or not ObjectId.is_valid(user_id):
            return False

        result = collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"preferredStoreProximity": proximity}}
        )
        return result.matched_count > 0

    @staticmethod
    def get_by_id(user_id: str):
        collection = User.get_collection()
        if collection is None or not ObjectId.is_valid(user_id):
            return None
        return collection.find_one({"_id": ObjectId(user_id)})

    @staticmethod
    def get_user_score_detail(user_id: str):
        """
        Calculates the user's rank based on monthly contributions.
        Filter: monthlyContributions > 0.
        Sorting: monthlyContributions DESC, joinedAt ASC (tie-breaker).
        Returns: {'rank': int, 'score': int}
        """
        collection = User.get_collection()
        if collection is None:
            return None

        # Fetch required fields for new ranking logic
        user = collection.find_one(
            {"_id": ObjectId(user_id)},
            {"monthlyContributions": 1, "joinedAt": 1}
        )
        if not user:
            return None

        my_score = user.get("monthlyContributions", 0)
        my_joined_at = user.get("joinedAt")

        # If contribution is 0, they are not on the leaderboard
        if my_score <= 0:
            return None

        # Count users who are strictly better:
        # 1. Higher score
        # 2. Same score but joined earlier
        higher_rank_count = collection.count_documents({
            "$or": [
                {"monthlyContributions": {"$gt": my_score}},
                {
                    "monthlyContributions": my_score,
                    "joinedAt": {"$lt": my_joined_at}
                }
            ]
        })

        return {
            "rank": higher_rank_count + 1,
            "score": my_score
        }

    @staticmethod
    def get_top_users(limit=3):
        """
        Fetches the top N users based on monthlyContributions.
        Filter: monthlyContributions > 0.
        Sort: monthlyContributions DESC, joinedAt ASC.
        Returns a list of dicts: {username, avatarId, score, contributions}
        """
        collection = User.get_collection()
        if collection is None:
            return []

        # Update Query and Sort
        cursor = collection.find(
            {"monthlyContributions": {"$gt": 0}},  # Only non-zero contributions
            {
                "username": 1,
                "userAvatarId": 1,
                "monthlyContributions": 1,  # Fetch monthly stats
                "_id": 0
            }
        ).sort([("monthlyContributions", -1), ("joinedAt", 1)]).limit(limit)

        top_users = []
        for doc in cursor:
            top_users.append({
                "username": doc.get("username"),
                "avatarId": doc.get("userAvatarId"),
                # Score is now monthlyContributions
                "score": doc.get("monthlyContributions", 0),
                "contributions": doc.get("monthlyContributions", 0)
            })

        return top_users

    @staticmethod
    def penalize_user(user_id: str):
        """
        Increments bad upload count. If >= 5, bans the user for 24 hours.
        """
        collection = User.get_collection()
        if collection is None:
            return False

        # 1. Atomic Increment & Fetch
        updated_user = collection.find_one_and_update(
            {"_id": ObjectId(user_id)},
            {"$inc": {"consecutiveBadUploads": 1}},
            projection={"consecutiveBadUploads": 1},
            return_document=ReturnDocument.AFTER
        )

        if not updated_user:
            return False

        # 2. Check Threshold & Apply Ban if needed
        if updated_user.get("consecutiveBadUploads", 0) >= 5:
            ban_expiry = datetime.now(timezone.utc) + timedelta(hours=24)

            collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"bannedUntil": ban_expiry}}
            )
            return True  # User was just banned

        return False  # User penalized but not yet banned

    @staticmethod
    def is_upload_allowed(user_id: str):
        """
        Checks if user is banned. 
        If ban has expired, automatically resets stats and allows access.
        """
        collection = User.get_collection()
        if collection is None:
            return True

        user = collection.find_one(
            {"_id": ObjectId(user_id)},
            {"bannedUntil": 1}
        )

        if not user:
            return True

        banned_until = user.get("bannedUntil")

        if banned_until is None:
            return True

        now = datetime.now(timezone.utc)

        if banned_until.tzinfo is None:
            banned_until = banned_until.replace(tzinfo=timezone.utc)

        if now <= banned_until:
            return False

        collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"bannedUntil": None, "consecutiveBadUploads": 0}}
        )
        return True
