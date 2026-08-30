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

# direct link for Chat & International buttons (आप कभी भी इसे बदल सकते हैं)
CHAT_LINK = "https://t.me/princemaan00"
INTERNATIONAL_LINK = "https://t.me/princemaan00"

bot = telebot.TeleBot(BOT_TOKEN)

# --- थ्रेड-सेफ डेटाबेस कनेक्शन और बैकअप सिस्टम ---
DB_FILE = "shop_master_v4.db"
BACKUP_FILE = "master_backup.json"

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS purchases 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, item_info TEXT, date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS courses 
                        (course_id TEXT PRIMARY KEY, promo_media TEXT, qr_file_id TEXT, amount TEXT, custom_caption TEXT, secret_text TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS batches 
                        (batch_id TEXT PRIMARY KEY, title TEXT, courses_json TEXT)''')
        conn.commit()

init_db()

def load_backup():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {"courses": {}, "batches": {}}
    return {"courses": {}, "batches": {}}

def save_backup(data):
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- सिंगल कोर्स डेटा प्राप्त करना ---
def get_course_data(course_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM courses WHERE course_id=?", (course_id,))
        row = cursor.fetchone()
        if row: return dict(row)
    backup = load_backup()
    return backup.get("courses", {}).get(course_id)

# --- बैच डेटा प्राप्त करना ---
def get_batch_data(batch_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,))
        row = cursor.fetchone()
        if row: return dict(row)
    backup = load_backup()
    return backup.get("batches", {}).get(batch_id)

# --- स्टेट मैनेजमेंट ---
user_states = {} 
user_qr_messages = {} 
admin_states = {} 
temp_single_course = {} 
temp_batch = {} 

# --- 10-Min Timer Function ---
def expire_payment(chat_id, message_id, state_key):
    if user_states.get(chat_id) == state_key:
        try:
            bot.delete_message(chat_id, message_id)
            bot.send_message(chat_id, "❌ **आपका पेमेंट सेशन (10 मिनट) एक्सपायर हो गया है!**\nसुरक्षा कारणों से QR कोड हटा दिया गया है। कृपया दोबारा लिंक पर क्लिक करके शुरुआत करें।")
            del user_states[chat_id]
            if chat_id in user_qr_messages:
                del user_qr_messages[chat_id]
        except: pass

# ==========================================
# 1. स्टार्ट कमांड और डीप लिंकिंग
# ==========================================
@bot.message_handler(commands=['start'])
def start_command(message):
    command_parts = message.text.split()
    user_id = message.chat.id
    
    if len(command_parts) > 1:
        param = command_parts[1].strip()
        
        # --- BATCH LINK (b_xxxx) ---
        if param.startswith("b_"):
            batch_id = param
            batch = get_batch_data(batch_id)
            if batch:
                send_batch_menu(user_id, batch)
            else:
                bot.send_message(user_id, "❌ यह बैच लिंक उपलब्ध नहीं है या गलत है।")
                
        # --- SINGLE COURSE LINK (c_xxxx) ---
        elif param.startswith("c_"):
            course_id = param
            course = get_course_data(course_id)
            if course:
                promo_items = json.loads(course['promo_media'])
                
                # डायरेक्ट URL बटन्स
                markup = InlineKeyboardMarkup()
                markup.row(InlineKeyboardButton("🇮🇳 UPI (India)", callback_data=f"pay_upi_{course_id}"))
                markup.row(InlineKeyboardButton("🌍 International", url=INTERNATIONAL_LINK),
                           InlineKeyboardButton("💬 Chat with Me", url=CHAT_LINK))
                
                # अगर 1 फोटो/वीडियो है
                if len(promo_items) == 1:
                    item = promo_items[0]
                    cap = item.get('caption', '')
                    if item['type'] == 'photo': bot.send_photo(user_id, item['file_id'], caption=cap, reply_markup=markup, parse_mode="Markdown")
                    elif item['type'] == 'video': bot.send_video(user_id, item['file_id'], caption=cap, reply_markup=markup, parse_mode="Markdown")
                    else: bot.send_message(user_id, cap, reply_markup=markup, parse_mode="Markdown")
                
                # अगर मल्टीपल फाइल्स हैं (असली एल्बम ग्रिड)
                else:
                    media_group = []
                    for idx, item in enumerate(promo_items):
                        cap = item.get('caption', '') if idx == 0 else ""
                        if item['type'] == 'photo': media_group.append(InputMediaPhoto(item['file_id'], caption=cap))
                        elif item['type'] == 'video': media_group.append(InputMediaVideo(item['file_id'], caption=cap))
                    
                    if media_group:
                        try: bot.send_media_group(user_id, media_group)
                        except: pass
                    
                    bot.send_message(user_id, "👇 **Pay / Contact Options:**", reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(user_id, "❌ यह लिंक उपलब्ध नहीं है या गलत है।")
    else:
        if user_id == ADMIN_ID:
            send_admin_panel(user_id)
        else:
            bot.send_message(user_id, "नमस्कार! कृपया कोर्स के सही लिंक पर क्लिक करके आएँ।")

def send_admin_panel(chat_id):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ Add Single Course", callback_data="admin_add_course"))
    markup.row(InlineKeyboardButton("📦 Course Batch (बैच बनाएँ)", callback_data="admin_create_batch"))
    markup.row(InlineKeyboardButton("👥 User Info", callback_data="admin_user_info"))
    bot.send_message(chat_id, "🛠 **एडमिन पैनल**\nकृपया कोई विकल्प चुनें:", reply_markup=markup)

def send_batch_menu(chat_id, batch, edit_msg_id=None):
    title = batch['title']
    batch_id = batch['batch_id']
    courses = json.loads(batch['courses_json'])
    
    markup = InlineKeyboardMarkup()
    for idx, c in enumerate(courses):
        markup.row(InlineKeyboardButton(f"📚 {c['name']} - {c['price']}", callback_data=f"bbuy_{batch_id}_{idx}"))
    
    markup.row(InlineKeyboardButton("🌍 International", url=INTERNATIONAL_LINK),
               InlineKeyboardButton("💬 Chat with Me", url=CHAT_LINK))
    
    text = f"📦 **{title}**\n\nनीचे दिए गए कोर्सेज में से जिसे आप खरीदना चाहते हैं, उस पर क्लिक करें:"
    
    if edit_msg_id:
        try: bot.edit_message_text(text, chat_id=chat_id, message_id=edit_msg_id, reply_markup=markup, parse_mode="Markdown")
        except: bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

# ==========================================
# 2. इनपुट मैसेज हैंडलर (सिंगल कोर्स & बैच)
# ==========================================
@bot.message_handler(content_types=['photo', 'video', 'document', 'text'])
def handle_all_messages(message):
    user_id = message.chat.id
    
    # ------------------ SINGLE COURSE FLOW ------------------
    if user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_PROMO':
        media_type = 'text'
        file_id = None
        if message.photo: media_type, file_id = 'photo', message.photo[-1].file_id
        elif message.video: media_type, file_id = 'video', message.video.file_id
        temp_single_course[ADMIN_ID]['promo'].append({'type': media_type, 'file_id': file_id, 'caption': message.caption or message.text or ""})

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_QR':
        if message.photo:
            temp_single_course[ADMIN_ID]['qr'] = message.photo[-1].file_id
            admin_states[ADMIN_ID] = 'WAITING_FOR_AMOUNT'
            bot.send_message(ADMIN_ID, "✅ **QR Code सेव हो गया!**\n\n💰 **Step 3/5: अमाउंट सेट करें**\nकृपया कीमत भेजें (जैसे: ₹299):")
        else: bot.send_message(ADMIN_ID, "❌ कृपया QR कोड की **फोटो** भेजें।")
            
    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_AMOUNT':
        if message.text:
            temp_single_course[ADMIN_ID]['amount'] = message.text.strip()
            admin_states[ADMIN_ID] = 'WAITING_FOR_CAPTION'
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("⏭ Skip (कोई कैप्शन नहीं)", callback_data="skip_caption"))
            bot.send_message(ADMIN_ID, "✅ **अमाउंट सेव!**\n\n📝 **Step 4/5: अतिरिक्त कैप्शन (Optional)**\nअतिरिक्त मैसेज टाइप करें, या 'Skip' दबाएं।", reply_markup=markup)

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_CAPTION':
        if message.text:
            temp_single_course[ADMIN_ID]['caption'] = message.text.strip()
            admin_states[ADMIN_ID] = 'WAITING_FOR_LINK'
            bot.send_message(ADMIN_ID, "✅ **कैप्शन सेव!**\n\n🔗 **Step 5/5: फाइनल सीक्रेट लिंक**\nपेमेंट अप्रूव होने पर मिलने वाला लिंक भेजें:")

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_LINK':
        if message.text:
            secret = message.text.strip()
            course_id = "c_" + str(uuid.uuid4())[:6]
            promo_json = json.dumps(temp_single_course[ADMIN_ID]['promo'])
            qr_id = temp_single_course[ADMIN_ID]['qr']
            amount = temp_single_course[ADMIN_ID]['amount']
            cap = temp_single_course[ADMIN_ID]['caption']
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO courses VALUES (?, ?, ?, ?, ?, ?)", (course_id, promo_json, qr_id, amount, cap, secret))
                conn.commit()
            
            bk = load_backup()
            bk["courses"][course_id] = {"promo_media": promo_json, "qr_file_id": qr_id, "amount": amount, "custom_caption": cap, "secret_text": secret}
            save_backup(bk)
            
            link = f"https://t.me/{bot.get_me().username}?start={course_id}"
            try: bot.send_message(DB_CHANNEL_ID, f"🆕 **Single Course Created**\n🆔 ID: `{course_id}`\n💰 Amount: {amount}\n🔗 Link: {link}", parse_mode="Markdown")
            except: pass

            bot.send_message(ADMIN_ID, f"🎉 **कोर्स बन गया!**\n👉 `{link}`", parse_mode="Markdown")
            admin_states.pop(ADMIN_ID, None)
            temp_single_course.pop(ADMIN_ID, None)
            send_admin_panel(ADMIN_ID)

    # ------------------ COURSE BATCH FLOW ------------------
    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'BATCH_WAITING_TITLE':
        if message.text:
            temp_batch[ADMIN_ID] = {'title': message.text.strip(), 'courses': [], 'current_item': {}}
            admin_states[ADMIN_ID] = 'BATCH_ITEM_NAME_PRICE'
            bot.send_message(ADMIN_ID, f"✅ बैच टाइटल सेव: **{message.text.strip()}**\n\n📚 **Course #1 का नाम और कीमत भेजें** (बीच में '-' लगाएं)\n*उदा:* Video Editing - ₹299", parse_mode="Markdown")

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'BATCH_ITEM_NAME_PRICE':
        if message.text:
            txt = message.text.strip()
            if "-" in txt: name, price = txt.split("-", 1)
            else: name, price = txt, "Free"
            
            temp_batch[ADMIN_ID]['current_item'] = {'name': name.strip(), 'price': price.strip()}
            admin_states[ADMIN_ID] = 'BATCH_ITEM_QR'
            bot.send_message(ADMIN_ID, f"📷 **{name.strip()} के लिए UPI QR Code (फोटो) भेजें:**")

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'BATCH_ITEM_QR':
        if message.photo:
            temp_batch[ADMIN_ID]['current_item']['qr_file_id'] = message.photo[-1].file_id
            admin_states[ADMIN_ID] = 'BATCH_ITEM_SECRET'
            bot.send_message(ADMIN_ID, "🔗 **इस कोर्स का फाइनल सीक्रेट डिलीवरी लिंक/मैसेज भेजें:**")
        else: bot.send_message(ADMIN_ID, "❌ कृपया QR कोड की **फोटो** भेजें।")

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'BATCH_ITEM_SECRET':
        if message.text:
            temp_batch[ADMIN_ID]['current_item']['secret'] = message.text.strip()
            # कोर्स को बैच में जोड़ें
            temp_batch[ADMIN_ID]['courses'].append(temp_batch[ADMIN_ID]['current_item'])
            temp_batch[ADMIN_ID]['current_item'] = {}
            admin_states[ADMIN_ID] = 'BATCH_MENU'
            
            total = len(temp_batch[ADMIN_ID]['courses'])
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("➕ Add Another Course (अगला कोर्स)", callback_data="batch_add_next"))
            markup.row(InlineKeyboardButton("✅ Finish & Create Batch Link", callback_data="batch_finish"))
            
            bot.send_message(ADMIN_ID, f"✅ **Course #{total} सेव हो गया!**\n\nक्या आप इस बैच में एक और कोर्स जोड़ना चाहते हैं?", reply_markup=markup)

    # ------------------ USER SCREENSHOT RECEIVING ------------------
    elif user_id in user_states:
        if message.photo:
            state_key = user_states[user_id]
            first_name = message.from_user.first_name or "User"
            username = f"(@{message.from_user.username})" if message.from_user.username else ""
            
            bot.send_message(user_id, "⏳ आपका स्क्रीनशॉट मिल गया है। सर्वर पर चेक किया जा रहा है...")
            del user_states[user_id]
            
            # SINGLE COURSE VERIFICATION
            if state_key.startswith("c_"):
                course_id = state_key
                markup = InlineKeyboardMarkup()
                markup.row(InlineKeyboardButton("✅ Approve", callback_data=f"app_{user_id}_{course_id}"))
                markup.row(InlineKeyboardButton("❌ Deny", callback_data=f"den_{user_id}_{course_id}"))
                admin_text = f"🔔 **New Single Payment!**\n👤 User: {first_name} {username}\n🆔 ID: `{user_id}`\n📚 Course: `{course_id}`"
                try: bot.send_photo(DB_CHANNEL_ID, photo=message.photo[-1].file_id, caption=admin_text, reply_markup=markup, parse_mode="Markdown")
                except: pass
                
            # BATCH COURSE VERIFICATION
            elif state_key.startswith("batch_"):
                parts = state_key.split('_')
                batch_id = f"b_{parts[1]}"
                c_idx = int(parts[2])
                batch = get_batch_data(batch_id)
                course_info = json.loads(batch['courses_json'])[c_idx] if batch else {}
                
                markup = InlineKeyboardMarkup()
                markup.row(InlineKeyboardButton("✅ Approve", callback_data=f"bapp_{user_id}_{batch_id}_{c_idx}"))
                markup.row(InlineKeyboardButton("❌ Deny", callback_data=f"bden_{user_id}_{batch_id}_{c_idx}"))
                
                admin_text = (f"🔔 **New Batch Payment!**\n\n"
                              f"👤 User: {first_name} {username}\n"
                              f"🆔 ID: `{user_id}`\n"
                              f"📦 Batch: {batch['title'] if batch else 'Batch'}\n"
                              f"📚 Course: {course_info.get('name')} ({course_info.get('price')})")
                try: bot.send_photo(DB_CHANNEL_ID, photo=message.photo[-1].file_id, caption=admin_text, reply_markup=markup, parse_mode="Markdown")
                except: pass
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
    
    # --- ADMIN: Single Course ---
    if data == "admin_add_course":
        admin_states[ADMIN_ID] = 'WAITING_FOR_PROMO'
        temp_single_course[ADMIN_ID] = {'promo': [], 'qr': None, 'amount': None, 'caption': "", 'secret': None}
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("➡️ Next Step", callback_data="next_qr"))
        bot.edit_message_text("📝 **Step 1/5: प्रोमो मीडिया**\nडेमो फोटो/वीडियो भेजें (एल्बम के लिए एक साथ चुनें)। फिर 'Next Step' दबाएं।", chat_id=chat_id, message_id=msg_id, reply_markup=markup)
        
    elif data == "next_qr":
        if not temp_single_course.get(ADMIN_ID) or not temp_single_course[ADMIN_ID]['promo']:
            bot.answer_callback_query(call.id, "❌ पहले मीडिया भेजें!", show_alert=True)
            return
        admin_states[ADMIN_ID] = 'WAITING_FOR_QR'
        bot.edit_message_text("✅ मीडिया सेव!\n\n📷 **Step 2/5: पेमेंट QR कोड**\nअपना UPI QR Code (फोटो) भेजें।", chat_id=chat_id, message_id=msg_id)
        
    elif data == "skip_caption":
        admin_states[ADMIN_ID] = 'WAITING_FOR_LINK'
        bot.edit_message_text("✅ **कैप्शन स्किप!**\n\n🔗 **Step 5/5: फाइनल लिंक**\nफाइनल सीक्रेट डिलीवरी लिंक भेजें।", chat_id=chat_id, message_id=msg_id)

    # --- ADMIN: Batch Course Creation ---
    elif data == "admin_create_batch":
        admin_states[ADMIN_ID] = 'BATCH_WAITING_TITLE'
        bot.edit_message_text("📦 **नया कोर्स बैच (Course Batch) बनाएँ**\n\nकृपया इस बैच का **नाम/टाइटल** भेजें (उदा: All-in-One Pro Pack):", chat_id=chat_id, message_id=msg_id)

    elif data == "batch_add_next":
        total = len(temp_batch[ADMIN_ID]['courses']) + 1
        admin_states[ADMIN_ID] = 'BATCH_ITEM_NAME_PRICE'
        bot.send_message(ADMIN_ID, f"📚 **Course #{total} का नाम और कीमत भेजें** (उदा: Editing Course - ₹199):")

    elif data == "batch_finish":
        if not temp_batch.get(ADMIN_ID) or not temp_batch[ADMIN_ID]['courses']:
            bot.answer_callback_query(call.id, "❌ कोई कोर्स नहीं जोड़ा गया!", show_alert=True)
            return
        
        batch_id = "b_" + str(uuid.uuid4())[:6]
        title = temp_batch[ADMIN_ID]['title']
        courses_json = json.dumps(temp_batch[ADMIN_ID]['courses'])
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO batches VALUES (?, ?, ?)", (batch_id, title, courses_json))
            conn.commit()
            
        bk = load_backup()
        bk["batches"][batch_id] = {"batch_id": batch_id, "title": title, "courses_json": courses_json}
        save_backup(bk)
        
        link = f"https://t.me/{bot.get_me().username}?start={batch_id}"
        try: bot.send_message(DB_CHANNEL_ID, f"🆕 **Course Batch Created**\n📦 Title: {title}\n🆔 ID: `{batch_id}`\n🔗 Link: {link}", parse_mode="Markdown")
        except: pass
        
        bot.edit_message_text(f"🎉 **कोर्स बैच सफलतापूर्वक बन गया!**\n\n📦 **Title:** {title}\n📚 **Total Courses:** {len(temp_batch[ADMIN_ID]['courses'])}\n\n👉 `{link}` 👈", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")
        admin_states.pop(ADMIN_ID, None)
        temp_batch.pop(ADMIN_ID, None)
        send_admin_panel(ADMIN_ID)

    # --- ADMIN: User Info ---
    elif data == "admin_user_info":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, date, item_info FROM purchases ORDER BY id DESC LIMIT 15")
            records = cursor.fetchall()
            
        if not records:
            bot.edit_message_text("अभी तक किसी ने कोर्स नहीं खरीदा है।", chat_id=chat_id, message_id=msg_id)
        else:
            text = "👥 **Recent Buyers:**\n\n"
            for r in records: text += f"👤 {r['username']} | 📅 {r['date'][:10]} | 📚 `{r['item_info']}`\n"
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔙 Back", callback_data="back_to_admin"))
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="Markdown")
            
    elif data == "back_to_admin":
        try: bot.delete_message(chat_id, msg_id)
        except: pass
        send_admin_panel(chat_id)

    # --- USER: Single UPI QR View ---
    elif data.startswith("pay_upi_"):
        course_id = data.replace("pay_upi_", "")
        course = get_course_data(course_id)
        if course:
            user_states[chat_id] = course_id
            first_name = call.from_user.first_name or "User"
            username = f"(@{call.from_user.username})" if call.from_user.username else ""
            date_time = datetime.now().strftime("%d-%m-%Y %I:%M %p")
            
            invoice_text = (
                f"👤 **Name:** {first_name} {username}\n"
                f"📅 **Date & Time:** {date_time}\n"
                f"💰 **Amount to Pay:** {course['amount']}\n"
            )
            if course['custom_caption']: invoice_text += f"\n📝 {course['custom_caption']}\n"
            invoice_text += "\n⏳ *ध्यान दें: यह पेमेंट QR 10 मिनट में एक्सपायर हो जाएगा!*\n📸 **पेमेंट सफल होने के बाद स्क्रीनशॉट यहीं सेंड करें।**"
            
            sent_msg = bot.send_photo(chat_id, photo=course['qr_file_id'], caption=invoice_text, parse_mode="Markdown")
            user_qr_messages[chat_id] = sent_msg.message_id
            
            threading.Timer(600, expire_payment, args=(chat_id, sent_msg.message_id, course_id)).start()

    # --- USER: Batch Item Buy Click (Show QR + Back Button) ---
    elif data.startswith("bbuy_"):
        parts = data.split('_')
        batch_id = f"b_{parts[1]}"
        c_idx = int(parts[2])
        batch = get_batch_data(batch_id)
        
        if batch:
            course = json.loads(batch['courses_json'])[c_idx]
            state_key = f"batch_{parts[1]}_{c_idx}"
            user_states[chat_id] = state_key
            
            first_name = call.from_user.first_name or "User"
            username = f"(@{call.from_user.username})" if call.from_user.username else ""
            date_time = datetime.now().strftime("%d-%m-%Y %I:%M %p")
            
            invoice_text = (
                f"📦 **Batch:** {batch['title']}\n"
                f"📚 **Selected:** {course['name']}\n"
                f"👤 **Name:** {first_name} {username}\n"
                f"📅 **Date & Time:** {date_time}\n"
                f"💰 **Amount to Pay:** {course['price']}\n\n"
                f"⏳ *ध्यान दें: यह पेमेंट QR 10 मिनट में एक्सपायर हो जाएगा!*\n"
                f"📸 **पेमेंट सफल होने के बाद स्क्रीनशॉट यहीं सेंड करें।**"
            )
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔙 Back to Batch / वापस जाएं", callback_data=f"bback_{batch_id}"))
            markup.row(InlineKeyboardButton("🌍 International", url=INTERNATIONAL_LINK),
                       InlineKeyboardButton("💬 Chat with Me", url=CHAT_LINK))
            
            # पिछला बैच मेनू हटाकर फ्रेश QR भेजें
            try: bot.delete_message(chat_id, msg_id)
            except: pass
            
            sent_msg = bot.send_photo(chat_id, photo=course['qr_file_id'], caption=invoice_text, reply_markup=markup, parse_mode="Markdown")
            user_qr_messages[chat_id] = sent_msg.message_id
            
            threading.Timer(600, expire_payment, args=(chat_id, sent_msg.message_id, state_key)).start()

    # --- USER: Back to Batch List ---
    elif data.startswith("bback_"):
        batch_id = data.replace("bback_", "")
        batch = get_batch_data(batch_id)
        if chat_id in user_states: del user_states[chat_id]
        if chat_id in user_qr_messages:
            try: bot.delete_message(chat_id, user_qr_messages[chat_id])
            except: pass
            del user_qr_messages[chat_id]
            
        if batch:
            send_batch_menu(chat_id, batch)

    # --- ADMIN: Approve Single Course ---
    elif data.startswith("app_"):
        parts = data.split('_', 2)
        user_id = int(parts[1])
        course_id = parts[2]
        
        if user_id in user_qr_messages:
            try: bot.delete_message(user_id, user_qr_messages[user_id]); del user_qr_messages[user_id]
            except: pass
        
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
            
            try: bot.send_message(DB_CHANNEL_ID, f"✅ **PURCHASE LOGGED**\n👤 Buyer: {uname}\n🆔 ID: `{user_id}`\n📚 Course: `{course_id}`\n📅 Date: {date_now}")
            except: pass
            bot.edit_message_caption("✅ **Approved & Sent!**", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")

    # --- ADMIN: Deny Single Course ---
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
        
        if user_id in user_qr_messages:
            try: bot.delete_message(user_id, user_qr_messages[user_id]); del user_qr_messages[user_id]
            except: pass
            
        retry_markup = InlineKeyboardMarkup()
        retry_markup.row(InlineKeyboardButton("🔄 Try Again", callback_data=f"pay_upi_{course_id}"))
        try: bot.send_message(user_id, f"❌ **Payment Denied!**\nकारण: {reason}", reply_markup=retry_markup)
        except: pass
        bot.edit_message_caption(f"❌ **Denied:** {reason}", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")

    # --- ADMIN: Approve Batch Course ---
    elif data.startswith("bapp_"):
        parts = data.split('_')
        user_id = int(parts[1])
        batch_id = f"b_{parts[2]}"
        c_idx = int(parts[3])
        
        if user_id in user_qr_messages:
            try: bot.delete_message(user_id, user_qr_messages[user_id]); del user_qr_messages[user_id]
            except: pass
            
        batch = get_batch_data(batch_id)
        if batch:
            course = json.loads(batch['courses_json'])[c_idx]
            try: bot.send_message(user_id, f"🎉 **Payment Approved!**\n\n📚 **{course['name']}**\n\n{course['secret']}", parse_mode="Markdown")
            except: pass
            
            date_now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            try: uname = bot.get_chat(user_id).username or "User"
            except: uname = "User"
            
            info = f"{batch['title']} -> {course['name']}"
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO purchases (user_id, username, item_info, date) VALUES (?, ?, ?, ?)", (user_id, uname, info, date_now))
                conn.commit()
                
            try: bot.send_message(DB_CHANNEL_ID, f"✅ **BATCH PURCHASE LOGGED**\n👤 Buyer: {uname}\n🆔 ID: `{user_id}`\n📚 Item: {info}\n📅 Date: {date_now}")
            except: pass
            bot.edit_message_caption("✅ **Approved & Sent!**", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")

    # --- ADMIN: Deny Batch Course ---
    elif data.startswith("bden_"):
        parts = data.split('_')
        user_id, batch_num, c_idx = parts[1], parts[2], parts[3]
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("1️⃣ Fake Screenshot", callback_data=f"brsn_fake_{user_id}_{batch_num}_{c_idx}"))
        markup.row(InlineKeyboardButton("2️⃣ Payment Not Received", callback_data=f"brsn_notrecv_{user_id}_{batch_num}_{c_idx}"))
        markup.row(InlineKeyboardButton("3️⃣ Wrong Amount", callback_data=f"brsn_wrong_{user_id}_{batch_num}_{c_idx}"))
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=markup)

    elif data.startswith("brsn_"):
        parts = data.split('_')
        reason_code, user_id, batch_num, c_idx = parts[1], int(parts[2]), parts[3], parts[4]
        batch_id = f"b_{batch_num}"
        if reason_code == "fake": reason = "आपका स्क्रीनशॉट फेक या अमान्य है।"
        elif reason_code == "notrecv": reason = "हमें आपका पेमेंट बैंक में प्राप्त नहीं हुआ है।"
        elif reason_code == "wrong": reason = "आपने गलत अमाउंट भेजा है।"
        
        if user_id in user_qr_messages:
            try: bot.delete_message(user_id, user_qr_messages[user_id]); del user_qr_messages[user_id]
            except: pass
            
        retry_markup = InlineKeyboardMarkup()
        retry_markup.row(InlineKeyboardButton("🔄 Try Again", callback_data=f"bbuy_{batch_id}_{c_idx}"))
        retry_markup.row(InlineKeyboardButton("🔙 Back to Batch", callback_data=f"bback_{batch_id}"))
        try: bot.send_message(user_id, f"❌ **Payment Denied!**\nकारण: {reason}", reply_markup=retry_markup)
        except: pass
        bot.edit_message_caption(f"❌ **Denied:** {reason}", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")

# ==========================================
# 4. Flask Web Server (Render 24/7)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Payment & Batch Bot is Running Smoothly 24/7!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    
    def run_bot():
        print("बोट स्टार्ट हो गया है...")
        bot.infinity_polling(skip_pending=True)
        
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    
    app.run(host="0.0.0.0", port=port)
