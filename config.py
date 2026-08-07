"""
Configuration Management Module
Loads environment variables and sets defaults for the Telegram Movie Management Bot.
"""

import os
from typing import List, Union


class Config:
    # --- Telegram API Configuration ---
    API_ID: int = int(os.getenv("API_ID", "0"))
    API_HASH: str = os.getenv("API_HASH", "")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # --- Admin & Authorization ---
    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
    ADMINS: List[int] = [
        int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip().isdigit()
    ]
    if OWNER_ID and OWNER_ID not in ADMINS:
        ADMINS.append(OWNER_ID)

    # --- Channels & Groups ---
    SEARCH_CHANNEL_ID: int = int(os.getenv("SEARCH_CHANNEL_ID", "0"))
    UPDATE_CHANNEL_ID: int = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
    UPDATE_CHANNEL_LINK: str = os.getenv("UPDATE_CHANNEL_LINK", "https://t.me/")
    STORAGE_CHANNEL_ID: int = int(os.getenv("STORAGE_CHANNEL_ID", "0"))
    MOVIE_CHANNEL_ID: int = int(os.getenv("MOVIE_CHANNEL_ID", "0"))
    LOG_CHANNEL_ID: int = int(os.getenv("LOG_CHANNEL_ID", "0"))

    # --- Database Configuration ---
    MONGODB_URI: str = os.getenv(
        "MONGODB_URI",
        "mongodb+srv://user:pass@cluster.mongodb.net/movie_db?retryWrites=true&w=majority",
    )
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "movie_management_db")

    # --- External APIs ---
    TMDB_API_KEY: str = os.getenv("TMDB_API_KEY", "")

    # --- Shortener Settings ---
    SHORTLINK_URL: str = os.getenv("SHORTLINK_URL", "")  # e.g. api.shareus.io
    SHORTLINK_API: str = os.getenv("SHORTLINK_API", "")

    # --- Server Settings (Render.com compatibility) ---
    PORT: int = int(os.getenv("PORT", "8080"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    @classmethod
    def validate(cls) -> None:
        """Validates critical configuration parameters on startup."""
        missing = []
        if not cls.API_ID:
            missing.append("API_ID")
        if not cls.API_HASH:
            missing.append("API_HASH")
        if not cls.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not cls.OWNER_ID:
            missing.append("OWNER_ID")
        if not cls.MONGODB_URI:
            missing.append("MONGODB_URI")
        if not cls.TMDB_API_KEY:
            missing.append("TMDB_API_KEY")

        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


# Instantiate and validate configuration
Config.validate()
