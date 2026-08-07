"""
Admin Commands Plugin Module
Contains management handlers for administrators:
- /add, /del, /pratap1 (movie management & pagination)
- /pratap2 on / off (toggle shortlink feature)
- /stats, /settings, /broadcast, /notify
- /ban, /unban, /logs, /backup, /restore
"""

import io
import json
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from database import db
from utils.helpers import format_movie_caption
from utils.tmdb import tmdb_client

logger = logging.getLogger("AdminPlugin")

# Custom authorization filter
async def admin_filter(_, __, message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in Config.ADMINS)

is_admin = filters.create(admin_filter)


# --- /add Command ---
@Client.on_message(filters.command("add") & is_admin & filters.private)
async def add_movie_command(client: Client, message: Message):
    """
    Manual Movie Add:
    Usage: /add <Movie Name> | <File ID / Link>
    """
    args = message.text.split(" ", 1)
    if len(args) < 2 or "|" not in args[1]:
        await message.reply_text(
            "⚠️ **Usage Format:**\n`/add <Movie Title> | <File_ID or TG_Message_Link>`\n\n"
            "Example:\n`/add Inception 2010 | BQACAgUAAxkBAAI...`"
        )
        return

    parts = args[1].split("|")
    title_query = parts[0].strip()
    file_id = parts[1].strip()

    status_msg = await message.reply_text(f"🔍 Searching TMDB for **{title_query}**...")

    tmdb_data = await tmdb_client.search_movie(title_query)
    if not tmdb_data:
        await status_msg.edit_text(f"❌ Could not find TMDB info for: **{title_query}**")
        return

    movie_record = {
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
        "file_id": file_id,
        "tmdb_id": tmdb_data["tmdb_id"],
        "aliases": [title_query.lower(), tmdb_data["title"].lower()],
    }

    success = await db.add_movie(movie_record)
    if success:
        await status_msg.edit_text(
            f"✅ **Movie Added Successfully!**\n\n"
            f"🎬 **Title:** {tmdb_data['title']} ({tmdb_data['year']})\n"
            f"⭐ **Rating:** {tmdb_data['rating']}/10\n"
            f"📂 **File ID:** `{file_id}`"
        )
    else:
        await status_msg.edit_text("❌ Failed to save movie to database.")


# --- /del Command ---
@Client.on_message(filters.command("del") & is_admin & filters.private)
async def delete_movie_command(client: Client, message: Message):
    """Usage: /del <Movie_ID or Exact Title>"""
    args = message.text.split(" ", 1)
    if len(args) < 2:
        await message.reply_text("⚠️ Usage: `/del <Movie_ID or Movie Title>`")
        return

    query = args[1].strip()
    # Search for movie first
    results = await db.search_movies(query, limit=1)
    if not results:
        await message.reply_text(f"❌ No movie found matching: **{query}**")
        return

    target = results[0]
    movie_id = str(target["_id"])
    deleted = await db.delete_movie(movie_id)

    if deleted:
        await message.reply_text(f"🗑️ Deleted movie: **{target.get('title')}** ({target.get('year')})")
    else:
        await message.reply_text("❌ Failed to delete movie.")


# --- /pratap1 (Paginated Movie Catalog & Search) ---
@Client.on_message(filters.command("pratap1") & is_admin & filters.private)
async def catalog_pagination_command(client: Client, message: Message):
    """Displays movie database with pagination."""
    await render_catalog_page(message, page=1)


async def render_catalog_page(message_or_cb: Message | CallbackQuery, page: int = 1):
    limit = 5
    offset = (page - 1) * limit

    total_movies = await db.get_total_movies_count()
    movies = await db.search_movies(query="", limit=limit, offset=offset)

    if not movies and total_movies > 0:
        movies = await db.search_movies(query="", limit=limit, offset=0)
        page = 1

    text = f"⚙️ **Admin Movie Management**\nTotal Movies: `{total_movies}`\nPage: `{page}`\n\n"
    buttons = []

    for m in movies:
        m_id = str(m["_id"])
        m_title = m.get("title", "Unknown")
        m_year = m.get("year", "N/A")
        text += f"• **{m_title}** ({m_year})\n  ID: `{m_id}`\n"
        buttons.append([
            InlineKeyboardButton(f"🗑️ Delete {m_title[:15]}", callback_data=f"adm_del_{m_id}_{page}")
        ])

    # Navigation buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"adm_page_{page-1}"))
    if offset + limit < total_movies:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_page_{page+1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    markup = InlineKeyboardMarkup(buttons)

    if isinstance(message_or_cb, CallbackQuery):
        await message_or_cb.message.edit_text(text, reply_markup=markup)
    else:
        await message_or_cb.reply_text(text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^adm_page_(\d+)$") & is_admin)
async def catalog_page_callback(client: Client, cb: CallbackQuery):
    page = int(cb.matches[0].group(1))
    await render_catalog_page(cb, page=page)
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^adm_del_(.+)_(\d+)$") & is_admin)
async def catalog_delete_callback(client: Client, cb: CallbackQuery):
    m_id = cb.matches[0].group(1)
    page = int(cb.matches[0].group(2))

    await db.delete_movie(m_id)
    await cb.answer("Movie deleted!", show_alert=True)
    await render_catalog_page(cb, page=page)


# --- /pratap2 (Shortlink Toggle) ---
@Client.on_message(filters.command("pratap2") & is_admin & filters.private)
async def toggle_shortlink_command(client: Client, message: Message):
    """Usage: /pratap2 on  OR  /pratap2 off"""
    args = message.text.split(" ", 1)
    if len(args) < 2 or args[1].lower() not in ["on", "off"]:
        settings = await db.get_settings()
        status = "ON 🟢" if settings.get("shortlink_enabled") else "OFF 🔴"
        await message.reply_text(
            f"ℹ️ **Shortlink Status:** {status}\n\n"
            "Usage:\n`/pratap2 on` - Enable shortlink\n`/pratap2 off` - Disable shortlink"
        )
        return

    enable = args[1].lower() == "on"
    await db.update_setting("shortlink_enabled", enable)
    state_str = "ENABLED 🟢" if enable else "DISABLED 🔴"
    await message.reply_text(f"✅ Shortlink conversion is now **{state_str}**.")


# --- /stats Command ---
@Client.on_message(filters.command("stats") & is_admin & filters.private)
async def stats_command(client: Client, message: Message):
    total_movies = await db.get_total_movies_count()
    total_users = await db.get_total_users_count()
    total_requests = await db.get_total_requests_count()

    stats_text = (
        "📊 **System Statistics**\n\n"
        f"🎬 **Total Movies:** `{total_movies}`\n"
        f"👤 **Total Registered Users:** `{total_users}`\n"
        f"📩 **Pending Requests:** `{total_requests}`\n"
        f"⏰ **Server Time:** `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}`"
    )
    await message.reply_text(stats_text)


# --- /settings Command ---
@Client.on_message(filters.command("settings") & is_admin & filters.private)
async def settings_command(client: Client, message: Message):
    settings = await db.get_settings()
    sl_status = "ENABLED 🟢" if settings.get("shortlink_enabled") else "DISABLED 🔴"
    ap_status = "ENABLED 🟢" if settings.get("auto_post_enabled") else "DISABLED 🔴"
    logo_txt = settings.get("custom_logo_text", "MOVIE BOT")

    text = (
        "⚙️ **Bot Control Settings**\n\n"
        f"• **Shortlink System:** {sl_status}\n"
        f"• **Auto Channel Post:** {ap_status}\n"
        f"• **Poster Custom Title Logo:** `{logo_txt}`"
    )

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Toggle Auto Post", callback_data="toggle_setting_auto_post_enabled"
            )
        ]
    ])
    await message.reply_text(text, reply_markup=buttons)


@Client.on_callback_query(filters.regex(r"^toggle_setting_(.+)$") & is_admin)
async def toggle_setting_callback(client: Client, cb: CallbackQuery):
    key = cb.matches[0].group(1)
    settings = await db.get_settings()
    current_val = settings.get(key, False)
    await db.update_setting(key, not current_val)
    await cb.answer("Setting updated!")
    await settings_command(client, cb.message)


# --- /broadcast Command ---
@Client.on_message(filters.command("broadcast") & is_admin & filters.private)
async def broadcast_command(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply_text("⚠️ Reply to a message to broadcast it to all registered users.")
        return

    users = await db.get_all_user_ids()
    status_msg = await message.reply_text(f"🚀 Broadcasting to `{len(users)}` users...")

    success = 0
    failed = 0

    for u_id in users:
        try:
            await message.reply_to_message.copy(chat_id=u_id)
            success += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"• **Successful:** `{success}`\n"
        f"• **Failed/Blocked:** `{failed}`"
    )


# --- /notify Command ---
@Client.on_message(filters.command("notify") & is_admin & filters.private)
async def notify_user_command(client: Client, message: Message):
    """Usage: /notify <User_ID> <Text Message>"""
    args = message.text.split(" ", 2)
    if len(args) < 3:
        await message.reply_text("⚠️ Usage: `/notify <User_ID> <Message>`")
        return

    target_user_id = int(args[1]) if args[1].isdigit() else 0
    msg_text = args[2]

    try:
        await client.send_message(chat_id=target_user_id, text=f"🔔 **Notification from Admin:**\n\n{msg_text}")
        await message.reply_text(f"✅ Notification sent to user `{target_user_id}`.")
    except Exception as e:
        await message.reply_text(f"❌ Failed to notify user: {e}")


# --- /ban & /unban Commands ---
@Client.on_message(filters.command("ban") & is_admin & filters.private)
async def ban_user_command(client: Client, message: Message):
    args = message.text.split(" ", 1)
    if len(args) < 2 or not args[1].isdigit():
        await message.reply_text("⚠️ Usage: `/ban <User_ID>`")
        return

    u_id = int(args[1])
    await db.set_user_ban(u_id, True)
    await message.reply_text(f"🚫 User `{u_id}` has been banned.")


@Client.on_message(filters.command("unban") & is_admin & filters.private)
async def unban_user_command(client: Client, message: Message):
    args = message.text.split(" ", 1)
    if len(args) < 2 or not args[1].isdigit():
        await message.reply_text("⚠️ Usage: `/unban <User_ID>`")
        return

    u_id = int(args[1])
    await db.set_user_ban(u_id, False)
    await message.reply_text(f"✅ User `{u_id}` has been unbanned.")


# --- /logs Command ---
@Client.on_message(filters.command("logs") & is_admin & filters.private)
async def get_logs_command(client: Client, message: Message):
    """Sends log summary or log database extract."""
    logs = await db.db.logs.find({}).sort("timestamp", -1).limit(20).to_list(length=20)
    if not logs:
        await message.reply_text("📝 No activity logs recorded yet.")
        return

    log_text = "📝 **Recent System Audit Logs:**\n\n"
    for l in logs:
        ts = l.get("timestamp", "").strftime("%H:%M:%S") if isinstance(l.get("timestamp"), datetime) else ""
        log_text += f"• `[{ts}]` **{l.get('event_type')}**: {json.dumps(l.get('details', {}))}\n"

    await message.reply_text(log_text[:4000])


# --- /backup & /restore Commands ---
@Client.on_message(filters.command("backup") & is_admin & filters.private)
async def backup_command(client: Client, message: Message):
    """Exports movies database collection to JSON document."""
    movies = await db.db.movies.find({}).to_list(length=None)
    for m in movies:
        m["_id"] = str(m["_id"])
        if isinstance(m.get("created_at"), datetime):
            m["created_at"] = m["created_at"].isoformat()
        if isinstance(m.get("updated_at"), datetime):
            m["updated_at"] = m["updated_at"].isoformat()

    json_data = json.dumps(movies, indent=2)
    bio = io.BytesIO(json_data.encode("utf-8"))
    bio.name = f"movie_db_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

    await message.reply_document(document=bio, caption="📦 **MongoDB Movies Backup**")


@Client.on_message(filters.command("restore") & is_admin & filters.private)
async def restore_command(client: Client, message: Message):
    """Restores database from uploaded backup JSON file."""
    if not message.reply_to_message or not message.reply_to_message.document:
        await message.reply_text("⚠️ Reply to a valid backup `.json` file with `/restore`.")
        return

    doc_msg = message.reply_to_message
    if not doc_msg.document.file_name.endswith(".json"):
        await message.reply_text("❌ File must be JSON format.")
        return

    file_path = await client.download_media(doc_msg)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        restored_count = 0
        for item in data:
            if "file_id" in item and "title" in item:
                if "_id" in item:
                    del item["_id"]
                await db.add_movie(item)
                restored_count += 1

        await message.reply_text(f"✅ **Database Restored!** Imported `{restored_count}` records.")
    except Exception as e:
        await message.reply_text(f"❌ Failed to restore database: {e}")
