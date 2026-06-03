from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import datetime
import asyncio
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
TOKEN = '8896341222:AAFqDx4VaRfkgXWJDM0TxyAncHiiX2RUNeo'
ADMIN_ID = 8855787926
BOT_USERNAME = "mynew778899bot"
BUY_LINK = "https://t.me/theHeisenberg009"

# --- 3. DATABASE ---
user_membership = {}
files_db = {}         
valid_codes = {}      
all_users = {}        
banned_users = set()

# --- 4. BUTTONS ---
def get_buy_keyboard():
    keyboard = [[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]]
    return InlineKeyboardMarkup(keyboard)

# --- 5. FUNCTIONS ---

async def start(update, context):
    user = update.message.from_user
    if user.id in banned_users: return
    all_users[user.id] = {'name': user.first_name}
    
    if context.args:
        key = context.args[0]
        if key in files_db:
            if user.id == ADMIN_ID or (user.id in user_membership and datetime.datetime.now() < user_membership[user.id]['expiry']):
                for f in files_db[key]:
                    try: 
                        await context.bot.copy_message(chat_id=user.id, from_chat_id=f['chat_id'], message_id=f['message_id'], protect_content=True)
                    except: continue
            else: 
                await update.message.reply_text("😒 Your membership is not active.\n\n You have either not yet purchased a membership, or it has expired.", reply_markup=get_buy_keyboard())
        else: await update.message.reply_text("❌ File not found.")
    else: 
        await update.message.reply_text("🫡 Hi, I'm Heisenberg \n\nTo Watch the videos, you need to subscribe to a membership.", reply_markup=get_buy_keyboard())

async def info(update, context):
    msg = ("📜 **Commands Tutorial:**\n\n \n\n📌 /savebatch [L1] [L2] [NAME]\n\n🧑‍🤝‍🧑 /addcode [CODE] [DAYS] [USES]\n\n🕺 /redeem [CODE]\n\n👁️ /stats\n\n📳 /broadcast [MSG]\n\n👟 /ban [ID]\n/reminder")
    await update.message.reply_text(msg)

async def stats(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    msg = f"📊 **STATISTICS**\n👥 Total: {len(all_users)}\n✅ Active: {len(user_membership)}\n🚫 Banned: {len(banned_users)}"
    await update.message.reply_text(msg)

async def broadcast(update, context):
    if update.message.from_user.id == ADMIN_ID and context.args:
        msg = " ".join(context.args)
        success, failed = 0, 0
        for u in all_users:
            try: await context.bot.send_message(u, msg); success += 1
            except: failed += 1
        await update.message.reply_text(f"✅ Broadcast Report:\n👤 Sent: {success}\n🚫 Failed: {failed}")

async def reminder_broadcast(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    now = datetime.datetime.now()
    count = 0
    for uid, data in user_membership.items():
        if now < data['expiry'] and (data['expiry'] - now).days <= 2:
            try: await context.bot.send_message(uid, "⚠️ Alert: Membership expiring soon!\n💰 Renew: " + BUY_LINK); count += 1
            except: continue
    await update.message.reply_text(f"✅ Reminder sent to {count} members.")

async def save_file(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    key = f"file_{update.message.message_id}"
    files_db[key] = [{'chat_id': update.effective_chat.id, 'message_id': update.message.message_id}]
    await update.message.reply_text(f"✅ Saved! Link: t.me/{BOT_USERNAME}?start={key}")

async def save_batch(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        first_link = context.args[0]
        chat_id = int("-100" + first_link.split('/')[4])
        start_id = int(first_link.split('/')[5])
        end_id = int(context.args[1].split('/')[-1])
        files_db[context.args[2]] = [{'chat_id': chat_id, 'message_id': i} for i in range(start_id, end_id + 1)]
        await update.message.reply_text("✅ Batch Saved!")
    except: await update.message.reply_text("❌ Error!")

async def ban(update, context):
    if update.message.from_user.id == ADMIN_ID: banned_users.add(int(context.args[0])); await update.message.reply_text("🚫 Banned.")

async def redeem(update, context):
    user = update.message.from_user
    code = context.args[0] if context.args else ""
    if code in valid_codes and valid_codes[code]['uses_left'] > 0:
        valid_codes[code]['uses_left'] -= 1
        expiry = datetime.datetime.now() + datetime.timedelta(days=valid_codes[code]['days'])
        user_membership[user.id] = {'name': user.first_name, 'expiry': expiry, 'code': code}
        await update.message.reply_text("✅ Membership activated!")
    else: await update.message.reply_text("❌ Invalid code!")

async def addcode(update, context):
    if update.message.from_user.id == ADMIN_ID:
        valid_codes[context.args[0]] = {'days': int(context.args[1]), 'uses_left': int(context.args[2])}
        await update.message.reply_text(f"✅ Code {context.args[0]} added!")

# --- 6. APP SETUP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("savebatch", save_batch))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("addcode", addcode))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("reminder", reminder_broadcast))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("info", info))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, save_file))

print("Master Bot is Running!")
app.run_polling()
