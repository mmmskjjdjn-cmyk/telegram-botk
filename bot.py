from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackQueryHandler, CommandHandler, ContextTypes, filters
import sqlite3, asyncio, time

TOKEN = "YOUR_TOKEN"
ADMIN_ID = 123456789

# ================= DB =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS banned (id INTEGER)")
conn.commit()

# ================= DATA =================
likes = {}
liked_users = {}
post_owner = {}
user_channel = {}
contest_on = {}
contest_posts = {}
user_sent = {}

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.message.from_user
    cur.execute("INSERT OR IGNORE INTO users VALUES (?,?)", (u.id, u.username))
    conn.commit()

    kb = [[InlineKeyboardButton("⚙️ التحكم", callback_data="menu")]]
    await update.message.reply_text("🔥 بوت مسابقات خارق", reply_markup=InlineKeyboardMarkup(kb))

# ================= HANDLE =================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.message.from_user
    uid = u.id

    # banned
    cur.execute("SELECT * FROM banned WHERE id=?", (uid,))
    if cur.fetchone():
        return

    if not u.username:
        await update.message.reply_text("❌ حط يوزرنيم")
        return

    # ربط قناة
    if context.user_data.get("wait"):
        user_channel[uid] = update.message.text
        context.user_data["wait"] = False
        await update.message.reply_text("✅ تم الربط")
        return

    if not contest_on.get(uid):
        return

    if user_sent.get(uid):
        await update.message.reply_text("❌ أرسلت مسبقاً")
        return

    ch = user_channel.get(uid)
    if not ch:
        await update.message.reply_text("❌ اربط قناة")
        return

    user_sent[uid] = True

    kb = [[InlineKeyboardButton("👍 0", callback_data="like")]]

    if update.message.photo:
        msg = await context.bot.send_photo(
            chat_id=ch,
            photo=update.message.photo[-1].file_id,
            caption=f"https://t.me/{u.username}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        msg = await context.bot.send_message(
            chat_id=ch,
            text=f"https://t.me/{u.username}\n\n{update.message.text}",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    mid = msg.message_id
    likes[mid] = 0
    liked_users[mid] = set()
    post_owner[mid] = uid
    contest_posts.setdefault(uid, []).append(mid)

# ================= LIKE =================
async def like(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    mid = q.message.message_id
    await q.answer()

    if mid not in likes:
        return

    if post_owner[mid] == uid:
        await q.answer("❌ لنفسك؟!", show_alert=True)
        return

    ch = q.message.chat.username
    member = await context.bot.get_chat_member(f"@{ch}", uid)
    if member.status in ["left", "kicked"]:
        await q.answer("❌ اشترك أولاً", show_alert=True)
        return

    if uid in liked_users[mid]:
        await q.answer("❌ مرة وحدة", show_alert=True)
        return

    liked_users[mid].add(uid)
    likes[mid] += 1

    kb = [[InlineKeyboardButton(f"👍 {likes[mid]}", callback_data="like")]]
    await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(kb))

# ================= BUTTONS =================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if q.data == "menu":
        kb = [
            [InlineKeyboardButton("🔗 ربط قناة", callback_data="set")],
            [InlineKeyboardButton("❌ فصل قناة", callback_data="del")],
            [InlineKeyboardButton("▶️ بدء", callback_data="start")],
            [InlineKeyboardButton("⛔ إيقاف", callback_data="stop")]
        ]
        if uid == ADMIN_ID:
            kb.append([InlineKeyboardButton("👑 أدمن", callback_data="admin")])

        await q.message.reply_text("⚙️ لوحة التحكم", reply_markup=InlineKeyboardMarkup(kb))

    elif q.data == "set":
        context.user_data["wait"] = True
        await q.message.reply_text("أرسل @القناة")

    elif q.data == "del":
        user_channel.pop(uid, None)
        await q.message.reply_text("تم الفصل")

    elif q.data == "start":
        contest_on[uid] = True
        contest_posts[uid] = []
        user_sent.clear()
        await q.message.reply_text("🚀 بدأت")

        asyncio.create_task(auto_end(context, uid, 120))

    elif q.data == "stop":
        await end(context, uid)

    elif q.data == "admin" and uid == ADMIN_ID:
        kb = [
            [InlineKeyboardButton("📊 إحصائيات", callback_data="stats")],
            [InlineKeyboardButton("🚫 حظر", callback_data="ban")]
        ]
        await q.message.reply_text("👑 لوحة الأدمن", reply_markup=InlineKeyboardMarkup(kb))

    elif q.data == "stats":
        cur.execute("SELECT COUNT(*) FROM users")
        count = cur.fetchone()[0]
        await q.message.reply_text(f"👥 المستخدمين: {count}")

    elif q.data == "ban":
        context.user_data["ban"] = True
        await q.message.reply_text("أرسل ID")

# ================= BAN =================
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("ban"):
        uid = int(update.message.text)
        cur.execute("INSERT INTO banned VALUES (?)", (uid,))
        conn.commit()
        context.user_data["ban"] = False
        await update.message.reply_text("🚫 تم الحظر")

# ================= END =================
async def auto_end(context, uid, sec):
    await asyncio.sleep(sec)
    await end(context, uid)

async def end(context, uid):
    posts = contest_posts.get(uid)
    if not posts:
        return

    win = max(posts, key=lambda x: likes.get(x, 0))
    owner = post_owner[win]
    l = likes[win]
    ch = user_channel[uid]

    await context.bot.send_message(ch, f"🏆 الفائز:\ntg://user?id={owner}\n🔥 {l} لايك")

    contest_on[uid] = False

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle))
    app.add_handler(MessageHandler(filters.TEXT, ban_user))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(CallbackQueryHandler(like, pattern="like"))

    app.run_polling()

if __name__ == "__main__":
    main()