"""
Search Plugin Module
Enforces search channel rules, force subscription checks, private message rules for normal users,
and renders search results with posters, metadata, and download/trailer links.
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from database import db
from utils.helpers import check_force_sub, format_movie_caption, get_force_sub_markup
from utils.shortlink import shortlink_service

logger = logging.getLogger("SearchPlugin")


# --- Private Chat Guard & Admin Commands Dispatcher ---
@Client.on_message(filters.private & ~filters.service)
async def private_chat_handler(client: Client, message: Message):
    """
    Private bot chat is restricted to admins only.
    If a normal user sends any text/movie name, reply informing them that search
    is available exclusively in the Search Channel.
    """
    user_id = message.from_user.id

    # Register user in DB
    await db.add_user(
        user_id=user_id,
        name=message.from_user.first_name,
        username=message.from_user.username,
    )

    # Check ban status
    if await db.is_user_banned(user_id):
        await message.reply_text("🚫 **You are banned from using this bot.**")
        return

    # Allow admins full private access (commands handled in plugins/admin.py)
    if user_id in Config.ADMINS:
        if message.text and message.text.startswith("/"):
            return  # Admin command will be processed by command handlers
        await message.reply_text("👋 **Welcome Admin!** Send /settings or /stats for management.")
        return

    # For non-admin users sending any text/movie query
    search_channel_link = Config.UPDATE_CHANNEL_LINK
    if Config.SEARCH_CHANNEL_ID:
        try:
            chat = await client.get_chat(Config.SEARCH_CHANNEL_ID)
            if chat.invite_link:
                search_channel_link = chat.invite_link
            elif chat.username:
                search_channel_link = f"https://t.me/{chat.username}"
        except Exception:
            pass

    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔍 Open Search Channel", url=search_channel_link
                )
            ]
        ]
    )

    await message.reply_text(
        "🔒 **Movie search is available only in our Search Channel.**\n\n"
        "Please join and search directly in our official search group/channel.",
        reply_markup=markup,
    )


# --- Search Channel Handler ---
@Client.on_message(filters.chat(Config.SEARCH_CHANNEL_ID) & filters.text & ~filters.service)
async def search_channel_handler(client: Client, message: Message):
    """
    Processes movie search queries submitted inside the designated Search Channel.
    Enforces Force Join requirements and smart fuzzy query lookup.
    """
    query = message.text.strip()

    # Ignore command calls or ultra-short messages
    if query.startswith("/") or len(query) < 2:
        return

    user_id = message.from_user.id if message.from_user else 0

    # Force Join Subscription Verification
    if user_id and not await check_force_sub(client, user_id):
        await message.reply_text(
            f"⚠️ **Hello {message.from_user.first_name}!**\n\n"
            "To search movies, you must join our Update Channel first.",
            reply_markup=get_force_sub_markup(),
        )
        return

    # Execute database smart search
    results = await db.search_movies(query=query, limit=5)

    if not results:
        # Save search query into requests system (with deduplication)
        if user_id:
            user_name = message.from_user.first_name if message.from_user else "User"
            user_username = message.from_user.username if message.from_user else None
            req_info = await db.add_or_update_request(query, user_id, user_name, user_username)

            # Notify Admin Log Channel about new or updated request
            if Config.LOG_CHANNEL_ID and req_info.get("is_new"):
                try:
                    await client.send_message(
                        chat_id=Config.LOG_CHANNEL_ID,
                        text=(
                            f"📥 **New Movie Request!**\n\n"
                            f"• **Movie:** `{query}`\n"
                            f"• **Requested By:** {user_name} (`{user_id}`)\n"
                            f"• **Total Requesters:** `{req_info.get('total_requested', 1)}`"
                        ),
                    )
                except Exception as e:
                    logger.error(f"Failed to send request log: {e}")

        btn_request = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📢 Check Updates Channel", url=Config.UPDATE_CHANNEL_LINK
                    )
                ]
            ]
        )
        await message.reply_text(
            f"❌ **Movie Not Found:** `{query}`\n\n"
            "Your request has been registered and sent to our team. "
            "You will be notified automatically when it gets uploaded!",
            reply_markup=btn_request,
        )
        return

    # Format and return primary matching movie result
    movie = results[0]
    caption = format_movie_caption(movie)

    # Shortlink processing for direct file download
    raw_file_link = f"https://t.me/c/{str(Config.STORAGE_CHANNEL_ID).replace('-100', '')}/{movie.get('file_id')}" if str(movie.get('file_id')).isdigit() else f"https://t.me/{movie.get('file_id')}"
    download_url = await shortlink_service.get_shortlink(raw_file_link)

    buttons = [
        [
            InlineKeyboardButton("📥 Download Movie", url=download_url),
            InlineKeyboardButton("🎬 Trailer", url=movie.get("trailer_url", "https://youtube.com")),
        ]
    ]

    # Add page switcher if multiple search results found
    if len(results) > 1:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"View More Results ({len(results)})", callback_data=f"src_more_{query[:15]}"
                )
            ]
        )

    markup = InlineKeyboardMarkup(buttons)
    poster_url = movie.get("poster_url") or movie.get("backdrop_url")

    if poster_url:
        try:
            await message.reply_photo(photo=poster_url, caption=caption, reply_markup=markup)
            return
        except Exception as e:
            logger.warning(f"Failed to send poster photo: {e}. Falling back to text message.")

    await message.reply_text(text=caption, reply_markup=markup)


# --- More Search Results Callback Handler ---
@Client.on_callback_query(filters.regex(r"^src_more_(.+)$"))
async def search_more_callback(client: Client, cb: CallbackQuery):
    query = cb.matches[0].group(1)
    results = await db.search_movies(query=query, limit=10)

    if not results:
        await cb.answer("No additional results found.", show_alert=True)
        return

    text = f"🔎 **More Results for:** `{query}`\n\n"
    buttons = []

    for idx, m in enumerate(results, 1):
        m_title = m.get("title")
        m_year = m.get("year", "")
        text += f"{idx}. **{m_title}** ({m_year}) - ⭐ {m.get('rating')}\n"
        
        # Link to direct download
        raw_link = f"https://t.me/c/{str(Config.STORAGE_CHANNEL_ID).replace('-100', '')}/{m.get('file_id')}" if str(m.get('file_id')).isdigit() else f"https://t.me/{m.get('file_id')}"
        dl_url = await shortlink_service.get_shortlink(raw_link)
        buttons.append([InlineKeyboardButton(f"📥 {m_title[:20]} ({m_year})", url=dl_url)])

    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await cb.answer()
