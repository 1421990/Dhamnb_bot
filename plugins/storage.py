"""
Storage Channel Auto Detect & Auto Post Plugin
Monitors the Storage Channel for uploaded media files, parses filenames, fetches TMDB details,
generates dynamic banner poster artwork, saves metadata into MongoDB Atlas, auto-posts to the
Movie Channel, and notifies users with pending requests.
"""

import os
import logging
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from database import db
from poster.generator import poster_generator
from utils.helpers import clean_filename, format_movie_caption
from utils.shortlink import shortlink_service
from utils.tmdb import tmdb_client

logger = logging.getLogger("StoragePlugin")


@Client.on_message(filters.chat(Config.STORAGE_CHANNEL_ID) & (filters.document | filters.video))
async def storage_channel_auto_detect(client: Client, message: Message):
    """
    Automatically detects uploaded media in the Storage Channel.
    Parses filename -> Searches TMDB -> Generates Poster Banner -> Stores in MongoDB
    -> Notifies Requesting Users -> Auto-Posts to Main Movie Channel.
    """
    media = message.document or message.video
    if not media or not media.file_name:
        logger.warning("Uploaded storage message lacks a valid file_name.")
        return

    raw_filename = media.file_name
    file_id = message.id  # Store storage channel message sequence ID as reference

    logger.info(f"Auto-detected media upload in Storage Channel: {raw_filename}")

    # 1. Clean filename and extract search title & year
    extracted_title, extracted_year = clean_filename(raw_filename)
    logger.info(f"Parsed Filename: Title='{extracted_title}', Year='{extracted_year}'")

    # 2. Fetch metadata from TMDB API
    tmdb_data = await tmdb_client.search_movie(query=extracted_title, year=extracted_year)
    if not tmdb_data:
        # Fallback to searching without year constraint
        tmdb_data = await tmdb_client.search_movie(query=extracted_title)

    if not tmdb_data:
        logger.warning(f"Could not automatically resolve TMDB info for '{extracted_title}'")
        if Config.LOG_CHANNEL_ID:
            await client.send_message(
                chat_id=Config.LOG_CHANNEL_ID,
                text=f"⚠️ **TMDB Auto-Detect Failed**\nFile: `{raw_filename}`\nParsed Query: `{extracted_title}`",
            )
        return

    # 3. Build unified movie object for MongoDB
    movie_data = {
        "title": tmdb_data["title"],
        "year": tmdb_data["year"],
        "rating": tmdb_data["rating"],
        "genres": tmdb_data["genres"],
        "language": tmdb_data["language"],
        "runtime": tmdb_data["runtime"],
        "overview": tmdb_data["overview"],
        "poster_url": tmdb_data["poster_url"],
        "backdrop_url": tmdb_data["backdrop_url"],
        "trailer_url": tmdb_data["trailer_url"],
        "file_id": str(file_id),
        "tmdb_id": tmdb_data["tmdb_id"],
        "aliases": [
            extracted_title.lower(),
            tmdb_data["title"].lower(),
            raw_filename.lower(),
        ],
    }

    # 4. Save into MongoDB database
    saved = await db.add_movie(movie_data)
    if not saved:
        logger.error(f"Failed to persist movie metadata for {tmdb_data['title']}")
        return

    logger.info(f"Movie successfully indexed into database: {tmdb_data['title']} ({tmdb_data['year']})")

    # 5. Fetch system settings
    settings = await db.get_settings()
    custom_logo = settings.get("custom_logo_text", "MOVIE BOT")
    auto_post_enabled = settings.get("auto_post_enabled", True)

    # 6. Generate Pillow Banner Image
    banner_buffer = await poster_generator.create_poster(
        backdrop_url=tmdb_data["backdrop_url"],
        poster_url=tmdb_data["poster_url"],
        title=tmdb_data["title"],
        year=tmdb_data["year"],
        rating=tmdb_data["rating"],
        genres=tmdb_data["genres"],
        language=tmdb_data["language"],
        runtime=tmdb_data["runtime"],
        logo_text=custom_logo,
    )

    caption_text = format_movie_caption(movie_data)

    # Build direct link and pass through shortlink transformer
    raw_storage_link = f"https://t.me/c/{str(Config.STORAGE_CHANNEL_ID).replace('-100', '')}/{file_id}"
    shortened_dl_link = await shortlink_service.get_shortlink(raw_storage_link)

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📥 Direct Download", url=shortened_dl_link),
                InlineKeyboardButton("🎬 Watch Trailer", url=tmdb_data["trailer_url"]),
            ]
        ]
    )

    # 7. Auto-Publish to Movie Channel if enabled
    if auto_post_enabled and Config.MOVIE_CHANNEL_ID:
        try:
            banner_buffer.seek(0)
            await client.send_photo(
                chat_id=Config.MOVIE_CHANNEL_ID,
                photo=banner_buffer,
                caption=caption_text,
                reply_markup=buttons,
            )
            logger.info(f"Auto-published movie post to Movie Channel: {tmdb_data['title']}")
        except Exception as e:
            logger.error(f"Failed to auto-post to Movie Channel: {e}")

    # 8. Send Owner / Admin Log Notification
    if Config.LOG_CHANNEL_ID:
        try:
            banner_buffer.seek(0)
            await client.send_photo(
                chat_id=Config.LOG_CHANNEL_ID,
                photo=banner_buffer,
                caption=f"✅ **Auto-Detected & Saved Movie!**\n\n{caption_text}",
            )
        except Exception as e:
            logger.error(f"Failed to send log notification: {e}")

    # 9. Notify Users who requested this movie (Deduplicated Request Fulfillment)
    affected_user_ids = await db.fulfill_and_get_requested_users(tmdb_data["title"])
    if affected_user_ids:
        logger.info(f"Notifying {len(affected_user_ids)} users about requested movie release: {tmdb_data['title']}")
        notify_text = (
            f"🎉 **Your Movie Request is Ready!**\n\n"
            f"🎬 **{tmdb_data['title']} ({tmdb_data['year']})** has just been uploaded!"
        )
        for u_id in affected_user_ids:
            try:
                banner_buffer.seek(0)
                await client.send_photo(
                    chat_id=u_id,
                    photo=banner_buffer,
                    caption=notify_text,
                    reply_markup=buttons,
                )
            except Exception as e:
                logger.warning(f"Could not notify user {u_id}: {e}")
