from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
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
TOKEN = '8120598596:AAGCBHAbhc7V_Jnj8Z0H85QpLaDk3WCACLU'
ADMIN_ID = 8717007836
BOT_USERNAME = "lite0000op_bot"
BUY_LINK = "https://t.me/theHeisenberg009"
DB_CHANNEL_ID = -100XXXXXXXXXX # यहाँ अपना डेटाबेस चैनल ID डालें

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
                await update.message.reply_text("😒 Your membership is not active.", reply_markup=get_buy_keyboard())
        else: await update.message.reply_text("❌ File not found.")
    else: 
        await update.message.reply_text("🫡 Hi, I'm Heisenberg \n\nTo Watch the videos, you need to subscribe to a membership.", reply_markup=get_buy_keyboard())

# --- NEW FEATURE: SUBSCRIPTION LIST ---
async def sub_list(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    now = datetime.datetime.now()
    text = "📊 **ACTIVE SUBSCRIPTIONS:**\n\n"
    for uid, data in user_membership.items():
        if now < data['expiry']:
            remaining = (data['expiry'] - now).days
            text += f"👤 {data['name']} (ID: {uid})\n⏳ Expire in: {remaining} days\n🏷 Code: {data['code']}\n\n"
    
    await context.bot.send_message(chat_id=DB_CHANNEL_ID, text=text)
    await update.message.reply_text("✅ List has been sent to your Database Channel!")

# --- OLD FEATURES PRESERVED ---
async def export_data(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    data_str = str(files_db)
    for i in range(0, len(data_str), 4000):
        await update.message.reply_text(f"📂 **Backup:**\n\n{data_str[i:i+4000]}")

async def import_data(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        global files_db
        files_db = eval(" ".join(context.args))
        await update.message.reply_text("✅ Data imported!")
    except Exception as e: await update.message.reply_text(f"❌ Error: {str(e)}")

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
        await update.message.reply_text(f"✅ Sent: {success}\n🚫 Failed: {failed}")

async def reminder_broadcast(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    now = datetime.datetime.now()
    count = 0
    for uid, data in user_membership.items():
        if now < data['expiry'] and (data['expiry'] - now).days <= 2:
            try: await context.bot.send_message(uid, "⚠️ Alert: Membership expiring soon!\n💰 Renew: " + BUY_LINK); count += 1
            except: continue
    await update.message.reply_text(f"✅ Reminders sent to {count} members.")

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

# --- APP SETUP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("savebatch", save_batch))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("addcode", addcode))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("reminder", reminder_broadcast))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("sublist", sub_list)) # New Command
app.add_handler(CommandHandler("export", export_data))
app.add_handler(CommandHandler("import", import_data))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, save_file))

print("Master Bot is Running!")
app.run_polling()
