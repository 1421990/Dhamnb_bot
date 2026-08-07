"""
Async TMDB (The Movie Database) API Client
Handles searching for movies/TV shows, extracting metadata, posters, backdrops,
and formatting structured information for MongoDB storage and display.
"""

import logging
from typing import Any, Dict, Optional
import aiohttp

from config import Config

logger = logging.getLogger("TMDBClient")


class TMDBClient:
    def __init__(self) -> None:
        self.api_key = Config.TMDB_API_KEY
        self.base_url = "https://api.themoviedb.org/3"
        self.image_base_url = "https://image.tmdb.org/t/p/w500"
        self.backdrop_base_url = "https://image.tmdb.org/t/p/w1280"

    async def search_movie(self, query: str, year: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Searches TMDB for a movie by title and optional year.
        Returns detailed metadata dictionary or None if not found.
        """
        if not self.api_key:
            logger.error("TMDB_API_KEY is not configured.")
            return None

        url = f"{self.base_url}/search/movie"
        params = {
            "api_key": self.api_key,
            "query": query,
            "include_adult": "false",
            "language": "en-US",
            "page": "1",
        }
        if year and year.isdigit():
            params["primary_release_year"] = year

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"TMDB search failed with status {response.status}")
                        return None

                    data = await response.json()
                    results = data.get("results", [])
                    if not results:
                        return None

                    # Pick top matching result
                    first_match = results[0]
                    return await self.get_movie_details(first_match["id"])
        except Exception as e:
            logger.error(f"Error fetching from TMDB: {e}")
            return None

    async def get_movie_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves complete movie details by TMDB ID, including runtime, genres, and trailer."""
        url = f"{self.base_url}/movie/{tmdb_id}"
        params = {
            "api_key": self.api_key,
            "append_to_response": "videos",
            "language": "en-US",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status != 200:
                        return None

                    data = await response.json()

                    # Format release year
                    release_date = data.get("release_date", "")
                    year = release_date.split("-")[0] if release_date else "N/A"

                    # Format genres
                    genres = [g["name"] for g in data.get("genres", [])]
                    genre_str = ", ".join(genres) if genres else "Action, Drama"

                    # Format runtime
                    runtime = data.get("runtime", 0)
                    runtime_str = f"{runtime} min" if runtime else "N/A"

                    # Extract primary YouTube trailer key if available
                    trailer_url = None
                    videos = data.get("videos", {}).get("results", [])
                    for video in videos:
                        if video.get("site") == "YouTube" and video.get("type") in ["Trailer", "Teaser"]:
                            trailer_url = f"https://www.youtube.com/watch?v={video.get('key')}"
                            break

                    poster_path = data.get("poster_path")
                    backdrop_path = data.get("backdrop_path")

                    return {
                        "tmdb_id": data.get("id"),
                        "title": data.get("title") or data.get("original_title"),
                        "year": year,
                        "rating": str(round(data.get("vote_average", 0.0), 1)),
                        "genres": genre_str,
                        "language": (data.get("original_language") or "en").upper(),
                        "runtime": runtime_str,
                        "overview": data.get("overview", "No description available."),
                        "poster_url": f"{self.image_base_url}{poster_path}" if poster_path else None,
                        "backdrop_url": f"{self.backdrop_base_url}{backdrop_path}" if backdrop_path else None,
                        "trailer_url": trailer_url or "https://www.youtube.com",
                    }
        except Exception as e:
            logger.error(f"Error fetching TMDB details for ID {tmdb_id}: {e}")
            return None


# Singleton TMDB Client instance
tmdb_client = TMDBClient()
