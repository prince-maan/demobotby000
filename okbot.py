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
TOKEN = '8760244596:AAGSzPn7773wv_cc8rVFHQfhJIAFPKl_LJI'
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
    
    uname = f"@{user.username}" if user.username else "No Username"
    all_users[user.id] = {'name': user.first_name, 'username': uname}
    
    if context.args:
        key = context.args[0]
        if key in files_db:
            if user.id == ADMIN_ID or (user.id in user_membership and datetime.datetime.now(IST) < user_membership[user.id]['expiry']):
                
                # --- NAYA LOGIC: HORIZONTAL & VERTICAL SUPPORT ---
                if len(files_db[key]) == 1:
                    # Single File Logic
                    f = files_db[key][0]
                    try: 
                        if f.get('caption'):
                            await context.bot.copy_message(chat_id=user.id, from_chat_id=f['chat_id'], message_id=f['message_id'], protect_content=True, caption=f['caption'])
                        else:
                            await context.bot.copy_message(chat_id=user.id, from_chat_id=f['chat_id'], message_id=f['message_id'], protect_content=True)
                    except: pass
                else:
                    # Batch File Logic (Fast & Supports Albums)
                    source_chat = files_db[key][0]['chat_id']
                    msg_ids = [f['message_id'] for f in files_db[key]]
                    
                    for i in range(0, len(msg_ids), 100):
                        chunk = msg_ids[i:i+100]
                        try:
                            await context.bot.copy_messages(chat_id=user.id, from_chat_id=source_chat, message_ids=chunk, protect_content=True)
                        except Exception as e:
                            print(f"Batch sending error: {e}")
                # --------------------------------------------------
                
            else: 
                await update.message.reply_text("⚠️ Important Notice\n\n\n• You haven't purchased a membership here, or your membership has expired.\n\n• आपने यहाँ कोई मेंबरशिप नहीं खरीदी है, या आपकी मेंबरशिप की समय-सीमा समाप्त हो गई है।\n\n\n🔮 Purchase membership here:\n", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]]))
        else: 
            await update.message.reply_text("❌ File not found.")
    else: 
        await update.message.reply_text("🫡 Hi, I'm Saul.\n\nTo watch videos, subscribe to a membership.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)]]))

async def info(update, context):
    msg = ("📜 **Commands Tutorial:**\n\n"
           "📌 /savebatch [Link1] [Link2] [NAME]\n\n"
           "🧑‍🤝‍🧑 /addcode [CODE] [DAYS] [USES]\n\n"
           "🕺 /redeem [CODE]\n\n"
           "👁️ /stats\n\n"
           "📳 /broadcast [MESSAGE]\n\n"
           "💳 /cancel [ID]\n\n"
           "👟 /ban [ID]\n\n"
           "📤 /export\n\n"
           "📥 /import [DATA]")
    await update.message.reply_text(msg)

async def addcode(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        code = context.args[0]
        days = int(context.args[1])
        uses = int(context.args[2])
        valid_codes[code] = {'days': days, 'uses_left': uses}
        await update.message.reply_text(f"✅ Code '{code}' added!\n⏳ Validity: {days} Days\n👥 Uses Limit: {uses}")
    except: 
        await update.message.reply_text("❌ Format Error! Use: /addcode [CODE] [DAYS] [USES]")

async def redeem(update, context):
    user = update.message.from_user
    code = context.args[0] if context.args else ""
    if code in valid_codes and valid_codes[code]['uses_left'] > 0:
        valid_codes[code]['uses_left'] -= 1
        now = datetime.datetime.now(IST)
        expiry_date = now + datetime.timedelta(days=valid_codes[code]['days'])
        
        uname = f"@{user.username}" if user.username else "No Username"
        user_membership[user.id] = {
            'name': user.first_name, 
            'username': uname,
            'expiry': expiry_date, 
            'code': code, 
            'join_date': now.strftime("%Y-%m-%d %I:%M %p")
        }
        await update.message.reply_text("✅ Membership activated successfully!")
    else: 
        await update.message.reply_text("❌ Invalid or Expired code!")

async def stats(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    now = datetime.datetime.now(IST)
    active_list = []
    
    for uid, d in user_membership.items():
        if now < d['expiry']:
            rem = d['expiry'] - now
            uname = d.get('username', 'No Username')
            active_list.append(
                f"👤 Name: {d['name']} | {uname}\n"
                f"🆔 User ID: {uid}\n"
                f"🎫 Code Used: {d.get('code', 'N/A')}\n"
                f"📅 Joined: {d.get('join_date', 'N/A')}\n"
                f"⏳ Expiry: {d['expiry'].strftime('%Y-%m-%d %I:%M %p')}\n"
                f"⌛ Time Left: {rem.days} Days, {rem.seconds//3600} Hours\n"
                f"------------------------"
            )
    
    msg = (f"📊 **STATISTICS**\n"
           f"👥 Total Users: {len(all_users)}\n"
           f"✅ Active Members: {len(active_list)}\n"
           f"🚫 Banned Users: {len(banned_users)}\n\n"
           f"📋 **Detailed Active Members:**\n\n" + "\n".join(active_list))
    
    if len(msg) > 4000:
        for x in range(0, len(msg), 4000):
            await update.message.reply_text(msg[x:x+4000])
    else:
        await update.message.reply_text(msg)

async def broadcast(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("❌ Please provide a message: /broadcast [MESSAGE]")
        return
        
    msg = " ".join(context.args)
    sent = 0
    blocked = 0
    
    await update.message.reply_text("⏳ Broadcast started... please wait.")
    for u in all_users:
        try: 
            await context.bot.send_message(chat_id=u, text=msg)
            sent += 1
        except: 
            blocked += 1
            
    await update.message.reply_text(f"✅ **Broadcast Report:**\n📨 Successfully Sent: {sent}\n🚫 Blocked by users: {blocked}")

async def save_file(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    key = f"file_{update.message.message_id}"
    caption = update.message.caption if update.message.caption else ""
    
    files_db[key] = [{'chat_id': update.effective_chat.id, 'message_id': update.message.message_id, 'caption': caption}]
    await update.message.reply_text(f"✅ Single File Saved!\n🔗 Link: https://t.me/{BOT_USERNAME}?start={key}")

async def save_batch(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        first_link = context.args[0]
        c = int("-100" + first_link.split('/')[4])
        s = int(first_link.split('/')[5])
        e = int(context.args[1].split('/')[-1])
        name = context.args[2]
        
        files_db[name] = [{'chat_id': c, 'message_id': i} for i in range(s, e + 1)]
        await update.message.reply_text(f"✅ Batch Saved Successfully!\n🔗 Link: https://t.me/{BOT_USERNAME}?start={name}")
    except Exception as e: 
        await update.message.reply_text(f"❌ Error! Correct format: /savebatch [LINK1] [LINK2] [NAME]")

async def cancel_membership(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        uid = int(context.args[0])
        if uid in user_membership: 
            del user_membership[uid]
            await update.message.reply_text(f"✅ User ID {uid} membership cancelled.")
        else: 
            await update.message.reply_text("❌ This user is not an active member.")
    except:
        await update.message.reply_text("❌ Format: /cancel [USER_ID]")

async def ban(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        banned_users.add(int(context.args[0]))
        await update.message.reply_text("🚫 User Banned.")
    except:
        pass

async def export_data(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    data_str = str(files_db)
    if len(data_str) > 4000:
        for i in range(0, len(data_str), 4000):
            await update.message.reply_text(data_str[i:i+4000])
    else:
        await update.message.reply_text(f"📂 **Backup Data:**\n\n`{data_str}`", parse_mode='Markdown')

async def import_data(update, context):
    if update.message.from_user.id != ADMIN_ID: return
    try:
        global files_db
        files_db = eval(" ".join(context.args))
        await update.message.reply_text("✅ Data imported successfully!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error importing data: {str(e)}")

# --- 5. APP SETUP & HANDLERS ---
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("info", info))
app.add_handler(CommandHandler("addcode", addcode))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("savebatch", save_batch))
app.add_handler(CommandHandler("cancel", cancel_membership))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("export", export_data))
app.add_handler(CommandHandler("import", import_data))

app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, save_file))

print("Master Bot is Running perfectly without errors!")
app.run_polling()
