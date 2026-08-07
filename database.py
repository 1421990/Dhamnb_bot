"""
Async MongoDB Database Interface Module
Handles all MongoDB Atlas interactions using Motor, including connection management,
indexing for fuzzy search, settings persistence, and request deduplication.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import TEXT, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from config import Config

logger = logging.getLogger("Database")


class Database:
    def __init__(self) -> None:
        self._client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

    async def connect(self) -> None:
        """Establishes connection to MongoDB Atlas and ensures indexes."""
        try:
            self._client = AsyncIOMotorClient(
                Config.MONGODB_URI,
                maxPoolSize=20,
                minPoolSize=5,
                serverSelectionTimeoutMS=5000,
            )
            self.db = self._client[Config.DATABASE_NAME]
            # Ping to verify connection
            await self.db.command("ping")
            logger.info("Successfully connected to MongoDB Atlas.")

            await self._ensure_indexes()
            await self._init_settings()
        except PyMongoError as e:
            logger.critical(f"Failed to connect to MongoDB: {e}")
            raise e

    async def close(self) -> None:
        """Closes MongoDB connection cleanly."""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed.")

    async def _ensure_indexes(self) -> None:
        """Creates necessary database indexes for fast query performance."""
        if self.db is None:
            return

        # Text and compound indexes for smart search & fuzzy lookup
        await self.db.movies.create_index(
            [("title", TEXT), ("aliases", TEXT), ("overview", TEXT)],
            weights={"title": 10, "aliases": 5, "overview": 1},
            name="movie_search_text_idx",
        )
        await self.db.movies.create_index([("tmdb_id", ASCENDING)], unique=True, sparse=True)
        await self.db.movies.create_index([("file_id", ASCENDING)])

        # User indexes
        await self.db.users.create_index([("user_id", ASCENDING)], unique=True)

        # Request deduplication index
        await self.db.requests.create_index([("query_clean", ASCENDING)], unique=True)

        # Log index
        await self.db.logs.create_index([("timestamp", DESCENDING)])

        logger.info("Database indexes ensured.")

    async def _init_settings(self) -> None:
        """Initializes system settings if not already present."""
        if self.db is None:
            return
        existing = await self.db.settings.find_one({"_id": "global_settings"})
        if not existing:
            default_settings = {
                "_id": "global_settings",
                "shortlink_enabled": False,
                "auto_post_enabled": True,
                "force_sub_enabled": True,
                "custom_logo_text": "MOVIE BOT",
            }
            await self.db.settings.insert_one(default_settings)
            logger.info("Default settings initialized.")

    # --- Movie Operations ---

    async def add_movie(self, movie_data: Dict[str, Any]) -> bool:
        """Inserts or updates a movie record in the movies collection."""
        if self.db is None:
            return False
        try:
            movie_data["updated_at"] = datetime.utcnow()
            if "created_at" not in movie_data:
                movie_data["created_at"] = datetime.utcnow()

            await self.db.movies.update_one(
                {"file_id": movie_data["file_id"]},
                {"$set": movie_data},
                upsert=True,
            )
            return True
        except PyMongoError as e:
            logger.error(f"Error adding movie: {e}")
            return False

    async def search_movies(self, query: str, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Smart search supporting regex partial matching and text search."""
        if self.db is None:
            return []

        clean_query = re.escape(query.strip())
        regex_pattern = re.compile(f".*{clean_query}.*", re.IGNORECASE)

        # Search by exact regex match on title or alias first
        cursor = self.db.movies.find(
            {"$or": [{"title": regex_pattern}, {"aliases": regex_pattern}]}
        ).skip(offset).limit(limit)

        results = await cursor.to_list(length=limit)

        # If regex finds nothing, fall back to MongoDB text search
        if not results:
            cursor = self.db.movies.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}},
            ).sort([("score", {"$meta": "textScore"})]).skip(offset).limit(limit)
            results = await cursor.to_list(length=limit)

        return results

    async def get_movie_by_id(self, movie_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a movie by MongoDB _id or custom string ID."""
        if self.db is None:
            return None
        from bson.objectid import ObjectId

        try:
            return await self.db.movies.find_one({"_id": ObjectId(movie_id)})
        except Exception:
            return await self.db.movies.find_one({"_id": movie_id})

    async def delete_movie(self, movie_id: str) -> bool:
        """Deletes a movie by ID."""
        if self.db is None:
            return False
        from bson.objectid import ObjectId

        try:
            res = await self.db.movies.delete_one({"_id": ObjectId(movie_id)})
            return res.deleted_count > 0
        except Exception:
            res = await self.db.movies.delete_one({"_id": movie_id})
            return res.deleted_count > 0

    async def get_total_movies_count(self) -> int:
        """Returns total count of stored movies."""
        if self.db is None:
            return 0
        return await self.db.movies.count_documents({})

    # --- User Operations ---

    async def add_user(self, user_id: int, name: str, username: Optional[str] = None) -> bool:
        """Registers or updates a user in the database."""
        if self.db is None:
            return False
        try:
            await self.db.users.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "name": name,
                        "username": username,
                        "updated_at": datetime.utcnow(),
                    },
                    "$setOnInsert": {
                        "user_id": user_id,
                        "is_banned": False,
                        "joined_at": datetime.utcnow(),
                    },
                },
                upsert=True,
            )
            return True
        except PyMongoError as e:
            logger.error(f"Error saving user {user_id}: {e}")
            return False

    async def is_user_banned(self, user_id: int) -> bool:
        """Checks if a user is banned."""
        if self.db is None:
            return False
        user = await self.db.users.find_one({"user_id": user_id})
        return user.get("is_banned", False) if user else False

    async def set_user_ban(self, user_id: int, ban_status: bool) -> bool:
        """Bans or unbans a user."""
        if self.db is None:
            return False
        res = await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"is_banned": ban_status}},
        )
        return res.modified_count > 0

    async def get_all_user_ids(self) -> List[int]:
        """Retrieves list of all user IDs for broadcasting."""
        if self.db is None:
            return []
        cursor = self.db.users.find({"is_banned": False}, {"user_id": 1, "_id": 0})
        users = await cursor.to_list(length=None)
        return [u["user_id"] for u in users if "user_id" in u]

    async def get_total_users_count(self) -> int:
        """Returns total registered users count."""
        if self.db is None:
            return 0
        return await self.db.users.count_documents({})

    # --- Movie Request System (Deduplication) ---

    async def add_or_update_request(self, query: str, user_id: int, name: str, username: Optional[str]) -> Dict[str, Any]:
        """
        Appends user to existing request if movie query already exists,
        preventing duplicate request records.
        """
        if self.db is None:
            return {}

        clean_query = query.strip().lower()
        user_info = {
            "user_id": user_id,
            "name": name,
            "username": username,
            "requested_at": datetime.utcnow(),
        }

        doc = await self.db.requests.find_one({"query_clean": clean_query})

        if doc:
            # Check if user already requested
            existing_users = [u["user_id"] for u in doc.get("users", [])]
            if user_id not in existing_users:
                await self.db.requests.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$push": {"users": user_info},
                        "$set": {"updated_at": datetime.utcnow()},
                    },
                )
            return {"is_new": False, "request_id": str(doc["_id"]), "total_requested": len(existing_users) + (1 if user_id not in existing_users else 0)}
        else:
            new_request = {
                "query": query.strip(),
                "query_clean": clean_query,
                "users": [user_info],
                "status": "pending",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            res = await self.db.requests.insert_one(new_request)
            return {"is_new": True, "request_id": str(res.inserted_id), "total_requested": 1}

    async def fulfill_and_get_requested_users(self, movie_title: str) -> List[int]:
        """
        Finds pending requests matching newly added movie title,
        marks them as fulfilled, and returns affected user IDs to notify.
        """
        if self.db is None:
            return []

        clean_title = movie_title.strip().lower()
        regex_pattern = re.compile(f".*{re.escape(clean_title)}.*", re.IGNORECASE)

        matching_requests = await self.db.requests.find(
            {"status": "pending", "query_clean": regex_pattern}
        ).to_list(length=None)

        user_ids = set()
        for req in matching_requests:
            for u in req.get("users", []):
                user_ids.add(u["user_id"])
            await self.db.requests.update_one(
                {"_id": req["_id"]},
                {"$set": {"status": "fulfilled", "fulfilled_at": datetime.utcnow()}},
            )

        return list(user_ids)

    async def get_total_requests_count(self) -> int:
        """Returns total pending requests count."""
        if self.db is None:
            return 0
        return await self.db.requests.count_documents({"status": "pending"})

    # --- System Settings Operations ---

    async def get_settings(self) -> Dict[str, Any]:
        """Retrieves global configuration settings from DB."""
        if self.db is None:
            return {}
        settings = await self.db.settings.find_one({"_id": "global_settings"})
        return settings or {}

    async def update_setting(self, key: str, value: Any) -> bool:
        """Updates a single setting key."""
        if self.db is None:
            return False
        res = await self.db.settings.update_one(
            {"_id": "global_settings"},
            {"$set": {key: value}},
            upsert=True,
        )
        return res.modified_count > 0 or res.upserted_id is not None

    # --- Logging & Admin Utilities ---

    async def log_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Persists audit logs into MongoDB."""
        if self.db is None:
            return
        try:
            await self.db.logs.insert_one(
                {
                    "event_type": event_type,
                    "details": details,
                    "timestamp": datetime.utcnow(),
                }
            )
        except Exception as e:
            logger.error(f"Failed to log event: {e}")


# Singleton Database Instance
db = Database()
