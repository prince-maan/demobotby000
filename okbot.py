from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
import datetime
import asyncio
import os
from flask import Flask
from threading import Thread

# --- KEEP-ALIVE SERVER (होस्टिंग के लिए जरूरी) ---
app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "Bot is active!"
def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
Thread(target=run_flask).start()

# --- SETTINGS ---
TOKEN = '8896341222:AAFqDx4VaRfkgXWJDM0TxyAncHiiX2RUNeo'
ADMIN_ID = 8855787926
BOT_USERNAME = "mynew778899bot"

# --- DATABASE ---
user_membership = {}
files_db = {}         
valid_codes = {}      
all_users = {}        
banned_users = set()

# --- FUNCTIONS ---

async def start(update, context):
    user = update.message.from_user
    if user.id in banned_users: return
    all_users[user.id] = {'name': user.first_name, 'username': user.username or 'N/A'}
    if context.args:
        key = context.args[0]
        if key in files_db:
            if user.id == ADMIN_ID or (user.id in user_membership and datetime.datetime.now() < user_membership[user.id]['expiry']):
                for f in files_db[key]:
                    try: 
                        # Content Protection: Forwarding disabled
                        await context.bot.copy_message(chat_id=user.id, from_chat_id=f['chat_id'], message_id=f['message_id'], protect_content=True)
                    except: continue
            else: await update.message.reply_text("😒 Your membership is not active.\n\n You have either not yet purchased a membership, or it has expired.\n\n💰 Buy Now - @theHeisenberg009")
        else: await update.message.reply_text("❌ File not found.")
    else: await update.message.reply_text("🫡 Hi, I'm Heisenberg\n\nTo Watch the videos, you need to subscribe to a membership.\n\n💰 Membership Buy Now - @theHeisenberg009\n\n ")

async def info(update, context):
    msg = ("📜 **Commands Tutorial:**\n\n"
           "/savebatch [LINK1] [LINK2] [NAME]\n/addcode [CODE] [DAYS] [USES]\n/redeem [CODE]\n"
           "/stats - Total stats aur members ki detail\n/broadcast [MESSAGE]\n/ban [USER_ID]")
    await update.message.reply_text(msg)

async def stats(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    now = datetime.datetime.now()
    total_users = len(all_users)
    membership_users = len(user_membership)
    non_membership = total_users - membership_users
    blocked = len(banned_users)
    
    msg = (f"📊 **TOTAL STATISTICS**\n"
           f"━━━━━━━━━━━━━━\n"
           f"👥 Total Users: {total_users}\n"
           f"✅ Membership Li: {membership_users}\n"
           f"❌ Membership Nahi Li: {non_membership}\n"
           f"🚫 Blocked Users: {blocked}\n\n"
           f"📜 **ACTIVE MEMBERS LIST**\n"
           f"━━━━━━━━━━━━━━\n")
    
    for uid, data in user_membership.items():
        if now < data['expiry']:
            msg += (f"👤 {data.get('name', 'User')} (@{data.get('username', 'N/A')})\n"
                    f"📅 Start: {data['joined'].strftime('%d-%m')}\n"
                    f"⏳ End: {data['expiry'].strftime('%d-%m')}\n"
                    f"🎫 Code: {data['code']}\n\n")
    await update.message.reply_text(msg if len(msg) > 50 else "Koi active member nahi hai.")

async def save_batch(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    if len(context.args) < 3: return
    first_link, last_link, batch_name = context.args[0], context.args[1], context.args[2]
    try:
        parts = first_link.split('/')
        chat_id = int("-100" + parts[4])
        start_id = int(parts[5])
        end_id = int(last_link.split('/')[-1])
        files_db[batch_name] = [{'chat_id': chat_id, 'message_id': i} for i in range(start_id, end_id + 1)]
        await update.message.reply_text(f"✅ Batch '{batch_name}' saved!")
    except: await update.message.reply_text("❌ Error!")

async def save_file(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    key = f"file_{update.message.message_id}"
    files_db[key] = [{'chat_id': update.effective_chat.id, 'message_id': update.message.message_id}]
    await update.message.reply_text(f"✅ Saved! 🔗 Link: t.me/{BOT_USERNAME}?start={key}")

async def broadcast(update, context):
    if update.message.from_user.id == ADMIN_ID and context.args:
        msg = " ".join(context.args)
        success = 0
        failed = 0
        for u in all_users:
            try: 
                await context.bot.send_message(u, msg)
                success += 1
            except: 
                failed += 1
        await update.message.reply_text(f"✅ Broadcast Report:\n👤 Sent to: {success} users\n🚫 Failed/Blocked: {failed} users")

async def ban(update, context):
    if update.message.from_user.id == ADMIN_ID and context.args:
        uid = int(context.args[0])
        banned_users.add(uid)
        await update.message.reply_text(f"🚫 User {uid} banned.")

async def redeem(update, context):
    user = update.message.from_user
    code = context.args[0] if context.args else ""
    if code in valid_codes and valid_codes[code]['uses_left'] > 0:
        valid_codes[code]['uses_left'] -= 1
        now = datetime.datetime.now()
        expiry = now + datetime.timedelta(days=valid_codes[code]['days'])
        user_membership[user.id] = {'name': user.first_name, 'username': user.username, 'joined': now, 'expiry': expiry, 'code': code}
        await update.message.reply_text("✅ Membership activated!")
    else: await update.message.reply_text("❌ Galat ya expired code!")

async def addcode(update, context):
    if update.message.from_user.id == ADMIN_ID and len(context.args) == 3:
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
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("info", info))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, save_file))

print("Bot is ready with Content Protection and Broadcast Report!")
app.run_polling()
