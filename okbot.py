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
                    try: await context.bot.copy_message(chat_id=user.id, from_chat_id=f['chat_id'], message_id=f['message_id'], protect_content=True)
                    except: continue
            else: await update.message.reply_text("😒 Membership inactive or expired.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]]))
        else: await update.message.reply_text("❌ File not found.")
    else: await update.message.reply_text("🫡 Hi, I'm Heisenberg.\n\nTo watch videos, subscribe to a membership.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]]))

async def info(update, context):
    msg = ("📜 **Commands Tutorial:**\n\n📌 /savebatch [L1] [L2] [NAME]\n🧑‍🤝‍🧑 /addcode [CODE] [DAYS] [USES]\n🕺 /redeem [CODE]\n👁️ /stats\n👟 /ban [ID]\n💳 /cancel_membership [ID]\n📤 /export\n📥 /import [DATA]\n📳 /broadcast [MSG]")
    await update.message.reply_text(msg)

async def save_batch(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        f = context.args[0]; c = int("-100"+f.split('/')[4]); s = int(f.split('/')[5]); e = int(context.args[1].split('/')[-1]); name = context.args[2]
        files_db[name] = [{'chat_id': c, 'message_id': i} for i in range(s, e + 1)]
        await update.message.reply_text(f"✅ Batch Saved!\n🔗 Link: t.me/{BOT_USERNAME}?start={name}")
    except: await update.message.reply_text("❌ Error! Use: /savebatch [LINK1] [LINK2] [NAME]")

async def redeem(update, context):
    user = update.message.from_user
    code = context.args[0] if context.args else ""
    if code in valid_codes and valid_codes[code]['uses_left'] > 0:
        valid_codes[code]['uses_left'] -= 1
        now = datetime.datetime.now(IST)
        user_membership[user.id] = {'name': user.first_name, 'expiry': now + datetime.timedelta(days=valid_codes[code]['days']), 'code': code}
        await update.message.reply_text("✅ Membership activated!")
    else: await update.message.reply_text("❌ Invalid or expired code!")

async def stats(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    now = datetime.datetime.now(IST)
    active = [d for d in user_membership.values() if now < d['expiry']]
    await update.message.reply_text(f"📊 **STATISTICS**\n👥 Total: {len(all_users)}\n✅ Active: {len(active)}\n🚫 Banned: {len(banned_users)}")

async def export_data(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    data_str = str(files_db)
    for i in range(0, len(data_str), 4000): await update.message.reply_text(data_str[i:i+4000])

async def import_data(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try: 
        global files_db
        files_db = eval(" ".join(context.args))
        await update.message.reply_text("✅ Data imported!")
    except: await update.message.reply_text("❌ Error importing data!")

async def broadcast(update, context):
    if update.message.from_user.id == ADMIN_ID and context.args:
        msg = " ".join(context.args)
        for u in all_users:
            try: await context.bot.send_message(u, msg)
            except: pass
        await update.message.reply_text("✅ Broadcast complete.")

async def cancel_membership(update, context):
    if update.message.from_user.id == ADMIN_ID and context.args:
        uid = int(context.args[0])
        if uid in user_membership: del user_membership[uid]; await update.message.reply_text(f"✅ Cancelled {uid}")
        else: await update.message.reply_text("❌ Not active.")

async def ban(update, context):
    if update.message.from_user.id == ADMIN_ID: banned_users.add(int(context.args[0])); await update.message.reply_text("🚫 Banned.")

async def addcode(update, context):
    if update.message.from_user.id == ADMIN_ID:
        valid_codes[context.args[0]] = {'days': int(context.args[1]), 'uses_left': int(context.args[2])}
        await update.message.reply_text(f"✅ Code {context.args[0]} added!")

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
app.add_handler(CommandHandler("export", export_data))
app.add_handler(CommandHandler("import", import_data))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, lambda u, c: None))

print("Master Bot is Running!")
app.run_polling()
