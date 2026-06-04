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

# --- 4. COMMANDS & FUNCTIONS ---

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
            else: await update.message.reply_text("😒 Membership inactive.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy", url=BUY_LINK)]]))
        else: await update.message.reply_text("❌ File not found.")
    else: await update.message.reply_text("🫡 Hi! Subscribe to access content.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]]))

async def addcode(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    if len(context.args) >= 3:
        code, days, uses = context.args[0], int(context.args[1]), int(context.args[2])
        valid_codes[code] = {'days': days, 'uses_left': uses}
        await update.message.reply_text(f"✅ Code {code} added!")
    else: await update.message.reply_text("⚠️ Use: /addcode [CODE] [DAYS] [USES]")

async def redeem(update, context):
    user = update.message.from_user
    code = context.args[0] if context.args else ""
    if code in valid_codes and valid_codes[code]['uses_left'] > 0:
        valid_codes[code]['uses_left'] -= 1
        now = datetime.datetime.now()
        user_membership[user.id] = {'name': user.first_name, 'expiry': now + datetime.timedelta(days=valid_codes[code]['days']), 'code': code, 'join_date': now.strftime("%Y-%m-%d %H:%M")}
        await update.message.reply_text("✅ Membership activated!")
    else: await update.message.reply_text("❌ Invalid code.")

async def stats(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    total = len(all_users)
    active = len(user_membership)
    await update.message.reply_text(f"📊 **STATISTICS**\n👥 Total Users: {total}\n✅ Active: {active}\n❌ Non-Members: {total - active}")

async def stats_pro(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    now = datetime.datetime.now()
    msg = "📊 **ACTIVE MEMBERS LIST**\n\n"
    for uid, data in user_membership.items():
        if now < data['expiry']:
            rem = data['expiry'] - now
            try:
                member = await context.bot.get_chat_member(uid, uid)
                username = f"@{member.user.username}" if member.user.username else "No Username"
            except: username = "N/A"
            msg += f"👤 {data['name']} | {username}\n🆔 {uid}\n🔑 {data['code']}\n📅 {data.get('join_date', 'N/A')}\n⏳ {rem.days}d {rem.seconds//3600}h\n----------------\n"
    await update.message.reply_text(msg if user_membership else "No active members.")

async def cancel_membership(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    if context.args:
        uid = int(context.args[0])
        if uid in user_membership:
            del user_membership[uid]
            await update.message.reply_text(f"✅ Membership cancelled for {uid}")
        else: await update.message.reply_text("❌ Not found.")

async def broadcast(update, context):
    if update.message.from_user.id == ADMIN_ID and context.args:
        msg = " ".join(context.args)
        for u in all_users:
            try: await context.bot.send_message(u, msg)
            except: pass
        await update.message.reply_text("✅ Broadcast complete.")

async def save_batch(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        f = context.args[0]; c = int("-100"+f.split('/')[4]); s = int(f.split('/')[5]); e = int(context.args[1].split('/')[-1])
        files_db[context.args[2]] = [{'chat_id': c, 'message_id': i} for i in range(s, e + 1)]
        await update.message.reply_text("✅ Batch Saved!")
    except: await update.message.reply_text("❌ Error!")

# --- 6. APP SETUP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addcode", addcode))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("stats_pro", stats_pro))
app.add_handler(CommandHandler("cancel_membership", cancel_membership))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("savebatch", save_batch))

print("Master Bot is Running!")
app.run_polling()
