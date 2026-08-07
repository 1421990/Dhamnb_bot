"""
Shortlink Integration Utility
Generates shortened download links using configured API endpoints (e.g. Shareus, Shortur)
when the shortlink feature is globally enabled in settings.
"""

import logging
from typing import Optional
import aiohttp

from config import Config
from database import db

logger = logging.getLogger("ShortlinkUtil")


class ShortlinkService:
    @staticmethod
    async def get_shortlink(destination_url: str) -> str:
        """
        Converts a direct Telegram file link into a shortened link if enabled in settings.
        If shortlink is disabled or the request fails, returns the original destination URL.
        """
        # Check global database settings
        settings = await db.get_settings()
        is_enabled = settings.get("shortlink_enabled", False)

        if not is_enabled:
            return destination_url

        if not Config.SHORTLINK_URL or not Config.SHORTLINK_API:
            logger.warning("Shortlink feature is enabled in settings, but SHORTLINK_URL or SHORTLINK_API is missing.")
            return destination_url

        # Format URL template
        # Standard formats: https://{SHORTLINK_URL}/api?api={SHORTLINK_API}&url={destination_url}
        api_endpoint = f"https://{Config.SHORTLINK_URL}/api"
        params = {
            "api": Config.SHORTLINK_API,
            "url": destination_url,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_endpoint, params=params, timeout=8) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Support standard shortener response keys (shortenedUrl, url, or shortlink)
                        if isinstance(data, dict):
                            short_url = data.get("shortenedUrl") or data.get("url") or data.get("shortlink")
                            if short_url:
                                return short_url
                    logger.error(f"Shortlink API returned non-200 or unexpected format: {response.status}")
        except Exception as e:
            logger.error(f"Failed to generate shortlink via {Config.SHORTLINK_URL}: {e}")

        # Fallback to direct link on error
        return destination_url


# Singleton instance
shortlink_service = ShortlinkService()
