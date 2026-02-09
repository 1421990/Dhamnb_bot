import os, time
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image, ImageDraw, ImageFont
import motor.motor_asyncio

# ================= CONFIG =================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
UPI_ID = os.getenv("UPI_ID")

DAILY_LIMIT = 2
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# ================= BOT =================
app = Client(
    "poster_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

mongo = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo.bot
users = db.users
usage = db.daily_usage
states = db.states
payments = db.payments
spam = db.spam

# ================= HELPERS =================
def today():
    return datetime.utcnow().strftime("%Y-%m-%d")

def is_admin(uid):
    return uid == ADMIN_ID

async def is_joined(client, uid):
    try:
        m = await client.get_chat_member(FORCE_CHANNEL, uid)
        return m.status in ["member", "administrator", "owner"]
    except:
        return False

async def anti_spam(uid):
    now = int(time.time())
    data = await spam.find_one({"user_id": uid})
    if not data:
        await spam.insert_one({"user_id": uid, "last": now, "warn": 0})
        return True
    if now - data["last"] < 5:
        warn = data["warn"] + 1
        await spam.update_one({"user_id": uid}, {"$set": {"last": now, "warn": warn}})
        if warn >= 3:
            await users.update_one({"user_id": uid}, {"$set": {"status": "blocked"}})
        return False
    await spam.update_one({"user_id": uid}, {"$set": {"last": now, "warn": 0}})
    return True

def generate_poster(bg, text, out):
    img = Image.open(bg).convert("RGBA")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # gradient
    for i in range(300):
        draw.rectangle([(0, h-i), (w, h)], fill=(0, 0, 0, int(i*0.7)))

    font = ImageFont.truetype("arial.ttf", 70)
    tw, th = draw.textsize(text, font)
    x = (w - tw) // 2
    y = h - th - 80

    draw.text((x+3, y+3), text, font=font, fill="black")
    draw.text((x, y), text, font=font, fill="white")

    img.convert("RGB").save(out, quality=95)

# ================= START =================
@app.on_message(filters.command("start"))
async def start(client, m):
    await m.reply_photo(
        "start.jpg",
        caption=
        "🎬 AUTO POSTER BOT\n\n"
        "🆓 Free: 2 Posters / Day\n"
        "📢 Channel join required\n\n"
        "💰 Unlimited chahiye? /upgrade",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Add MongoDB", callback_data="addmongo")],
                [InlineKeyboardButton("🖼 Poster Mode", callback_data="poster")],
                [
                    InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_CHANNEL.replace('@','')}"),
                    InlineKeyboardButton("📩 Admin", url=f"https://t.me/{ADMIN_ID}")
                ]
            ]
        )
    )

# ================= ADD MONGODB =================
@app.on_callback_query(filters.regex("addmongo"))
async def ask_mongo(client, q):
    await q.message.reply_text("🗄 MongoDB URI bhejo")

@app.on_message(filters.text & filters.private)
async def text_handler(client, m):
    if not await anti_spam(m.from_user.id):
        return

    state = await states.find_one({"user_id": m.from_user.id})

    # MongoDB add
    if m.text.startswith("mongodb"):
        await users.update_one(
            {"user_id": m.from_user.id},
            {"$set": {"license": "self", "status": "active"}},
            upsert=True
        )
        return await m.reply_text("✅ MongoDB added. Free plan active (2/day)")

    # Poster text step
    if state and state.get("step") == "text":
        bg = state["bg"]
        out = f"{TEMP_DIR}/{m.from_user.id}_final.jpg"
        generate_poster(bg, m.text, out)
        await m.reply_photo(out, caption="📤 Poster Ready")

        await usage.update_one(
            {"user_id": m.from_user.id, "date": today()},
            {"$inc": {"count": 1}},
            upsert=True
        )
        await states.delete_one({"user_id": m.from_user.id})
        os.remove(bg)
        os.remove(out)

# ================= POSTER IMAGE =================
@app.on_message(filters.photo & filters.private)
async def poster_img(client, m):
    uid = m.from_user.id
    user = await users.find_one({"user_id": uid})
    if not user:
        return await m.reply_text("❌ License nahi hai. /start")

    if user.get("license") == "self":
        if not await is_joined(client, uid):
            return await m.reply_text("❌ Pehle channel join karo")

        u = await usage.find_one({"user_id": uid, "date": today()})
        if u and u.get("count", 0) >= DAILY_LIMIT:
            return await m.reply_text("❌ Daily limit reached (2/2)")

    path = await m.download(f"{TEMP_DIR}/{uid}_bg.jpg")
    await states.update_one(
        {"user_id": uid},
        {"$set": {"step": "text", "bg": path}},
        upsert=True
    )
    await m.reply_text("📝 Ab movie name bhejo")

# ================= UPGRADE =================
@app.on_message(filters.command("upgrade"))
async def upgrade(client, m):
    await m.reply_photo(
        "upi_qr.png",
        caption=
        f"💰 PREMIUM\n₹99 Lifetime\n\nUPI: {UPI_ID}\n\n"
        "Payment ke baad:\n/utr <UTR>"
    )

@app.on_message(filters.command("utr"))
async def utr(client, m):
    try:
        utr = m.text.split()[1]
    except:
        return await m.reply_text("Use: /utr 123456789")

    await payments.insert_one({
        "user_id": m.from_user.id,
        "utr": utr,
        "status": "pending",
        "date": today()
    })
    await app.send_message(
        ADMIN_ID,
        f"💰 Payment request\nUser: {m.from_user.id}\nUTR: {utr}\n/approve {m.from_user.id}"
    )
    await m.reply_text("✅ UTR received, admin verify karega")

# ================= APPROVE =================
@app.on_message(filters.command("approve"))
async def approve(client, m):
    if not is_admin(m.from_user.id):
        return
    uid = int(m.text.split()[1])
    await users.update_one(
        {"user_id": uid},
        {"$set": {"license": "paid", "status": "active"}},
        upsert=True
    )
    await m.reply_text("✅ User approved (UNLIMITED)")

# ================= RUN =================
print("Bot started...")
app.run()
