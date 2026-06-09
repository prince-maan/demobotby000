from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import datetime
import pytz
import os
import random
import string
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
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = [8820964089, 8895101534]
BOT_USERNAME = "smallPinkVide00s_bot" 
BUY_LINK = "https://t.me/SaulGoodmanOp"
# 👇 यहाँ अपने प्राइवेट मास्टर चैनल की ID डालें (-100 से शुरू होनी चाहिए)
DB_CHANNEL_ID = -1000000000000 

IST = pytz.timezone('Asia/Kolkata')
TIERS = {'lite': 1, 'premium': 2, 'ultra': 3}

# --- 3. MONGODB DATABASE ---
MONGO_URI = "mongodb+srv://walter1122op_db_user:7b9QH8JrydXngsHi@cluster0.h4nwnyc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = pymongo.MongoClient(MONGO_URI)
db = client["TelegramBotDB"]

USER_COLLECTION = db["Prince_Users"]
FILE_COLLECTION = db["common_files"]
CODE_COLLECTION = db["Prince_Codes"]

(WAIT_REDEEM_CODE, WAIT_CODE_DAYS, WAIT_CODE_USES, WAIT_FIRST_LINK, WAIT_LAST_LINK, WAIT_BATCH_NAME, WAIT_BROADCAST_MSG, WAIT_USER_ID) = range(8)

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
                
                # Fixed Singular Loop (No Crash)
                success = 0
                err_msg = ""
                for m_id in msg_ids:
                    try:
                        await context.bot.copy_message(chat_id=user.id, from_chat_id=source_chat, message_id=m_id, protect_content=True)
                        success += 1
                    except Exception as e:
                        err_msg = str(e)
                
                if success == 0:
                    await update.message.reply_text(f"❌ **Error sending file.**\nChannel ID या Admin राइट्स चेक करें।\nReason: {err_msg}")
            else:
                keyboard = [[InlineKeyboardButton("💎 Upgrade Membership", url=BUY_LINK)]]
                await update.message.reply_text(f"🛑 **Access Denied!**\n\nThis is a **{file_tier.upper()}** file, but your current plan is **{user_tier.upper()}**.\nइसे देखने के लिए कृपया अपनी मेंबरशिप अपग्रेड करें।", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else: 
            await update.message.reply_text("❌ **File not found.**\nफाइल नहीं मिली।")
    else: 
        status, tier_msg = "Inactive 🔴", "None"
        if u_doc.get("expiry") and datetime.datetime.fromisoformat(u_doc["expiry"]) > now:
            status, tier_msg = "Active 🟢", u_doc.get('tier', 'lite').upper()
            
        keyboard = [[InlineKeyboardButton("💰 Buy Membership", url=BUY_LINK)], [InlineKeyboardButton("🎫 Redeem Code", callback_data="redeem_start")]]
        await update.message.reply_text(f"👋 **Welcome {user.first_name}!**\n\n👤 **Status:** {status}\n👑 **Current Plan:** {tier_msg}\n\n🎬 प्रीमियम वीडियो देखने के लिए कृपया मेंबरशिप खरीदें या अपना प्रोमो कोड रिडीम करें।", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- 5. REDEEM SYSTEM ---
async def redeem_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("✍️ **Please type and send your promo code:**\nकृपया अपना प्रोमो कोड टाइप करके भेजें:\n\n(Send /cancel to abort)")
    return WAIT_REDEEM_CODE

async def process_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    code = update.message.text.strip()
    c_doc = CODE_COLLECTION.find_one({"_id": code})
    
    if c_doc and c_doc['uses_left'] > 0:
        tier, days = c_doc['tier'], c_doc['days']
        CODE_COLLECTION.update_one({"_id": code}, {"$inc": {"uses_left": -1}})
        now = datetime.datetime.now(IST)
        expiry_str = (now + datetime.timedelta(days=days)).isoformat()
        
        USER_COLLECTION.update_one({"_id": user.id}, {"$set": {'name': user.first_name, 'username': user.username, 'tier': tier, 'code': code, 'expiry': expiry_str, 'join_date': now.strftime("%Y-%m-%d %I:%M %p")}}, upsert=True)
        await update.message.reply_text(f"🎉 **Congratulations! / बधाई हो!**\n\nYour **{tier.upper()}** plan has been successfully activated! (Validity: {days} Days)")
    else: 
        await update.message.reply_text("❌ **Invalid or Expired code.**\nकोड गलत है या एक्सपायर हो चुका है।")
    return ConversationHandler.END

# --- 6. ADMIN DASHBOARD & FULL STATS ---
def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Code", callback_data="addcode_start"), InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("📁 Add Batch", callback_data="batch_start"), InlineKeyboardButton("📢 Broadcast", callback_data="broadcast_start")],
        [InlineKeyboardButton("🚫 Ban/Unban", callback_data="ban_menu"), InlineKeyboardButton("❌ Cancel Plan", callback_data="action_cancel")]
    ])

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    await update.message.reply_text("👨‍💻 **Super Admin Dashboard**\nक्या करना चाहते हैं?", reply_markup=get_admin_keyboard())

async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    await update.callback_query.message.edit_text("👨‍💻 **Super Admin Dashboard**\nक्या करना चाहते हैं?", reply_markup=get_admin_keyboard())

async def ban_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    keyboard = [[InlineKeyboardButton("🚫 Ban User", callback_data="action_ban")], [InlineKeyboardButton("✅ Unban User", callback_data="action_unban")], [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_to_admin")]]
    await update.callback_query.message.edit_text("🚫 **Ban / Unban System**\n\nआप क्या करना चाहते हैं?", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    t_users = USER_COLLECTION.count_documents({})
    blocked = USER_COLLECTION.count_documents({"is_blocked": True})
    banned = USER_COLLECTION.count_documents({"is_banned": True})
    
    msg = (f"📊 **BOT STATISTICS**\n\n🤖 **बॉट स्टार्ट किया:** {t_users} लोगों ने\n🚫 **बॉट को ब्लॉक किया:** {blocked} लोगों ने\n⛔ **बैन किए गए यूज़र्स:** {banned} लोगों ने\n\n👇 **किस प्लान के मेंबर्स की लिस्ट देखनी है?**")
    keyboard = [[InlineKeyboardButton("🥉 Lite", callback_data="tierstats_lite"), InlineKeyboardButton("🥈 Premium", callback_data="tierstats_premium")], [InlineKeyboardButton("🥇 Ultra", callback_data="tierstats_ultra"), InlineKeyboardButton("🔙 Back", callback_data="back_to_admin")]]
    await update.callback_query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def show_tier_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    tier_req = update.callback_query.data.split('_')[1] 
    now = datetime.datetime.now(IST)
    tier_list = []
    
    for d in USER_COLLECTION.find({"tier": tier_req}):
        if d.get("expiry") and datetime.datetime.fromisoformat(d["expiry"]) > now:
            rem = datetime.datetime.fromisoformat(d["expiry"]) - now
            uname = f"@{d.get('username')}" if d.get('username') else "N/A"
            tier_list.append(f"👤 **{d.get('name')}** ({uname} | ID: `{d['_id']}`)\n🎫 **Code:** `{d.get('code', 'N/A')}` | 📅 **Joined:** {d.get('join_date', 'N/A')}\n⏳ **Left:** {rem.days} Days, {rem.seconds//3600} Hours\n━━━━━━━━━━━━━━━")
            
    emojis = {'lite': '🥉', 'premium': '🥈', 'ultra': '🥇'}
    msg = f"{emojis[tier_req]} **{tier_req.upper()} MEMBERS**\n\n👥 **Total {tier_req.upper()} Users:** {len(tier_list)}\n\n"
    if tier_list: msg += "\n".join(tier_list)
    else: msg += f"🔹 अभी कोई {tier_req.upper()} मेंबर नहीं है।"
        
    keyboard = [[InlineKeyboardButton("🔙 Back to Stats", callback_data="admin_stats")]]
    if len(msg) > 4000:
        await update.callback_query.message.delete()
        for x in range(0, len(msg), 4000):
            if x + 4000 >= len(msg): await context.bot.send_message(chat_id=update.effective_chat.id, text=msg[x:x+4000], parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            else: await context.bot.send_message(chat_id=update.effective_chat.id, text=msg[x:x+4000], parse_mode='Markdown')
    else: await update.callback_query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- 7. ADD CODE SYSTEM ---
async def addcode_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    keyboard = [[InlineKeyboardButton("🥉 Lite", callback_data="set_tier_lite")], [InlineKeyboardButton("🥈 Premium", callback_data="set_tier_premium")], [InlineKeyboardButton("🥇 Ultra", callback_data="set_tier_ultra")]]
    await update.callback_query.message.reply_text("1️⃣ **प्लान (Tier) चुनें:**", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAIT_CODE_DAYS

async def set_code_tier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data['new_code_tier'] = update.callback_query.data.split('_')[2] 
    await update.callback_query.message.reply_text(f"✅ प्लान **{context.user_data['new_code_tier'].upper()}** चुना गया।\n\n2️⃣ **कितने दिनों के लिए?** (केवल अंक):")
    return WAIT_CODE_DAYS 

async def set_code_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_code_days'] = int(update.message.text)
    await update.message.reply_text("3️⃣ **कितने लोग इसे यूज़ कर सकते हैं?** (जैसे: 50)")
    return WAIT_CODE_USES

async def set_code_uses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uses, tier, days = int(update.message.text), context.user_data['new_code_tier'], context.user_data['new_code_days']
    code = f"{tier[:3].upper()}-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    CODE_COLLECTION.update_one({"_id": code}, {"$set": {'tier': tier, 'days': days, 'uses_left': uses}}, upsert=True)
    await update.message.reply_text(f"✅ **नया कोड तैयार!**\n🎫 `{code}`\n👑 {tier.upper()} | ⏳ {days} Days | 👥 {uses} Uses", parse_mode='Markdown')
    return ConversationHandler.END

# --- 8. SMART BATCH UPLOAD SYSTEM ---
async def batch_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("🔗 **Step 1:** कृपया पहली फाइल का लिंक (First Link) भेजें:")
    return WAIT_FIRST_LINK

async def batch_first_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['first_link'] = update.message.text
    await update.message.reply_text("🔗 **Step 2:** अब आखिरी फाइल का लिंक (Last Link) भेजें:")
    return WAIT_LAST_LINK

async def batch_last_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['last_link'] = update.message.text
    await update.message.reply_text("📝 **Step 3:** इस बैच का एक नाम (Name/ID) दें (बिना स्पेस के):")
    return WAIT_BATCH_NAME

async def batch_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['batch_name'] = update.message.text
    keyboard = [[InlineKeyboardButton("🥉 Lite", callback_data="batchtier_lite")], [InlineKeyboardButton("🥈 Premium", callback_data="batchtier_premium")], [InlineKeyboardButton("🥇 Ultra", callback_data="batchtier_ultra")]]
    await update.message.reply_text("👑 **Step 4:** यह बैच किस प्लान के लिए है?", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAIT_BATCH_NAME

async def batch_save_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    tier, name = update.callback_query.data.split('_')[1], context.user_data['batch_name']
    try:
        parts_f = context.user_data['first_link'].split('/')
        parts_l = context.user_data['last_link'].split('/')
        
        c = int("-100" + parts_f[-2]) if 'c' in parts_f else "@" + parts_f[-2]
        s, e = int(parts_f[-1].split('?')[0]), int(parts_l[-1].split('?')[0])
        
        messages = [{'chat_id': c, 'msg_id': i} for i in range(s, e + 1)]
        FILE_COLLECTION.update_one({"_id": name}, {"$set": {'tier': tier, 'messages': messages}}, upsert=True)
        await update.callback_query.message.edit_text(f"✅ **बैच ({tier.upper()}) सेव हो गया!**\n🔗 लिंक: https://t.me/{BOT_USERNAME}?start={name}")
    except Exception as e:
        await update.callback_query.message.edit_text(f"❌ लिंक में कोई समस्या है। एरर: {e}")
    return ConversationHandler.END

# --- 9. BROADCAST, BAN/UNBAN, CANCEL ---
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("📢 **Broadcast:**\nकृपया वह मैसेज/फोटो/वीडियो भेजें जो आप सभी को भेजना चाहते हैं:")
    return WAIT_BROADCAST_MSG

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sent, blocked = 0, 0
    await update.message.reply_text("⏳ भेज रहा हूँ...")
    for u in USER_COLLECTION.find({"is_banned": {"$ne": True}}):
        try: 
            await context.bot.copy_message(chat_id=u['_id'], from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
            USER_COLLECTION.update_one({"_id": u['_id']}, {"$set": {"is_blocked": False}})
            sent += 1
        except: 
            USER_COLLECTION.update_one({"_id": u['_id']}, {"$set": {"is_blocked": True}})
            blocked += 1
    await update.message.reply_text(f"✅ **रिपोर्ट:**\n📨 भेजे गए: {sent}\n🚫 ब्लॉक किए गए: {blocked}")
    return ConversationHandler.END

async def ask_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    action = update.callback_query.data.split('_')[1] 
    context.user_data['admin_action'] = action
    action_text = {"cancel": "कैंसिल", "ban": "बैन", "unban": "अनबैन"}[action]
    await update.callback_query.message.edit_text(f"🎯 **{action_text.upper()} USER**\n\nकृपया उस यूज़र की **टेलीग्राम ID** भेजें जिसे आप {action_text} करना चाहते हैं:\n\n(रद्द करने के लिए /cancel लिखें)")
    return WAIT_USER_ID

async def process_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text, action = update.message.text.strip(), context.user_data['admin_action']
    try: uid = int(input_text)
    except: 
        await update.message.reply_text("❌ गलत इनपुट! कृपया सही ID भेजें।")
        return ConversationHandler.END
        
    if action == 'ban':
        USER_COLLECTION.update_one({"_id": uid}, {"$set": {"is_banned": True}})
        await update.message.reply_text(f"🚫 यूज़र (ID: `{uid}`) को बैन कर दिया गया है।", parse_mode='Markdown')
    elif action == 'unban':
        USER_COLLECTION.update_one({"_id": uid}, {"$set": {"is_banned": False}})
        await update.message.reply_text(f"✅ यूज़र (ID: `{uid}`) को अनबैन कर दिया गया है।", parse_mode='Markdown')
    elif action == 'cancel':
        USER_COLLECTION.update_one({"_id": uid}, {"$unset": {"expiry": "", "tier": ""}})
        await update.message.reply_text(f"❌ यूज़र (ID: `{uid}`) का प्रीमियम प्लान कैंसिल कर दिया गया है।", parse_mode='Markdown')
    return ConversationHandler.END

# --- 10. SINGLE FILE HANDLER (AUTO-FORWARD TO DB_CHANNEL) ---
async def catch_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    
    try:
        copied_msg = await context.bot.copy_message(
            chat_id=DB_CHANNEL_ID,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
        ch_msg_id = copied_msg.message_id
    except Exception as e:
        await update.message.reply_text(f"❌ **Error:**\nक्या आपने बॉट को मास्टर चैनल में Admin बनाया है और DB_CHANNEL_ID सही डाली है?\nError: {e}")
        return

    keyboard = [
        [InlineKeyboardButton("🥉 Lite File", callback_data=f"savefile_lite_{ch_msg_id}")],
        [InlineKeyboardButton("🥈 Premium File", callback_data=f"savefile_premium_{ch_msg_id}")],
        [InlineKeyboardButton("🥇 Ultra File", callback_data=f"savefile_ultra_{ch_msg_id}")]
    ]
    await update.message.reply_text("📁 फाइल मास्टर चैनल में बैकअप हो गई है। यह फाइल किस प्लान के लिए है?", reply_markup=InlineKeyboardMarkup(keyboard))

async def save_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id not in ADMIN_IDS: return
    await update.callback_query.answer()
    d = update.callback_query.data.split('_') 
    tier = d[1]
    msg_id = int(d[2])
    key = f"file_{msg_id}"
    
    FILE_COLLECTION.update_one({"_id": key}, {"$set": {'tier': tier, 'messages': [{'chat_id': DB_CHANNEL_ID, 'msg_id': msg_id}]}}, upsert=True)
    await update.callback_query.message.edit_text(f"✅ फाइल **{tier.upper()}** के लिए सेव!\n🔗 लिंक: https://t.me/{BOT_USERNAME}?start={key}")

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ **Process cancelled.** / प्रक्रिया रद्द कर दी गई है।")
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
app.add_handler(CallbackQueryHandler(ban_menu, pattern='^ban_menu$'))
app.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
app.add_handler(CallbackQueryHandler(show_tier_stats, pattern='^tierstats_'))
app.add_handler(CallbackQueryHandler(back_to_admin, pattern='^back_to_admin$'))
app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO | filters.PHOTO | filters.AUDIO | filters.ANIMATION, catch_file))
app.add_handler(CallbackQueryHandler(save_file_callback, pattern='^savefile_'))

print("Prince Bot Started! 🔥")
app.run_polling(drop_pending_updates=True)
