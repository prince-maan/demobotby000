from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import datetime
import pytz
import os
import random
import string
import io
import pymongo
from flask import Flask
from threading import Thread

# --- 1. KEEP-ALIVE SERVER ---
app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "Prince Bot is active!"
def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
Thread(target=run_flask).start()

# --- 2. SETTINGS (PRINCE) ---
TOKEN = '8383623405:AAHzYF8uDsnHmvSbiXRvG7SJGLAwWB8Hx68' 
ADMIN_IDS = [8820964089] 
BOT_USERNAME = "smallPinkVide00s_bot" 
BUY_LINK = "https://t.me/SaulGoodmanOp"
IST = pytz.timezone('Asia/Kolkata')
TIERS = {'lite': 1, 'premium': 2, 'ultra': 3}

# --- 3. MONGODB DATABASE ---
MONGO_URI = "mongodb+srv://walter1122op_db_user:7b9QH8JrydXngsHi@cluster0.h4nwnyq.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = pymongo.MongoClient(MONGO_URI)
db = client["TelegramBotDB"]

USER_COLLECTION = db["Prince_Users"]
FILE_COLLECTION = db["common_files"]
CODE_COLLECTION = db["Prince_Codes"]

# CONVERSATION STATES
(WAIT_REDEEM_CODE, WAIT_CODE_DAYS, WAIT_CODE_USES, 
 WAIT_FIRST_LINK, WAIT_LAST_LINK, WAIT_BATCH_NAME, 
 WAIT_BROADCAST_MSG, WAIT_USER_ID, WAIT_IMPORT_DATA) = range(9)

# --- 4. MAIN USER FUNCTIONS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u_doc = USER_COLLECTION.find_one({"_id": user.id}) or {}
    
    if u_doc.get("is_banned"): 
        await update.message.reply_text("🚫 **You have been banned from using this bot.**\nआपको इस बॉट का उपयोग करने से बैन कर दिया गया है।")
        return
        
    USER_COLLECTION.update_one({"_id": user.id}, {"$set": {"name": user.first_name, "username": user.username, "is_blocked": False}}, upsert=True)
    now = datetime.datetime.now(IST)
    
    if context.args:
        key = context.args[0]
        f_doc = FILE_COLLECTION.find_one({"_id": key})
        if f_doc:
            user_tier = 'lite'
            has_active_plan = False
            if u_doc.get("expiry") and datetime.datetime.fromisoformat(u_doc["expiry"]) > now:
                user_tier = u_doc.get('tier', 'lite')
                has_active_plan = True
            
            if user.id in ADMIN_IDS: 
                user_tier = 'ultra'
                has_active_plan = True
                
            file_tier = f_doc['tier']
            
            if has_active_plan and TIERS[user_tier] >= TIERS[file_tier]:
                messages = f_doc['messages']
                source_chat = messages[0]['chat_id']
                msg_ids = [m['msg_id'] for m in messages]
                try:
                    await context.bot.copy_messages(chat_id=user.id, from_chat_id=source_chat, message_ids=msg_ids, protect_content=True)
                except Exception:
                    await update.message.reply_text("❌ **Error sending file.** / फाइल भेजने में समस्या हुई।")
            else:
                keyboard = [[InlineKeyboardButton("💎 Upgrade Membership", url=BUY_LINK)]]
                await update.message.reply_text(f"🛑 **Access Denied!**\nThis is a **{file_tier.upper()}** file, but your plan is **{user_tier.upper()}**.", reply_markup=InlineKeyboardMarkup(keyboard))
        else: 
            await update.message.reply_text("❌ **File not found.**\nफाइल नहीं मिली।")
    else: 
        status, tier_msg = "Inactive 🔴", "None"
        if u_doc.get("expiry") and datetime.datetime.fromisoformat(u_doc["expiry"]) > now:
            status, tier_msg = "Active 🟢", u_doc.get('tier', 'lite').upper()
            
        keyboard = [[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)], [InlineKeyboardButton("🎫 Redeem Code", callback_data="redeem_start")]]
        await update.message.reply_text(f"👋 **Welcome {user.first_name}!**\n👤 **Status:** {status}\n👑 **Current Plan:** {tier_msg}", reply_markup=InlineKeyboardMarkup(keyboard))

# --- 5. REDEEM SYSTEM ---
async def redeem_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("✍️ **Please type and send your promo code:**\n(Send /cancel to abort)")
    return WAIT_REDEEM_CODE

async def process_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    code = update.message.text.strip()
    c_doc = CODE_COLLECTION.find_one({"_id": code})
    
    if c_doc and c_doc['uses_left'] > 0:
        tier = c_doc['tier']
        days = c_doc['days']
        CODE_COLLECTION.update_one({"_id": code}, {"$inc": {"uses_left": -1}})
        
        now = datetime.datetime.now(IST)
        expiry_str = (now + datetime.timedelta(days=days)).isoformat()
        USER_COLLECTION.update_one({"_id": user.id}, {"$set": {'tier': tier, 'code': code, 'expiry': expiry_str, 'join_date': now.strftime("%Y-%m-%d %I:%M %p")}})
        
        await update.message.reply_text(f"🎉 **Congratulations!**\nYour **{tier.upper()}** plan activated! (Validity: {days} Days)")
    else: 
        await update.message.reply_text("❌ **Invalid or Expired code.**")
    return ConversationHandler.END

# --- 6. ADMIN DASHBOARD & STATS ---
def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Code", callback_data="addcode_start"), InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("📁 Add Batch", callback_data="batch_start"), InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_start")],
        [InlineKeyboardButton("🚫 Ban/Unban", callback_data="ban_menu"), InlineKeyboardButton("❌ Cancel Plan", callback_data="action_cancel")],
        [InlineKeyboardButton("📤 Export (File)", callback_data="admin_export"), InlineKeyboardButton("📥 Import", callback_data="import_start")]
    ])

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    await update.message.reply_text("👨‍💻 **Super Admin Dashboard**", reply_markup=get_admin_keyboard())

async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    await update.callback_query.message.edit_text("👨‍💻 **Super Admin Dashboard**", reply_markup=get_admin_keyboard())

async def ban_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    keyboard = [[InlineKeyboardButton("🚫 Ban", callback_data="action_ban")], [InlineKeyboardButton("✅ Unban", callback_data="action_unban")], [InlineKeyboardButton("🔙 Back", callback_data="back_to_admin")]]
    await update.callback_query.message.edit_text("🚫 **Ban / Unban System**", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    t_users = USER_COLLECTION.count_documents({})
    banned = USER_COLLECTION.count_documents({"is_banned": True})
    blocked = USER_COLLECTION.count_documents({"is_blocked": True})
    
    msg = f"📊 **BOT STATISTICS**\n🤖 Started: {t_users}\n🚫 Blocked: {blocked}\n⛔ Banned: {banned}\n\n👇 **View Members List:**"
    keyboard = [[InlineKeyboardButton("🥉 Lite", callback_data="tierstats_lite")], [InlineKeyboardButton("🥈 Premium", callback_data="tierstats_premium")], [InlineKeyboardButton("🥇 Ultra", callback_data="tierstats_ultra")], [InlineKeyboardButton("🔙 Back", callback_data="back_to_admin")]]
    await update.callback_query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_tier_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    tier_req = update.callback_query.data.split('_')[1] 
    now = datetime.datetime.now(IST)
    tier_list = []
    
    users = USER_COLLECTION.find({"tier": tier_req})
    for d in users:
        if d.get("expiry") and datetime.datetime.fromisoformat(d["expiry"]) > now:
            rem = datetime.datetime.fromisoformat(d["expiry"]) - now
            tier_list.append(f"👤 **{d.get('name')}** (`{d['_id']}`)\n⏳ Left: {rem.days} Days")
            
    msg = f"👥 **Total {tier_req.upper()}:** {len(tier_list)}\n\n" + "\n".join(tier_list[:50]) # max 50 for display
    await update.callback_query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_stats")]]))

# --- 7. ADD CODE SYSTEM ---
async def addcode_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    keyboard = [[InlineKeyboardButton("🥉 Lite", callback_data="set_tier_lite")], [InlineKeyboardButton("🥈 Premium", callback_data="set_tier_premium")], [InlineKeyboardButton("🥇 Ultra", callback_data="set_tier_ultra")]]
    await update.callback_query.message.reply_text("1️⃣ **Select Tier:**", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAIT_CODE_DAYS

async def set_code_tier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data['new_code_tier'] = update.callback_query.data.split('_')[2] 
    await update.callback_query.message.reply_text("2️⃣ **How many days?** (Number only):")
    return WAIT_CODE_DAYS 

async def set_code_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_code_days'] = int(update.message.text)
    await update.message.reply_text("3️⃣ **How many uses?** (e.g. 50)")
    return WAIT_CODE_USES

async def set_code_uses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uses, tier, days = int(update.message.text), context.user_data['new_code_tier'], context.user_data['new_code_days']
    code = f"{tier[:3].upper()}-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    CODE_COLLECTION.update_one({"_id": code}, {"$set": {'tier': tier, 'days': days, 'uses_left': uses}}, upsert=True)
    await update.message.reply_text(f"✅ **Code Generated!**\n🎫 `{code}`\n👑 {tier.upper()} | ⏳ {days} Days | 👥 {uses} Uses", parse_mode='Markdown')
    return ConversationHandler.END

# --- 8. BATCH SYSTEM ---
async def batch_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("🔗 First file link:")
    return WAIT_FIRST_LINK

async def batch_first_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['first_link'] = update.message.text
    await update.message.reply_text("🔗 Last file link:")
    return WAIT_LAST_LINK

async def batch_last_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['last_link'] = update.message.text
    await update.message.reply_text("📝 Batch Name (No spaces):")
    return WAIT_BATCH_NAME

async def batch_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['batch_name'] = update.message.text
    keyboard = [[InlineKeyboardButton("🥉 Lite", callback_data="batchtier_lite")], [InlineKeyboardButton("🥈 Premium", callback_data="batchtier_premium")], [InlineKeyboardButton("🥇 Ultra", callback_data="batchtier_ultra")]]
    await update.message.reply_text("👑 Target Plan?", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAIT_BATCH_NAME

async def batch_save_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    tier, name = update.callback_query.data.split('_')[1], context.user_data['batch_name']
    try:
        f_link, l_link = context.user_data['first_link'], context.user_data['last_link']
        c = int("-100" + f_link.split('/')[4])
        s, e = int(f_link.split('/')[5]), int(l_link.split('/')[-1])
        messages = [{'chat_id': c, 'msg_id': i} for i in range(s, e + 1)]
        FILE_COLLECTION.update_one({"_id": name}, {"$set": {'tier': tier, 'messages': messages}}, upsert=True)
        await update.callback_query.message.edit_text(f"✅ **Batch Saved!**\n🔗 Link: https://t.me/{BOT_USERNAME}?start={name}")
    except Exception:
        await update.callback_query.message.edit_text("❌ Error in link.")
    return ConversationHandler.END

# --- 9. BROADCAST & ACTION ---
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("📢 **Broadcast:** Send message:")
    return WAIT_BROADCAST_MSG

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sent, blocked = 0, 0
    await update.message.reply_text("⏳ Sending...")
    for u in USER_COLLECTION.find({"is_banned": {"$ne": True}}):
        try: 
            await context.bot.copy_message(chat_id=u['_id'], from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
            USER_COLLECTION.update_one({"_id": u['_id']}, {"$set": {"is_blocked": False}})
            sent += 1
        except: 
            USER_COLLECTION.update_one({"_id": u['_id']}, {"$set": {"is_blocked": True}})
            blocked += 1
    await update.message.reply_text(f"✅ **Report:**\n📨 Sent: {sent}\n🚫 Blocked: {blocked}")
    return ConversationHandler.END

async def ask_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    context.user_data['admin_action'] = update.callback_query.data.split('_')[1] 
    await update.callback_query.message.edit_text(f"🎯 Send User ID:")
    return WAIT_USER_ID

async def process_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action, uid = context.user_data['admin_action'], int(update.message.text.strip())
    if action == 'ban':
        USER_COLLECTION.update_one({"_id": uid}, {"$set": {"is_banned": True}})
        await update.message.reply_text(f"🚫 User {uid} banned.")
    elif action == 'unban':
        USER_COLLECTION.update_one({"_id": uid}, {"$set": {"is_banned": False}})
        await update.message.reply_text(f"✅ User {uid} unbanned.")
    elif action == 'cancel':
        USER_COLLECTION.update_one({"_id": uid}, {"$unset": {"expiry": "", "tier": ""}})
        await update.message.reply_text(f"❌ User {uid} plan cancelled.")
    return ConversationHandler.END

# --- 10. IMPORT/EXPORT ---
async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    backup_dict = {f["_id"]: {"tier": f.get("tier"), "messages": f.get("messages")} for f in FILE_COLLECTION.find({})}
    bio = io.BytesIO(str(backup_dict).encode('utf-8'))
    bio.name = 'database_backup.txt'
    await context.bot.send_document(chat_id=update.effective_chat.id, document=bio, caption="📂 **Database Backup (MongoDB)**")

async def import_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("📥 Send your backup `.txt` file:")
    return WAIT_IMPORT_DATA

async def process_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        f = io.BytesIO()
        await (await context.bot.get_file(update.message.document.file_id)).download_to_memory(out=f)
        data_str = f.getvalue().decode('utf-8')
        imported_data = eval(data_str[data_str.find('{'):data_str.rfind('}')+1])
        
        for key, value in imported_data.items():
            tier = 'lite' if isinstance(value, list) else value.get('tier', 'lite')
            msgs = value if isinstance(value, list) else value.get('messages', [])
            FILE_COLLECTION.update_one({"_id": key}, {"$set": {'tier': tier, 'messages': msgs}}, upsert=True)
            
        await update.message.reply_text("✅ **Data imported to Cloud DB!**")
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")
    return ConversationHandler.END

async def catch_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    msg_id = update.message.message_id
    keyboard = [[InlineKeyboardButton("🥉 Lite File", callback_data=f"savefile_lite_{msg_id}")], [InlineKeyboardButton("🥇 Ultra File", callback_data=f"savefile_ultra_{msg_id}")]]
    await update.message.reply_text("📁 Select Plan:", reply_markup=InlineKeyboardMarkup(keyboard))

async def save_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    d = update.callback_query.data.split('_')
    key = f"file_{d[2]}"
    FILE_COLLECTION.update_one({"_id": key}, {"$set": {'tier': d[1], 'messages': [{'chat_id': update.effective_chat.id, 'msg_id': int(d[2])}]}}, upsert=True)
    await update.callback_query.message.edit_text(f"✅ File Saved!\n🔗 https://t.me/{BOT_USERNAME}?start={key}")

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ **Process cancelled.**")
    return ConversationHandler.END

# --- APP SETUP ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin_panel))
app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(redeem_start, pattern='^redeem_start$')], states={WAIT_REDEEM_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_redeem)]}, fallbacks=[CommandHandler('cancel', cancel_conv)]))
app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(addcode_start, pattern='^addcode_start$')], states={WAIT_CODE_DAYS: [CallbackQueryHandler(set_code_tier, pattern='^set_tier_'), MessageHandler(filters.TEXT & ~filters.COMMAND, set_code_days)], WAIT_CODE_USES: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_code_uses)]}, fallbacks=[CommandHandler('cancel', cancel_conv)]))
app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(batch_start, pattern='^batch_start$')], states={WAIT_FIRST_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_first_link)], WAIT_LAST_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_last_link)], WAIT_BATCH_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_name), CallbackQueryHandler(batch_save_final, pattern='^batchtier_')]}, fallbacks=[CommandHandler('cancel', cancel_conv)]))
app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(broadcast_start, pattern='^broadcast_start$')], states={WAIT_BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, process_broadcast)]}, fallbacks=[CommandHandler('cancel', cancel_conv)]))
app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(ask_user_id, pattern='^action_')], states={WAIT_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_action)]}, fallbacks=[CommandHandler('cancel', cancel_conv)]))
app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(import_start, pattern='^import_start$')], states={WAIT_IMPORT_DATA: [MessageHandler(filters.Document.ALL & ~filters.COMMAND, process_import)]}, fallbacks=[CommandHandler('cancel', cancel_conv)]))
app.add_handler(CallbackQueryHandler(ban_menu, pattern='^ban_menu$'))
app.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
app.add_handler(CallbackQueryHandler(show_tier_stats, pattern='^tierstats_'))
app.add_handler(CallbackQueryHandler(back_to_admin, pattern='^back_to_admin$'))
app.add_handler(CallbackQueryHandler(admin_export, pattern='^admin_export$'))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, catch_file))
app.add_handler(CallbackQueryHandler(save_file_callback, pattern='^savefile_'))

print("Prince Cloud Bot Started! 🔥")
app.run_polling()
