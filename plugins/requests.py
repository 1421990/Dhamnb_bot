"""
Requests Management Plugin
Allows administrators to view, clear, or manage user-submitted movie requests.
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from database import db

logger = logging.getLogger("RequestsPlugin")

# Admin authorization filter
async def admin_filter(_, __, message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in Config.ADMINS)

is_admin = filters.create(admin_filter)


@Client.on_message(filters.command("requests") & is_admin & filters.private)
async def view_requests_command(client: Client, message: Message):
    """
    Displays pending movie requests submitted by users.
    Usage: /requests
    """
    if db.db is None:
        await message.reply_text("❌ Database connection unavailable.")
        return

    # Fetch top pending requests
    pending = await db.db.requests.find({"status": "pending"}).sort("created_at", -1).limit(15).to_list(length=15)

    if not pending:
        await message.reply_text("✨ **No pending movie requests!**")
        return

    text = f"📩 **Pending Movie Requests ({len(pending)}):**\n\n"
    for idx, req in enumerate(pending, 1):
        q_text = req.get("query", "Unknown")
        user_list = req.get("users", [])
        requesters_count = len(user_list)
        last_requested_by = user_list[-1]["name"] if user_list else "Anonymous"
        
        text += f"{idx}. **{q_text}**\n   • Requesters: `{requesters_count}` (Latest by: {last_requested_by})\n"

    await message.reply_text(text[:4000])


@Client.on_message(filters.command("clearrequests") & is_admin & filters.private)
async def clear_requests_command(client: Client, message: Message):
    """
    Clears all fulfilled or pending requests.
    Usage: /clearrequests
    """
    if db.db is None:
        await message.reply_text("❌ Database connection unavailable.")
        return

    res = await db.db.requests.delete_many({"status": "fulfilled"})
    await message.reply_text(f"🧹 Cleared `{res.deleted_count}` fulfilled movie requests from database.")
