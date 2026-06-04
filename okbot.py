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
TOKEN = '8120598596:AAHe91PxDQSCFGQl68rxw0rgUne6f7Sa9zI'
ADMIN_ID = 8717007836
BOT_USERNAME = "lite0000op_bot"
BUY_LINK = "https://t.me/SaulGoodmanOp"
IST = pytz.timezone('Asia/Kolkata')

# --- 3. DATABASE ---
user_membership = {}
files_db = {}         
valid_codes = {}      
all_users = {}        
banned_users = set()

# --- 4. BUTTONS ---
def get_buy_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]])

# --- 5. FUNCTIONS ---

async def start(update, context):
    user = update.message.from_user
    if user.id in banned_users: return
    all_users[user.id] = {'name': user.first_name}
    
    if context.args:
        key = context.args[0]
        if key in files_db:
            if user.id == ADMIN_ID or (user.id in user_membership and datetime.datetime.now(IST) < user_membership[user.id]['expiry']):
                for f in files_db[key]:
                    try: 
                        await context.bot.copy_message(chat_id=user.id, from_chat_id=f['chat_id'], message_id=f['message_id'], protect_content=True, caption=f.get('caption', ""))
                    except: continue
            else: 
                await update.message.reply_text("😒 Membership inactive or expired.", reply_markup=get_buy_keyboard())
        else: await update.message.reply_text("❌ File not found.")
    else: 
        await update.message.reply_text("🫡 Hi, I'm Heisenberg.\n\nTo watch videos, subscribe to a membership.", reply_markup=get_buy_keyboard())

# --- COMMANDS & LOGIC ---

async def stats_pro(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    now = datetime.datetime.now(IST)
    msg = "📊 **DETAILED ACTIVE MEMBERS**\n\n"
    for uid, data in user_membership.items():
        if now < data['expiry']:
            rem = data['expiry'] - now
            try:
                member = await context.bot.get_chat_member(uid, uid)
                username = f"@{member.user.username}" if member.user.username else "No Username"
            except: username = "N/A"
            msg += (f"👤 {data['name']} | {username}\n🆔 {uid}\n🔑 Code: {data['code']}\n📅 {data.get('join_date', 'N/A')}\n⏳ {rem.days}d {rem.seconds//3600}h {(rem.seconds%3600)//60}m\n------------------------\n")
    if not user_membership: msg += "No active members."
    for i in range(0, len(msg), 4000): await update.message.reply_text(msg[i:i+4000])

async def redeem(update, context):
    user = update.message.from_user
    code = context.args[0] if context.args else ""
    if code in valid_codes and valid_codes[code]['uses_left'] > 0:
        valid_codes[code]['uses_left'] -= 1
        now = datetime.datetime.now(IST)
        user_membership[user.id] = {'name': user.first_name, 'expiry': now + datetime.timedelta(days=valid_codes[code]['days']), 'code': code, 'join_date': now.strftime("%Y-%m-%d %I:%M %p")}
        await update.message.reply_text("✅ Membership activated!")
    else: await update.message.reply_text("❌ Invalid code!")

async def save_file(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    key = f"file_{update.message.message_id}"
    files_db[key] = [{'chat_id': update.effective_chat.id, 'message_id': update.message.message_id, 'caption': update.message.caption or ""}]
    await update.message.reply_text(f"✅ Saved! Link: t.me/{BOT_USERNAME}?start={key}")

# --- REUSING YOUR OLD LOGIC FOR OTHER COMMANDS ---
# (Keeping your original export/import/save_batch/stats/broadcast logic intact below)

async def export_data(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    data_str = str(files_db)
    for i in range(0, len(data_str), 4000): await update.message.reply_text(f"📂 **Backup:**\n\n{data_str[i:i+4000]}")

async def import_data(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        global files_db
        files_db = eval(" ".join(context.args))
        await update.message.reply_text("✅ Data imported!")
    except Exception as e: await update.message.reply_text(f"❌ Error: {str(e)}")

async def stats(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    await update.message.reply_text(f"📊 **STATISTICS**\n👥 Total: {len(all_users)}\n✅ Active: {len(user_membership)}\n🚫 Banned: {len(banned_users)}")

async def save_batch(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        f = context.args[0]; c = int("-100"+f.split('/')[4]); s = int(f.split('/')[5]); e = int(context.args[1].split('/')[-1])
        files_db[context.args[2]] = [{'chat_id': c, 'message_id': i, 'caption': ""} for i in range(s, e + 1)]
        await update.message.reply_text("✅ Batch Saved!")
    except: await update.message.reply_text("❌ Error!")

async def cancel_membership(update, context):
    if update.message.from_user.id == ADMIN_ID and context.args:
        uid = int(context.args[0])
        if uid in user_membership: del user_membership[uid]; await update.message.reply_text(f"✅ Cancelled {uid}")
        else: await update.message.reply_text("❌ Not active.")

async def broadcast(update, context):
    if update.message.from_user.id == ADMIN_ID and context.args:
        msg = " ".join(context.args)
        for u in all_users:
            try: await context.bot.send_message(u, msg)
            except: pass
        await update.message.reply_text("✅ Broadcast complete.")

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
app.add_handler(CommandHandler("stats_pro", stats_pro))
app.add_handler(CommandHandler("cancel_membership", cancel_membership))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("export", export_data))
app.add_handler(CommandHandler("import", import_data))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, save_file))

print("Master Bot is Running!")
app.run_polling()
