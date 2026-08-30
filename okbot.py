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
PERSONAL_USERNAME = "@princemaan00" # इंटरनेशनल पेमेंट और चैट के लिए
DB_CHANNEL_ID = -1003757631353  # आपके प्राइवेट डेटाबेस चैनल की ID

bot = telebot.TeleBot(BOT_TOKEN)

# --- थ्रेड-सेफ डेटाबेस कनेक्शन हेल्पर ---
DB_FILE = "shop_master.db"
JSON_BACKUP = "courses_backup.json"

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS purchases 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, course_id TEXT, date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS courses 
                        (course_id TEXT PRIMARY KEY, promo_media TEXT, qr_file_id TEXT, amount TEXT, custom_caption TEXT, secret_text TEXT)''')
        conn.commit()

init_db()

# --- JSON बैकअप सिस्टम ---
def save_course_backup(course_id, promo_media, qr_file_id, amount, custom_caption, secret_text):
    data = {}
    if os.path.exists(JSON_BACKUP):
        try:
            with open(JSON_BACKUP, "r", encoding="utf-8") as f:
                data = json.load(f)
        except: data = {}
    data[course_id] = {
        "promo_media": promo_media,
        "qr_file_id": qr_file_id,
        "amount": amount,
        "custom_caption": custom_caption,
        "secret_text": secret_text
    }
    with open(JSON_BACKUP, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_course_data(course_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM courses WHERE course_id=?", (course_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
            
    if os.path.exists(JSON_BACKUP):
        try:
            with open(JSON_BACKUP, "r", encoding="utf-8") as f:
                data = json.load(f)
                if course_id in data:
                    c = data[course_id]
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("INSERT OR REPLACE INTO courses (course_id, promo_media, qr_file_id, amount, custom_caption, secret_text) VALUES (?, ?, ?, ?, ?, ?)",
                                       (course_id, c['promo_media'], c['qr_file_id'], c['amount'], c['custom_caption'], c['secret_text']))
                        conn.commit()
                    return c
        except: pass
    return None

# --- स्टेट मैनेजमेंट ---
user_states = {} 
user_qr_messages = {} # QR मैसेज की ID याद रखने के लिए (ताकि बाद में डिलीट हो सके)
admin_states = {} 
temp_courses = {} 

# --- 10-Min Timer Function ---
def expire_payment(chat_id, message_id, course_id):
    if user_states.get(chat_id) == course_id:
        try:
            bot.delete_message(chat_id, message_id) 
            bot.send_message(chat_id, "❌ **आपका पेमेंट सेशन (10 मिनट) एक्सपायर हो गया है!**\nसुरक्षा कारणों से QR कोड हटा दिया गया है। कृपया दोबारा लिंक पर क्लिक करके शुरुआत करें।")
            del user_states[chat_id]
            if chat_id in user_qr_messages:
                del user_qr_messages[chat_id]
        except: pass

# ==========================================
# 1. स्टार्ट कमांड
# ==========================================
@bot.message_handler(commands=['start'])
def start_command(message):
    command_parts = message.text.split()
    user_id = message.chat.id
    
    if len(command_parts) > 1:
        course_id = command_parts[1].strip()
        course = get_course_data(course_id)
        
        if course:
            promo_items = json.loads(course['promo_media'])
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🇮🇳 UPI (India)", callback_data=f"pay_upi_{course_id}"))
            markup.row(InlineKeyboardButton("🌍 International", callback_data="pay_intl"),
                       InlineKeyboardButton("💬 Chat with Me", callback_data="pay_chat"))
            
            # अगर केवल 1 मीडिया (फोटो/वीडियो) है, तो बटन्स सीधे उसी के नीचे आएंगे
            if len(promo_items) == 1:
                item = promo_items[0]
                caption = item.get('caption', '')
                if item['type'] == 'photo':
                    bot.send_photo(user_id, item['file_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")
                elif item['type'] == 'video':
                    bot.send_video(user_id, item['file_id'], caption=caption, reply_markup=markup, parse_mode="Markdown")
                elif item['type'] == 'text':
                    bot.send_message(user_id, caption, reply_markup=markup, parse_mode="Markdown")
            
            # अगर एल्बम है, तो आखिरी आइटम के नीचे बटन्स आएंगे
            else:
                media_group = []
                for item in promo_items[:-1]:
                    if item['type'] == 'photo':
                        media_group.append(InputMediaPhoto(item['file_id'], caption=item.get('caption', '')))
                    elif item['type'] == 'video':
                        media_group.append(InputMediaVideo(item['file_id'], caption=item.get('caption', '')))
                
                if media_group:
                    try: bot.send_media_group(user_id, media_group)
                    except: pass
                
                last_item = promo_items[-1]
                last_cap = last_item.get('caption', '')
                if last_item['type'] == 'photo':
                    bot.send_photo(user_id, last_item['file_id'], caption=last_cap, reply_markup=markup, parse_mode="Markdown")
                elif last_item['type'] == 'video':
                    bot.send_video(user_id, last_item['file_id'], caption=last_cap, reply_markup=markup, parse_mode="Markdown")
                else:
                    bot.send_message(user_id, last_cap, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(user_id, "❌ यह लिंक उपलब्ध नहीं है या गलत है।")
            
    else:
        if user_id == ADMIN_ID:
            send_admin_panel(user_id)
        else:
            bot.send_message(user_id, "नमस्कार! कृपया कोर्स के सही लिंक पर क्लिक करके आएँ।")

def send_admin_panel(chat_id):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ Add Course", callback_data="admin_add_course"))
    markup.row(InlineKeyboardButton("👥 User Info", callback_data="admin_user_info"))
    bot.send_message(chat_id, "🛠 **एडमिन पैनल**\nकृपया कोई विकल्प चुनें:", reply_markup=markup)

# ==========================================
# 2. कोर्स निर्माण के स्टेप्स
# ==========================================
@bot.message_handler(content_types=['photo', 'video', 'document', 'text'])
def handle_all_messages(message):
    user_id = message.chat.id
    
    if user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_PROMO':
        media_type = 'text'
        file_id = None
        if message.photo: media_type, file_id = 'photo', message.photo[-1].file_id
        elif message.video: media_type, file_id = 'video', message.video.file_id
        temp_courses[ADMIN_ID]['promo'].append({'type': media_type, 'file_id': file_id, 'caption': message.caption or message.text or ""})

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_QR':
        if message.photo:
            temp_courses[ADMIN_ID]['qr'] = message.photo[-1].file_id
            admin_states[ADMIN_ID] = 'WAITING_FOR_AMOUNT'
            bot.send_message(ADMIN_ID, "✅ **QR Code सेव हो गया!**\n\n💰 **Step 3/5: अमाउंट सेट करें**\nकृपया कोर्स की कीमत टाइप करके भेजें (जैसे: ₹299)")
        else: bot.send_message(ADMIN_ID, "❌ कृपया QR कोड की सिर्फ **फोटो** भेजें।")
            
    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_AMOUNT':
        if message.text:
            temp_courses[ADMIN_ID]['amount'] = message.text.strip()
            admin_states[ADMIN_ID] = 'WAITING_FOR_CAPTION'
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("⏭ Skip (कोई कैप्शन नहीं)", callback_data="skip_caption"))
            bot.send_message(ADMIN_ID, "✅ **अमाउंट सेव हो गई!**\n\n📝 **Step 4/5: अतिरिक्त कैप्शन (Optional)**\nअगर कोई एक्स्ट्रा मैसेज लिखना चाहते हैं तो टाइप करें, वरना 'Skip' दबाएं।", reply_markup=markup)
        else: bot.send_message(ADMIN_ID, "❌ कृपया अमाउंट टेक्स्ट में भेजें।")

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_CAPTION':
        if message.text:
            temp_courses[ADMIN_ID]['caption'] = message.text.strip()
            admin_states[ADMIN_ID] = 'WAITING_FOR_LINK'
            bot.send_message(ADMIN_ID, "✅ **कैप्शन सेव हो गया!**\n\n🔗 **Step 5/5: फाइनल सीक्रेट लिंक**\nअब वह फाइनल लिंक भेजें जो पेमेंट अप्रूव होने के बाद यूज़र को मिलेगा।")

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_LINK':
        if message.text:
            secret = message.text.strip()
            course_id = "c_" + str(uuid.uuid4())[:6]
            promo_json = json.dumps(temp_courses[ADMIN_ID]['promo'])
            qr_id = temp_courses[ADMIN_ID]['qr']
            amount = temp_courses[ADMIN_ID]['amount']
            cap = temp_courses[ADMIN_ID]['caption']
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO courses (course_id, promo_media, qr_file_id, amount, custom_caption, secret_text) VALUES (?, ?, ?, ?, ?, ?)", 
                               (course_id, promo_json, qr_id, amount, cap, secret))
                conn.commit()
            
            save_course_backup(course_id, promo_json, qr_id, amount, cap, secret)
            
            link = f"https://t.me/{bot.get_me().username}?start={course_id}"
            
            try: bot.send_message(DB_CHANNEL_ID, f"🆕 **New Course Created**\n🆔 ID: `{course_id}`\n💰 Amount: {amount}\n🔗 Link: {link}", parse_mode="Markdown")
            except: pass

            bot.send_message(ADMIN_ID, f"🎉 **कोर्स सफलतापूर्वक बन गया!**\n\n👉 `{link}` 👈\n\nइस लिंक को आप कभी भी शेयर कर सकते हैं।", parse_mode="Markdown")
            admin_states.pop(ADMIN_ID, None)
            temp_courses.pop(ADMIN_ID, None)
            send_admin_panel(ADMIN_ID)

    # --- USER: पेमेंट स्क्रीनशॉट भेजना ---
    elif user_id in user_states:
        if message.photo:
            course_id = user_states[user_id]
            first_name = message.from_user.first_name or "User"
            username = f"(@{message.from_user.username})" if message.from_user.username else ""
            
            bot.send_message(user_id, "⏳ आपका स्क्रीनशॉट मिल गया है। सर्वर पर चेक किया जा रहा है...")
            del user_states[user_id]
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("✅ Approve", callback_data=f"app_{user_id}_{course_id}"))
            markup.row(InlineKeyboardButton("❌ Deny", callback_data=f"den_{user_id}_{course_id}"))
            
            admin_text = f"🔔 **New Payment Verification!**\n\n👤 User: {first_name} {username}\n🆔 ID: `{user_id}`\n📚 Course: `{course_id}`"
            
            try: bot.send_photo(DB_CHANNEL_ID, photo=message.photo[-1].file_id, caption=admin_text, reply_markup=markup, parse_mode="Markdown")
            except Exception as e: bot.send_message(ADMIN_ID, f"⚠️ चैनल एरर: {e}")
        else:
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
    
    if data == "admin_add_course":
        admin_states[ADMIN_ID] = 'WAITING_FOR_PROMO'
        temp_courses[ADMIN_ID] = {'promo': [], 'qr': None, 'amount': None, 'caption': "", 'secret': None}
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("➡️ Next Step", callback_data="next_qr"))
        bot.edit_message_text("📝 **Step 1/5: प्रोमो मीडिया**\nगैलरी से डेमो फोटो/वीडियो सेंड करें। फिर 'Next Step' दबाएं।", chat_id=chat_id, message_id=msg_id, reply_markup=markup)
        
    elif data == "next_qr":
        if not temp_courses.get(ADMIN_ID) or not temp_courses[ADMIN_ID]['promo']:
            bot.answer_callback_query(call.id, "❌ कृपया पहले कोई मीडिया भेजें!", show_alert=True)
            return
        admin_states[ADMIN_ID] = 'WAITING_FOR_QR'
        bot.edit_message_text("✅ डेमो मीडिया सेव!\n\n📷 **Step 2/5: पेमेंट QR कोड**\nअब अपना UPI QR Code (फोटो) सेंड करें।", chat_id=chat_id, message_id=msg_id)
        
    elif data == "skip_caption":
        admin_states[ADMIN_ID] = 'WAITING_FOR_LINK'
        bot.edit_message_text("✅ **कैप्शन स्किप!**\n\n🔗 **Step 5/5: फाइनल लिंक**\nफाइनल सीक्रेट लिंक/मैसेज भेजें।", chat_id=chat_id, message_id=msg_id)
        
    elif data == "admin_user_info":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, date, course_id FROM purchases ORDER BY id DESC LIMIT 15")
            records = cursor.fetchall()
            
        if not records:
            bot.edit_message_text("अभी तक किसी ने कोर्स नहीं खरीदा है।", chat_id=chat_id, message_id=msg_id)
        else:
            text = "👥 **Recent Buyers:**\n\n"
            for r in records: text += f"👤 {r['username']} | 📅 {r['date'][:10]} | 📚 `{r['course_id']}`\n"
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔙 Back", callback_data="back_to_admin"))
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="Markdown")
            
    elif data == "back_to_admin":
        try: bot.delete_message(chat_id, msg_id)
        except: pass
        send_admin_panel(chat_id)

    # --- USER: UPI QR कोड देखना ---
    elif data.startswith("pay_upi_"):
        course_id = data.replace("pay_upi_", "")
        course = get_course_data(course_id)
        
        if course:
            user_states[chat_id] = course_id
            qr_photo = course['qr_file_id']
            amount = course['amount']
            custom_caption = course['custom_caption']
            
            first_name = call.from_user.first_name or "User"
            username = f"(@{call.from_user.username})" if call.from_user.username else ""
            date_time = datetime.now().strftime("%d-%m-%Y %I:%M %p")
            
            invoice_text = (
                f"👤 **Name:** {first_name} {username}\n"
                f"📅 **Date & Time:** {date_time}\n"
                f"💰 **Amount to Pay:** {amount}\n"
            )
            if custom_caption: invoice_text += f"\n📝 {custom_caption}\n"
            invoice_text += (
                f"\n⏳ *ध्यान दें: यह पेमेंट QR 10 मिनट में एक्सपायर हो जाएगा!*\n\n"
                f"📸 **पेमेंट सफल होने के बाद, कृपया स्क्रीनशॉट यहीं सेंड करें।**"
            )
            
            sent_msg = bot.send_photo(chat_id, photo=qr_photo, caption=invoice_text, parse_mode="Markdown")
            user_qr_messages[chat_id] = sent_msg.message_id # QR Message ID सेव कर ली
            
            timer = threading.Timer(600, expire_payment, args=(chat_id, sent_msg.message_id, course_id))
            timer.start()

    elif data in ["pay_intl", "pay_chat"]:
        bot.send_message(chat_id, f"💬 कृपया सीधे बात करने के लिए यहाँ मैसेज करें: {PERSONAL_USERNAME}")

    # --- ADMIN: Approve दबाना (QR कोड डिलीट + फाइनल लिंक) ---
    elif data.startswith("app_"):
        parts = data.split('_', 2)
        user_id = int(parts[1])
        course_id = parts[2]
        
        # 1. यूजर की चैट से QR कोड डिलीट करना
        if user_id in user_qr_messages:
            try:
                bot.delete_message(user_id, user_qr_messages[user_id])
                del user_qr_messages[user_id]
            except: pass
        
        # 2. यूजर को कोर्स भेजना
        course = get_course_data(course_id)
        if course:
            try: bot.send_message(user_id, f"🎉 **Payment Approved!**\n\n{course['secret_text']}", parse_mode="Markdown")
            except: pass
            
            date_now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            try: 
                user_info = bot.get_chat(user_id)
                uname = user_info.username or user_info.first_name
            except: uname = "User"
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO purchases (user_id, username, course_id, date) VALUES (?, ?, ?, ?)", (user_id, uname, course_id, date_now))
                conn.commit()
            
            success_log = f"✅ **SUCCESSFUL PURCHASE** ✅\n\n👤 Buyer: {uname}\n🆔 User ID: `{user_id}`\n📚 Course ID: `{course_id}`\n📅 Date: {date_now}"
            try: bot.send_message(DB_CHANNEL_ID, success_log)
            except: pass
            
            bot.edit_message_caption("✅ **Approved & Logged!**", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")

    # --- ADMIN: Deny दबाना (3 रीज़न दिखाना) ---
    elif data.startswith("den_"):
        parts = data.split('_', 2)
        user_id = parts[1]
        course_id = parts[2]
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("1️⃣ Fake Screenshot", callback_data=f"rsn_fake_{user_id}_{course_id}"))
        markup.row(InlineKeyboardButton("2️⃣ Payment Not Received", callback_data=f"rsn_notrecv_{user_id}_{course_id}"))
        markup.row(InlineKeyboardButton("3️⃣ Wrong Amount", callback_data=f"rsn_wrong_{user_id}_{course_id}"))
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=markup)

    # --- ADMIN: Rejection Reason चुनना (QR कोड डिलीट + रिफ्रेश बटन) ---
    elif data.startswith("rsn_"):
        parts = data.split('_')
        reason_code = parts[1]
        user_id = int(parts[2])
        course_id = parts[3]
        
        if reason_code == "fake": reason = "आपका स्क्रीनशॉट फेक या अमान्य है।"
        elif reason_code == "notrecv": reason = "हमें आपका पेमेंट बैंक में प्राप्त नहीं हुआ है।"
        elif reason_code == "wrong": reason = "आपने गलत अमाउंट भेजा है।"
        else: reason = "अमान्य ट्रांजेक्शन।"
        
        # 1. यूजर की चैट से पुराना QR कोड डिलीट करना
        if user_id in user_qr_messages:
            try:
                bot.delete_message(user_id, user_qr_messages[user_id])
                del user_qr_messages[user_id]
            except: pass
        
        # 2. रिफ्रेश / री-ट्राई बटन तैयार करना
        retry_markup = InlineKeyboardMarkup()
        retry_markup.row(InlineKeyboardButton("🔄 Try Again / फिर से कोशिश करें", callback_data=f"pay_upi_{course_id}"))
        
        deny_text = (
            f"❌ **Payment Denied!**\n\n"
            f"📌 **कारण:** {reason}\n\n"
            f"अगर आपको लगता है यह गलती है, तो {PERSONAL_USERNAME} पर संपर्क करें या नीचे दिए गए बटन पर क्लिक करके दोबारा पेमेंट करें।"
        )
        
        try: bot.send_message(user_id, deny_text, reply_markup=retry_markup, parse_mode="Markdown")
        except: pass
        
        bot.edit_message_caption(f"❌ **Denied:** {reason}", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")

# ==========================================
# 4. Flask Web Server (Render 24/7 के लिए)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Payment Bot is Running Smoothly 24/7!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    
    def run_bot():
        print("बोट स्टार्ट हो गया है...")
        bot.infinity_polling(skip_pending=True)
        
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    
    app.run(host="0.0.0.0", port=port)
