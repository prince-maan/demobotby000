import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo
import sqlite3
import json
import uuid
import threading
import os
from datetime import datetime
from flask import Flask

# ==========================================
# 🛑 आपकी मुख्य सेटिंग्स 🛑
# ==========================================
BOT_TOKEN = "8986044820:AAH_NrdyJ1A0ZCsSwPoQ4PuWdLNWXSUYB3U"
ADMIN_ID = 8994976810  # आपका Telegram User ID
DB_CHANNEL_ID = -1003757631353  # आपके प्राइवेट डेटाबेस चैनल की ID

# डायरेक्ट लिंक्स
CHAT_LINK = "https://t.me/princemaan00"
INTERNATIONAL_LINK = "https://t.me/princemaan00"

bot = telebot.TeleBot(BOT_TOKEN)

# --- डेटाबेस और बैकअप ---
DB_FILE = "shop_master_v5.db"
BACKUP_FILE = "master_backup_v5.json"

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, item_info TEXT, date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS courses (course_id TEXT PRIMARY KEY, promo_media TEXT, qr_file_id TEXT, amount TEXT, custom_caption TEXT, secret_text TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS batches (batch_id TEXT PRIMARY KEY, title TEXT, course_ids TEXT)''')
        conn.commit()
init_db()

def load_backup():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"courses": {}, "batches": {}}

def save_backup(data):
    with open(BACKUP_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def get_course_data(course_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM courses WHERE course_id=?", (course_id,))
        row = cursor.fetchone()
        if row: return dict(row)
    return load_backup().get("courses", {}).get(course_id)

def get_batch_data(batch_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,))
        row = cursor.fetchone()
        if row: return dict(row)
    return load_backup().get("batches", {}).get(batch_id)

# --- स्टेट मैनेजमेंट ---
admin_data = {} 
user_states = {} 
user_qr_messages = {} 
pending_verifications = {} # 5-min tracking के लिए

# --- Timers (10 Min QR, 5 Min Verification) ---
def expire_qr(chat_id, message_id, course_id):
    if user_states.get(chat_id) == course_id:
        try:
            bot.delete_message(chat_id, message_id)
            bot.send_message(chat_id, "❌ **आपका पेमेंट सेशन (10 मिनट) एक्सपायर हो गया है!**\nकृपया फिर से शुरुआत करें।")
            del user_states[chat_id]
        except: pass

def expire_verification(user_id, checking_msg_id, admin_msg_id, course_id):
    if user_id in pending_verifications and pending_verifications[user_id].get('course_id') == course_id:
        try: bot.delete_message(user_id, checking_msg_id)
        except: pass
        
        try: bot.edit_message_caption("❌ **Auto-Expired (5 Mins)** - No Action Taken", chat_id=DB_CHANNEL_ID, message_id=admin_msg_id, reply_markup=None)
        except: pass
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("💬 डायरेक्ट संपर्क करें", url=CHAT_LINK))
        try: bot.send_message(user_id, "⏳ **समय समाप्त!**\nएडमिन की तरफ से 5 मिनट में अप्रूवल नहीं मिला है। कृपया सीधे चैट पर संपर्क करें:", reply_markup=markup)
        except: pass
        
        del pending_verifications[user_id]

# --- कोर्स सेंड करने का मास्टर फंक्शन (एल्बम + बटन्स) ---
def send_course_to_user(chat_id, course):
    promo_items = json.loads(course['promo_media'])
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton(f"🇮🇳 UPI (Pay {course['amount']})", callback_data=f"pay_upi_{course['course_id']}"))
    markup.row(InlineKeyboardButton("🌍 International", url=INTERNATIONAL_LINK), InlineKeyboardButton("💬 Chat with Me", url=CHAT_LINK))

    if len(promo_items) == 1:
        item = promo_items[0]
        if item['type'] == 'photo': bot.send_photo(chat_id, item['file_id'], caption=item.get('caption',''), reply_markup=markup, parse_mode="Markdown")
        elif item['type'] == 'video': bot.send_video(chat_id, item['file_id'], caption=item.get('caption',''), reply_markup=markup, parse_mode="Markdown")
        elif item['type'] == 'text': bot.send_message(chat_id, item['caption'], reply_markup=markup, parse_mode="Markdown")
    else:
        media_group = []
        for i, item in enumerate(promo_items):
            cap = item.get('caption', '') if i == 0 else "" # कैप्शन सिर्फ पहले पर
            if item['type'] == 'photo': media_group.append(InputMediaPhoto(item['file_id'], caption=cap, parse_mode="Markdown"))
            elif item['type'] == 'video': media_group.append(InputMediaVideo(item['file_id'], caption=cap, parse_mode="Markdown"))
        
        if media_group:
            try: bot.send_media_group(chat_id, media_group)
            except: pass
        bot.send_message(chat_id, f"👆 **इस कोर्स ({course['amount']}) को खरीदने के लिए विकल्प चुनें:**", reply_markup=markup, parse_mode="Markdown")

# ==========================================
# 1. स्टार्ट कमांड
# ==========================================
@bot.message_handler(commands=['start'])
def start_command(message):
    param = message.text.split()[1].strip() if len(message.text.split()) > 1 else ""
    user_id = message.chat.id
    
    if param.startswith("b_"):
        batch = get_batch_data(param)
        if batch:
            bot.send_message(user_id, f"📦 **{batch['title']}**\nनीचे सभी कोर्सेज दिए गए हैं:", parse_mode="Markdown")
            course_ids = json.loads(batch['course_ids'])
            for cid in course_ids:
                c_data = get_course_data(cid)
                if c_data: send_course_to_user(user_id, c_data)
        else: bot.send_message(user_id, "❌ यह बैच लिंक एक्सपायर हो गया है।")
                
    elif param.startswith("c_"):
        course = get_course_data(param)
        if course: send_course_to_user(user_id, course)
        else: bot.send_message(user_id, "❌ यह लिंक उपलब्ध नहीं है।")
    else:
        if user_id == ADMIN_ID: send_admin_panel(user_id)
        else: bot.send_message(user_id, "नमस्कार! कृपया कोर्स के सही लिंक पर क्लिक करके आएँ।")

def send_admin_panel(chat_id):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ Add Single Course", callback_data="admin_add_course"))
    markup.row(InlineKeyboardButton("📦 Course Batch (मल्टी-कोर्स)", callback_data="admin_create_batch"))
    markup.row(InlineKeyboardButton("👥 User Info", callback_data="admin_user_info"))
    bot.send_message(chat_id, "🛠 **एडमिन पैनल**\nकृपया कोई विकल्प चुनें:", reply_markup=markup)

# ==========================================
# 2. एडमिन मैसेज हैंडलर (Unified State Machine)
# ==========================================
@bot.message_handler(content_types=['photo', 'video', 'document', 'text'])
def handle_all_messages(message):
    user_id = message.chat.id
    
    # --- ADMIN CREATION FLOW ---
    if user_id == ADMIN_ID and user_id in admin_data:
        step = admin_data[ADMIN_ID].get('step')
        
        if step == 'TITLE':
            admin_data[ADMIN_ID]['title'] = message.text.strip()
            admin_data[ADMIN_ID]['step'] = 'PROMO'
            admin_data[ADMIN_ID]['promo'] = []
            bot.send_message(ADMIN_ID, f"✅ बैच टाइटल सेव: **{admin_data[ADMIN_ID]['title']}**\n\n📝 **पहले कोर्स का प्रोमो मीडिया भेजें (फोटो/वीडियो)।**\n(भेजने के बाद नीचे 'Next' बटन दबाएं)", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("➡️ Next Step", callback_data="next_qr")))
            return

        elif step == 'PROMO':
            media_type, file_id = 'text', None
            if message.photo: media_type, file_id = 'photo', message.photo[-1].file_id
            elif message.video: media_type, file_id = 'video', message.video.file_id
            admin_data[ADMIN_ID]['promo'].append({'type': media_type, 'file_id': file_id, 'caption': message.caption or message.text or ""})
            return

        elif step == 'QR':
            if message.photo:
                admin_data[ADMIN_ID]['qr'] = message.photo[-1].file_id
                admin_data[ADMIN_ID]['step'] = 'AMOUNT'
                bot.send_message(ADMIN_ID, "✅ **QR Code सेव!**\n\n💰 अब इस कोर्स की कीमत भेजें (जैसे: ₹299):")
            else: bot.send_message(ADMIN_ID, "❌ कृपया QR कोड की **फोटो** भेजें।")
            return
            
        elif step == 'AMOUNT':
            admin_data[ADMIN_ID]['amount'] = message.text.strip()
            admin_data[ADMIN_ID]['step'] = 'CAPTION'
            markup = InlineKeyboardMarkup().row(InlineKeyboardButton("⏭ Skip (कोई कैप्शन नहीं)", callback_data="skip_caption"))
            bot.send_message(ADMIN_ID, "✅ **अमाउंट सेव!**\n\n📝 कोई अतिरिक्त कैप्शन भेजना है तो टाइप करें, वरना 'Skip' दबाएं।", reply_markup=markup)
            return

        elif step == 'CAPTION':
            admin_data[ADMIN_ID]['caption'] = message.text.strip()
            admin_data[ADMIN_ID]['step'] = 'SECRET'
            bot.send_message(ADMIN_ID, "✅ **कैप्शन सेव!**\n\n🔗 अब इसका फाइनल सीक्रेट लिंक/मैसेज भेजें:")
            return

        elif step == 'SECRET':
            secret = message.text.strip()
            course_id = "c_" + str(uuid.uuid4())[:6]
            promo_json = json.dumps(admin_data[ADMIN_ID]['promo'])
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO courses VALUES (?, ?, ?, ?, ?, ?)", (course_id, promo_json, admin_data[ADMIN_ID]['qr'], admin_data[ADMIN_ID]['amount'], admin_data[ADMIN_ID]['caption'], secret))
                conn.commit()
            
            bk = load_backup()
            bk["courses"][course_id] = {"promo_media": promo_json, "qr_file_id": admin_data[ADMIN_ID]['qr'], "amount": admin_data[ADMIN_ID]['amount'], "custom_caption": admin_data[ADMIN_ID]['caption'], "secret_text": secret}
            save_backup(bk)

            mode = admin_data[ADMIN_ID].get('mode')
            if mode == 'single':
                link = f"https://t.me/{bot.get_me().username}?start={course_id}"
                bot.send_message(ADMIN_ID, f"🎉 **कोर्स बन गया!**\n👉 `{link}`", parse_mode="Markdown")
                del admin_data[ADMIN_ID]
                send_admin_panel(ADMIN_ID)
            
            elif mode == 'batch':
                admin_data[ADMIN_ID]['course_ids'].append(course_id)
                admin_data[ADMIN_ID]['step'] = 'NEXT_ACTION'
                markup = InlineKeyboardMarkup()
                markup.row(InlineKeyboardButton("➕ Add Another Course", callback_data="batch_add_next"))
                markup.row(InlineKeyboardButton("✅ Finish Batch", callback_data="batch_finish"))
                bot.send_message(ADMIN_ID, f"✅ **कोर्स सेव हो गया! (Total: {len(admin_data[ADMIN_ID]['course_ids'])})**\n\nक्या आप इस बैच में एक और कोर्स जोड़ना चाहते हैं?", reply_markup=markup)
            return

    # --- USER: PAYMENT SCREENSHOT ---
    if user_id in user_states and message.photo:
        course_id = user_states[user_id]
        
        if user_id in user_qr_messages:
            try: bot.delete_message(user_id, user_qr_messages[user_id]); del user_qr_messages[user_id]
            except: pass
            
        first_name = message.from_user.first_name or "User"
        username = f"(@{message.from_user.username})" if message.from_user.username else ""
        
        check_msg = bot.send_message(user_id, "⏳ आपका स्क्रीनशॉट मिल गया है। 5 मिनट के अंदर अप्रूव हो जाएगा...")
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("✅ Approve", callback_data=f"app_{user_id}_{course_id}"))
        markup.row(InlineKeyboardButton("❌ Deny", callback_data=f"den_{user_id}_{course_id}"))
        admin_text = f"🔔 **New Verification!**\n👤 User: {first_name} {username}\n🆔 ID: `{user_id}`\n📚 Course: `{course_id}`"
        
        try:
            admin_msg = bot.send_photo(DB_CHANNEL_ID, photo=message.photo[-1].file_id, caption=admin_text, reply_markup=markup, parse_mode="Markdown")
            
            pending_verifications[user_id] = {
                'checking_msg_id': check_msg.message_id,
                'admin_msg_id': admin_msg.message_id,
                'course_id': course_id
            }
            threading.Timer(300, expire_verification, args=(user_id, check_msg.message_id, admin_msg.message_id, course_id)).start()
        except Exception as e:
            bot.send_message(ADMIN_ID, f"⚠️ चैनल एरर: {e}")
        
        del user_states[user_id]
    elif user_id in user_states and not message.photo:
        bot.send_message(user_id, "❌ कृपया पेमेंट का स्क्रीनशॉट (फोटो) भेजें।")

# ==========================================
# 3. सभी बटन्स को हैंडल करना
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    bot.answer_callback_query(call.id)
    
    # --- ADMIN START ACTIONS ---
    if data == "admin_add_course":
        admin_data[ADMIN_ID] = {'mode': 'single', 'step': 'PROMO', 'promo': [], 'qr': None, 'amount': None, 'caption': ""}
        markup = InlineKeyboardMarkup().row(InlineKeyboardButton("➡️ Next Step", callback_data="next_qr"))
        bot.edit_message_text("📝 **Step 1/5: प्रोमो मीडिया**\nगैलरी से डेमो फोटो/वीडियो भेजें (एल्बम के लिए एक साथ चुनें)। फिर 'Next Step' दबाएं।", chat_id=chat_id, message_id=msg_id, reply_markup=markup)
        
    elif data == "admin_create_batch":
        admin_data[ADMIN_ID] = {'mode': 'batch', 'step': 'TITLE', 'course_ids': []}
        bot.edit_message_text("📦 **नया कोर्स बैच (Course Batch) बनाएँ**\n\nकृपया इस बैच का **नाम/टाइटल** टाइप करके भेजें:", chat_id=chat_id, message_id=msg_id)

    # --- ADMIN NAVIGATION ---
    elif data == "next_qr":
        if ADMIN_ID not in admin_data or not admin_data[ADMIN_ID].get('promo'):
            bot.answer_callback_query(call.id, "❌ पहले मीडिया भेजें!", show_alert=True)
            return
        admin_data[ADMIN_ID]['step'] = 'QR'
        bot.edit_message_text("✅ मीडिया सेव!\n\n📷 **Step 2/5: पेमेंट QR कोड**\nअपना UPI QR Code (फोटो) भेजें।", chat_id=chat_id, message_id=msg_id)
        
    elif data == "skip_caption":
        if ADMIN_ID in admin_data:
            admin_data[ADMIN_ID]['caption'] = ""
            admin_data[ADMIN_ID]['step'] = 'SECRET'
            bot.edit_message_text("✅ **कैप्शन स्किप!**\n\n🔗 **Step 5/5: फाइनल लिंक**\nफाइनल सीक्रेट लिंक भेजें।", chat_id=chat_id, message_id=msg_id)

    elif data == "batch_add_next":
        admin_data[ADMIN_ID]['step'] = 'PROMO'
        admin_data[ADMIN_ID]['promo'] = []
        admin_data[ADMIN_ID]['qr'] = None
        admin_data[ADMIN_ID]['caption'] = ""
        markup = InlineKeyboardMarkup().row(InlineKeyboardButton("➡️ Next Step", callback_data="next_qr"))
        bot.edit_message_text(f"📝 **अगले कोर्स का प्रोमो मीडिया भेजें**\nफिर 'Next Step' दबाएं।", chat_id=chat_id, message_id=msg_id, reply_markup=markup)

    elif data == "batch_finish":
        d = admin_data.get(ADMIN_ID)
        if not d or not d.get('course_ids'): return
        
        batch_id = "b_" + str(uuid.uuid4())[:6]
        c_ids_json = json.dumps(d['course_ids'])
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO batches VALUES (?, ?, ?)", (batch_id, d['title'], c_ids_json))
            conn.commit()
            
        bk = load_backup()
        bk["batches"][batch_id] = {"batch_id": batch_id, "title": d['title'], "course_ids": c_ids_json}
        save_backup(bk)
        
        link = f"https://t.me/{bot.get_me().username}?start={batch_id}"
        bot.edit_message_text(f"🎉 **कोर्स बैच सफलतापूर्वक बन गया!**\n\n📦 **Title:** {d['title']}\n📚 **Total Courses:** {len(d['course_ids'])}\n\n👉 `{link}` 👈", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")
        del admin_data[ADMIN_ID]
        send_admin_panel(ADMIN_ID)

    # --- ADMIN USER INFO ---
    elif data == "admin_user_info":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, date, item_info FROM purchases ORDER BY id DESC LIMIT 15")
            records = cursor.fetchall()
            
        if not records: bot.edit_message_text("अभी तक किसी ने कोर्स नहीं खरीदा है।", chat_id=chat_id, message_id=msg_id)
        else:
            text = "👥 **Recent Buyers:**\n\n"
            for r in records: text += f"👤 {r['username']} | 📅 {r['date'][:10]} | 📚 `{r['item_info']}`\n"
            markup = InlineKeyboardMarkup().row(InlineKeyboardButton("🔙 Back", callback_data="back_to_admin"))
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="Markdown")
            
    elif data == "back_to_admin":
        try: bot.delete_message(chat_id, msg_id)
        except: pass
        send_admin_panel(chat_id)

    # --- USER: UPI QR VIEW ---
    elif data.startswith("pay_upi_"):
        course_id = data.replace("pay_upi_", "")
        course = get_course_data(course_id)
        if course:
            user_states[chat_id] = course_id
            first_name = call.from_user.first_name or "User"
            username = f"(@{call.from_user.username})" if call.from_user.username else ""
            
            invoice_text = f"👤 **Name:** {first_name} {username}\n📅 **Date:** {datetime.now().strftime('%d-%m-%Y %I:%M %p')}\n💰 **Amount:** {course['amount']}\n"
            if course['custom_caption']: invoice_text += f"\n📝 {course['custom_caption']}\n"
            invoice_text += "\n⏳ *पेमेंट QR 10 मिनट में एक्सपायर हो जाएगा!*\n📸 **पेमेंट के बाद स्क्रीनशॉट यहीं भेजें।**"
            
            sent_msg = bot.send_photo(chat_id, photo=course['qr_file_id'], caption=invoice_text, parse_mode="Markdown")
            user_qr_messages[chat_id] = sent_msg.message_id
            threading.Timer(600, expire_qr, args=(chat_id, sent_msg.message_id, course_id)).start()

    # --- ADMIN: APPROVE ---
    elif data.startswith("app_"):
        parts = data.split('_', 2)
        user_id, course_id = int(parts[1]), parts[2]
        
        # 5-min message auto-delete cleanup
        if user_id in pending_verifications:
            try: bot.delete_message(user_id, pending_verifications[user_id]['checking_msg_id'])
            except: pass
            del pending_verifications[user_id]
        
        course = get_course_data(course_id)
        if course:
            try: bot.send_message(user_id, f"🎉 **Payment Approved!**\n\n{course['secret_text']}", parse_mode="Markdown")
            except: pass
            
            date_now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            try: uname = bot.get_chat(user_id).username or "User"
            except: uname = "User"
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO purchases (user_id, username, item_info, date) VALUES (?, ?, ?, ?)", (user_id, uname, course_id, date_now))
                conn.commit()
            bot.edit_message_caption("✅ **Approved & Sent!**", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")

    # --- ADMIN: DENY ---
    elif data.startswith("den_"):
        parts = data.split('_', 2)
        user_id, course_id = parts[1], parts[2]
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("1️⃣ Fake Screenshot", callback_data=f"rsn_fake_{user_id}_{course_id}"))
        markup.row(InlineKeyboardButton("2️⃣ Payment Not Received", callback_data=f"rsn_notrecv_{user_id}_{course_id}"))
        markup.row(InlineKeyboardButton("3️⃣ Wrong Amount", callback_data=f"rsn_wrong_{user_id}_{course_id}"))
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=markup)

    elif data.startswith("rsn_"):
        parts = data.split('_')
        reason_code, user_id, course_id = parts[1], int(parts[2]), parts[3]
        if reason_code == "fake": reason = "आपका स्क्रीनशॉट फेक या अमान्य है।"
        elif reason_code == "notrecv": reason = "हमें आपका पेमेंट बैंक में प्राप्त नहीं हुआ है।"
        elif reason_code == "wrong": reason = "आपने गलत अमाउंट भेजा है।"
        
        if user_id in pending_verifications:
            try: bot.delete_message(user_id, pending_verifications[user_id]['checking_msg_id'])
            except: pass
            del pending_verifications[user_id]
            
        retry_markup = InlineKeyboardMarkup().row(InlineKeyboardButton("🔄 Try Again (QR जनरेट करें)", callback_data=f"pay_upi_{course_id}"))
        try: bot.send_message(user_id, f"❌ **Payment Denied!**\nकारण: {reason}", reply_markup=retry_markup)
        except: pass
        bot.edit_message_caption(f"❌ **Denied:** {reason}", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")

# ==========================================
# 4. Flask Web Server (Render 24/7)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Advanced Batch Bot is Running Smoothly 24/7!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    def run_bot():
        print("बोट स्टार्ट हो गया है...")
        bot.infinity_polling(skip_pending=True)
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=port)
