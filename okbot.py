from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import datetime
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
BUY_LINK = "https://t.me/SaulGoodmanOp"

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
            if user.id == ADMIN_ID or (user.id in user_membership and datetime.datetime.now() < user_membership[user.id]['expiry']):
                for f in files_db[key]:
                    try: await context.bot.copy_message(chat_id=user.id, from_chat_id=f['chat_id'], message_id=f['message_id'], protect_content=True)
                    except: continue
            else: await update.message.reply_text("😒 Your membership is not active.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]]))
        else: await update.message.reply_text("❌ File not found.")
    else: await update.message.reply_text("🫡 Hi, I'm Heisenberg.\n\nTo Watch the videos, you need to subscribe to a membership.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]]))

async def stats_pro(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    now = datetime.datetime.now()
    total = len(all_users)
    active = len(user_membership)
    
    msg = (f"📊 **DETAILED STATISTICS**\n\n"
           f"👥 Total Users: {total}\n"
           f"✅ Active Members: {active}\n"
           f"❌ Non-Members: {total - active}\n\n"
           f"📜 **Active Members Details:**\n")
    
    for uid, data in user_membership.items():
        if now < data['expiry']:
            rem = data['expiry'] - now
            # Username fetch karne ki koshish
            try:
                member = await context.bot.get_chat_member(uid, uid)
                username = f"@{member.user.username}" if member.user.username else "No Username"
            except: username = "N/A"
            
            msg += (f"👤 Name: {data['name']} | {username}\n"
                    f"🆔 ID: {uid}\n"
                    f"🔑 Code: {data['code']}\n"
                    f"📅 Joined: {data.get('join_date', 'N/A')}\n"
                    f"⏳ Remaining: {rem.days}d {rem.seconds // 3600}h {(rem.seconds % 3600) // 60}m\n"
                    f"------------------------\n")
    
    for i in range(0, len(msg), 4000): await update.message.reply_text(msg[i:i+4000])

async def redeem(update, context):
    user = update.message.from_user
    code = context.args[0] if context.args else ""
    if code in valid_codes and valid_codes[code]['uses_left'] > 0:
        valid_codes[code]['uses_left'] -= 1
        now = datetime.datetime.now()
        user_membership[user.id] = {'name': user.first_name, 'expiry': now + datetime.timedelta(days=valid_codes[code]['days']), 'code': code, 'join_date': now.strftime("%Y-%m-%d %H:%M")}
        await update.message.reply_text("✅ Membership activated!")
    else: await update.message.reply_text("❌ Invalid code!")

async def cancel_membership(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    if context.args:
        uid = int(context.args[0])
        if uid in user_membership:
            del user_membership[uid]
            await update.message.reply_text(f"✅ User {uid} ki membership cancel kar di gayi hai.")
        else: await update.message.reply_text("❌ Ye user active member nahi hai.")

async def broadcast(update, context):
    if update.message.from_user.id == ADMIN_ID and context.args:
        msg = " ".join(context.args)
        for u in all_users:
            try: await context.bot.send_message(u, msg)
            except: pass
        await update.message.reply_text("✅ Broadcast complete.")

# --- HANDLERS SETUP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats_pro", stats_pro))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("cancel_membership", cancel_membership))
app.add_handler(CommandHandler("broadcast", broadcast))
# Add other handlers (savebatch, addcode, etc.) as you had before...

print("Master Bot is Running!")
app.run_polling()
