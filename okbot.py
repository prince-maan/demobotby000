from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import datetime
import pytz
import os
from flask import Flask
from threading import Thread

# --- 1. KEEP-ALIVE SERVER ---
app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "Bot is active!"
def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
Thread(target=run_flask).start()

# --- 2. SETTINGS ---
TOKEN = '8760244596:AAHbZdwxz2e9Ddbvy0zfAi6B6aBrgsr65ig'
ADMIN_ID = 8895101534
BOT_USERNAME = "newaurVid_bot"
BUY_LINK = "https://t.me/SaulGoodmanOp"
IST = pytz.timezone('Asia/Kolkata')

# --- 3. DATABASE ---
user_membership = {}
files_db = {}
valid_codes = {}
all_users = {}
banned_users = set()

# --- 4. FUNCTIONS ---

async def start(update, context):
    user = update.message.from_user
    if user.id in banned_users: return
    all_users[user.id] = {'name': user.first_name}
    if context.args:
        key = context.args[0]
        if key in files_db:
            if user.id == ADMIN_ID or (user.id in user_membership and datetime.datetime.now(IST) < user_membership[user.id]['expiry']):
                for f in files_db[key]:
                    try: await context.bot.copy_message(chat_id=user.id, from_chat_id=f['chat_id'], message_id=f['message_id'], protect_content=True, caption=f.get('caption', ""))
                    except: continue
            else: await update.message.reply_text("😒 Membership inactive.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]]))
        else: await update.message.reply_text("❌ File not found.")
    else: await update.message.reply_text("🫡 Hi, I'm Heisenberg.\n\nTo watch videos, subscribe to a membership.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]]))

async def stats(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    now = datetime.datetime.now(IST)
    active_list = []
    for uid, d in user_membership.items():
        if now < d['expiry']:
            rem = d['expiry'] - now
            active_list.append(f"👤 {d['name']} | 🎫 {d['code']}\n📅 जॉइन: {d['join_date']}\n⏳ खत्म: {d['expiry'].strftime('%Y-%m-%d %H:%M')}")
    
    msg = f"📊 **STATISTICS**\n👥 कुल: {len(all_users)}\n✅ एक्टिव: {len(active_list)}\n🚫 बैन: {len(banned_users)}\n\n📋 **एक्टिव मेंबर्स:**\n" + "\n\n".join(active_list)
    await update.message.reply_text(msg)

async def broadcast(update, context):
    if update.message.from_user.id == ADMIN_ID and context.args:
        msg = " ".join(context.args)
        sent, blocked = 0, 0
        for u in all_users:
            try: 
                await context.bot.send_message(u, msg)
                sent += 1
            except: blocked += 1
        await update.message.reply_text(f"✅ Broadcast Report:\nSent: {sent}\nBlocked: {blocked}")

async def save_file(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    key = f"file_{update.message.message_id}"
    files_db[key] = [{'chat_id': update.effective_chat.id, 'message_id': update.message.message_id, 'caption': update.message.caption or ""}]
    await update.message.reply_text(f"✅ Saved! Link: t.me/{BOT_USERNAME}?start={key}")

async def save_batch(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        f = context.args[0]; c = int("-100"+f.split('/')[4]); s = int(f.split('/')[5]); e = int(context.args[1].split('/')[-1]); name = context.args[2]
        files_db[name] = [{'chat_id': c, 'message_id': i, 'caption': ""} for i in range(s, e + 1)]
        await update.message.reply_text(f"✅ Batch Saved!\n🔗 Link: t.me/{BOT_USERNAME}?start={name}")
    except: await update.message.reply_text("❌ Error!")

async def redeem(update, context):
    user = update.message.from_user
    code = context.args[0] if context.args else ""
    if code in valid_codes and valid_codes[code]['uses_left'] > 0:
        valid_codes[code]['uses_left'] -= 1
        now = datetime.datetime.now(IST)
        user_membership[user.id] = {'name': user.first_name, 'expiry': now + datetime.timedelta(days=valid_codes[code]['days']), 'code': code, 'join_date': now.strftime("%Y-%m-%d %H:%M")}
        await update.message.reply_text("✅ Membership activated!")
    else: await update.message.reply_text("❌ Invalid code!")

async def info(update, context):
    msg = "📜 **Commands:**\n/savebatch [L1] [L2] [NAME]\n/addcode [CODE] [DAYS] [USES]\n/redeem [CODE]\n/stats\n/broadcast [MSG]\n/cancel_membership [ID]\n/ban [ID]"
    await update.message.reply_text(msg)

# --- APP SETUP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("savebatch", save_batch))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("addcode", addcode))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("info", info))
app.add_handler(CommandHandler("cancel_membership", cancel_membership))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, save_file))

print("Master Bot is Running!")
app.run_polling()
