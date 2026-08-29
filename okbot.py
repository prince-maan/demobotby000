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
# 🛑 आपकी डिटेल्स 🛑
# ==========================================
BOT_TOKEN = "8986044820:AAH_NrdyJ1A0ZCsSwPoQ4PuWdLNWXSUYB3U"
ADMIN_ID = 8994976810  # आपका Telegram User ID
PERSONAL_USERNAME = "@princemaan00" # इंटरनेशनल पेमेंट के लिए
DB_CHANNEL_ID = -1003757631353  # आपके प्राइवेट चैनल की ID

bot = telebot.TeleBot(BOT_TOKEN)

# --- डेटाबेस सेटअप ---
conn = sqlite3.connect('shop_data_v3.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY, user_id INTEGER, username TEXT, course_id TEXT, date TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS courses (course_id TEXT PRIMARY KEY, promo_media TEXT, qr_file_id TEXT, amount TEXT, custom_caption TEXT, secret_text TEXT)''')
conn.commit()

# --- स्टेट मैनेजमेंट ---
user_states = {} 
admin_states = {} 
temp_courses = {} 

# --- 10-Min Timer Function ---
def expire_payment(chat_id, message_id, course_id):
    if user_states.get(chat_id) == course_id:
        try:
            bot.delete_message(chat_id, message_id) 
            bot.send_message(chat_id, "❌ **आपका पेमेंट सेशन (10 मिनट) एक्सपायर हो गया है!**\nसुरक्षा कारणों से QR कोड हटा दिया गया है। कृपया कोर्स के लिंक पर दोबारा क्लिक करके शुरुआत करें।")
            del user_states[chat_id] 
        except: pass

# ==========================================
# 1. स्टार्ट कमांड 
# ==========================================
@bot.message_handler(commands=['start'])
def start_command(message):
    command_parts = message.text.split()
    user_id = message.chat.id
    
    if len(command_parts) > 1:
        course_id = command_parts[1]
        cursor.execute("SELECT promo_media FROM courses WHERE course_id=?", (course_id,))
        res = cursor.fetchone()
        
        if res:
            promo_items = json.loads(res[0])
            media_group = []
            texts = []
            
            for item in promo_items:
                if item['type'] == 'photo': media_group.append(InputMediaPhoto(item['file_id'], caption=item.get('caption', '')))
                elif item['type'] == 'video': media_group.append(InputMediaVideo(item['file_id'], caption=item.get('caption', '')))
                elif item['type'] == 'text': texts.append(item['caption'])
            
            if len(media_group) > 1:
                try: bot.send_media_group(user_id, media_group)
                except: pass
            elif len(media_group) == 1:
                item = promo_items[0]
                if item['type'] == 'photo': bot.send_photo(user_id, item['file_id'], caption=item.get('caption',''))
                elif item['type'] == 'video': bot.send_video(user_id, item['file_id'], caption=item.get('caption',''))
            
            for text in texts:
                try: bot.send_message(user_id, text)
                except: pass
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🇮🇳 UPI (India)", callback_data=f"pay_upi_{course_id}"))
            markup.row(InlineKeyboardButton("🌍 International", callback_data="pay_intl"))
            markup.row(InlineKeyboardButton("💬 Chat with Me", callback_data="pay_chat"))
            
            bot.send_message(user_id, "👇 **पेमेंट के लिए विकल्प चुनें:**", reply_markup=markup)
        else:
            bot.send_message(user_id, "❌ यह लिंक एक्सपायर हो गया है या गलत है।")
    else:
        if user_id == ADMIN_ID: send_admin_panel(user_id)
        else: bot.send_message(user_id, "नमस्कार! कृपया सही लिंक से आएँ।")

def send_admin_panel(chat_id):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ Add Course", callback_data="admin_add_course"))
    markup.row(InlineKeyboardButton("👥 User Info", callback_data="admin_user_info"))
    bot.send_message(chat_id, "🛠 **एडमिन पैनल**\nकृपया कोई विकल्प चुनें:", reply_markup=markup)

# ==========================================
# 2. 5-Step Course Creation 
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
            bot.send_message(ADMIN_ID, "✅ **QR Code सेव हो गया!**\n\n💰 **Step 3/5: अमाउंट सेट करें**\nकृपया कोर्स की अमाउंट टाइप करके भेजें (जैसे: ₹299)")
        else: bot.send_message(ADMIN_ID, "❌ कृपया QR कोड की सिर्फ **फोटो** भेजें।")
            
    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_AMOUNT':
        if message.text:
            temp_courses[ADMIN_ID]['amount'] = message.text
            admin_states[ADMIN_ID] = 'WAITING_FOR_CAPTION'
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("⏭ Skip (कोई कैप्शन नहीं)", callback_data="skip_caption"))
            bot.send_message(ADMIN_ID, "✅ **अमाउंट सेव हो गई!**\n\n📝 **Step 4/5: अतिरिक्त कैप्शन (Optional)**\nअतिरिक्त मैसेज टाइप करें, या 'Skip' दबाएं।", reply_markup=markup)

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_CAPTION':
        if message.text:
            temp_courses[ADMIN_ID]['caption'] = message.text
            admin_states[ADMIN_ID] = 'WAITING_FOR_LINK'
            bot.send_message(ADMIN_ID, "✅ **कैप्शन सेव हो गया!**\n\n🔗 **Step 5/5: फाइनल लिंक**\nपेमेंट अप्रूव होने के बाद यूज़र को मिलने वाला सीक्रेट लिंक भेजें।")

    elif user_id == ADMIN_ID and admin_states.get(ADMIN_ID) == 'WAITING_FOR_LINK':
        if message.text:
            temp_courses[ADMIN_ID]['secret'] = message.text
            course_id = "c_" + str(uuid.uuid4())[:6]
            
            cursor.execute("INSERT INTO courses (course_id, promo_media, qr_file_id, amount, custom_caption, secret_text) VALUES (?, ?, ?, ?, ?, ?)", 
                           (course_id, json.dumps(temp_courses[ADMIN_ID]['promo']), temp_courses[ADMIN_ID]['qr'], temp_courses[ADMIN_ID]['amount'], temp_courses[ADMIN_ID]['caption'], temp_courses[ADMIN_ID]['secret']))
            conn.commit()
            
            link = f"https://t.me/{bot.get_me().username}?start={course_id}"
            
            try: bot.send_message(DB_CHANNEL_ID, f"🆕 **New Course Generated**\n🆔 ID: `{course_id}`\n💰 Amount: {temp_courses[ADMIN_ID]['amount']}\n🔗 Link: {link}", parse_mode="Markdown")
            except: pass

            bot.send_message(ADMIN_ID, f"🎉 **कोर्स सफलतापूर्वक बन गया!**\n👉 `{link}`", parse_mode="Markdown")
            admin_states.pop(ADMIN_ID, None)
            temp_courses.pop(ADMIN_ID, None)
            send_admin_panel(ADMIN_ID)

    # --- USER: पेमेंट का स्क्रीनशॉट ---
    elif user_id in user_states:
        if message.photo:
            course_id = user_states[user_id]
            first_name = message.from_user.first_name or "User"
            username = f"(@{message.from_user.username})" if message.from_user.username else ""
            
            bot.send_message(user_id, "⏳ आपका स्क्रीनशॉट मिल गया है। सर्वर पर चेक किया जा रहा है...")
            
            del user_states[user_id]
            
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("✅ Approve", callback_data=f"app_{user_id}_{course_id}"))
            markup.row(InlineKeyboardButton("❌ Deny", callback_data=f"den_{user_id}"))
            
            admin_text = f"🔔 **New Payment Verification!**\n\n👤 User: {first_name} {username}\n🆔 ID: `{user_id}`\n📚 Course: `{course_id}`"
            
            try: bot.send_photo(DB_CHANNEL_ID, photo=message.photo[-1].file_id, caption=admin_text, reply_markup=markup, parse_mode="Markdown")
            except Exception as e: bot.send_message(ADMIN_ID, f"⚠️ चैनल में भेजने में एरर: {e}")
        else:
            bot.send_message(user_id, "❌ कृपया पेमेंट का स्क्रीनशॉट (फोटो) भेजें।")

# ==========================================
# 3. बटन्स हैंडलिंग 
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
            bot.answer_callback_query(call.id, "❌ मीडिया भेजें!", show_alert=True)
            return
        admin_states[ADMIN_ID] = 'WAITING_FOR_QR'
        bot.edit_message_text("✅ डेमो मीडिया सेव!\n\n📷 **Step 2/5: पेमेंट QR कोड**\nअब अपना UPI QR Code (फोटो) सेंड करें।", chat_id=chat_id, message_id=msg_id)
        
    elif data == "skip_caption":
        admin_states[ADMIN_ID] = 'WAITING_FOR_LINK'
        bot.edit_message_text("✅ **कैप्शन स्किप!**\n\n🔗 **Step 5/5: फाइनल लिंक**\nफाइनल सीक्रेट लिंक/मैसेज भेजें।", chat_id=chat_id, message_id=msg_id)
        
    elif data == "admin_user_info":
        cursor.execute("SELECT username, date, course_id FROM purchases ORDER BY id DESC LIMIT 15")
        records = cursor.fetchall()
        if not records:
            bot.edit_message_text("अभी तक किसी ने कोर्स नहीं खरीदा है।", chat_id=chat_id, message_id=msg_id)
        else:
            text = "👥 **Recent Buyers:**\n\n"
            for r in records: text += f"👤 {r[0]} | 📅 {r[1][:10]} | 📚 `{r[2]}`\n"
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔙 Back", callback_data="back_to_admin"))
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="Markdown")
            
    elif data == "back_to_admin":
        try: bot.delete_message(chat_id, msg_id)
        except: pass
        send_admin_panel(chat_id)

    # --- USER: Select UPI (QR Layout & 10 Min Expiry) ---
    elif data.startswith("pay_upi_"):
        course_id = data.replace("pay_upi_", "")
        cursor.execute("SELECT qr_file_id, amount, custom_caption FROM courses WHERE course_id=?", (course_id,))
        res = cursor.fetchone()
        
        if res:
            user_states[chat_id] = course_id
            qr_photo, amount, custom_caption = res[0], res[1], res[2]
            
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
            
            timer = threading.Timer(600, expire_payment, args=(chat_id, sent_msg.message_id, course_id))
            timer.start()

    elif data in ["pay_intl", "pay_chat"]:
        bot.send_message(chat_id, f"💬 कृपया डायरेक्ट बात करने के लिए यहाँ मैसेज करें: {PERSONAL_USERNAME}")

    # --- ADMIN/CHANNEL: Approve Payment (Channel Log) ---
    elif data.startswith("app_"):
        parts = data.split('_', 2)
        user_id = int(parts[1])
        course_id = parts[2]
        
        cursor.execute("SELECT secret_text FROM courses WHERE course_id=?", (course_id,))
        res = cursor.fetchone()
        if res:
            try: bot.send_message(user_id, f"🎉 **Payment Approved!**\n\n{res[0]}", parse_mode="Markdown")
            except: pass
            
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try: 
                user_info = bot.get_chat(user_id)
                uname = user_info.username or user_info.first_name
            except: uname = "User"
            
            cursor.execute("INSERT INTO purchases (user_id, username, course_id, date) VALUES (?, ?, ?, ?)", (user_id, uname, course_id, date_now))
            conn.commit()
            
            success_log = f"✅ **SUCCESSFUL PURCHASE** ✅\n\n👤 Buyer: {uname}\n🆔 User ID: `{user_id}`\n📚 Course ID: `{course_id}`\n📅 Date: {date_now}"
            try: bot.send_message(DB_CHANNEL_ID, success_log)
            except: pass
            
            bot.edit_message_caption("✅ **Approved & Logged!**", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")

    elif data.startswith("den_"):
        user_id = data.split('_')[1]
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("1️⃣ Fake Screenshot", callback_data=f"rsn_fake_{user_id}"))
        markup.row(InlineKeyboardButton("2️⃣ Payment Not Received", callback_data=f"rsn_notrecv_{user_id}"))
        markup.row(InlineKeyboardButton("3️⃣ Wrong Amount", callback_data=f"rsn_wrong_{user_id}"))
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=markup)

    elif data.startswith("rsn_"):
        parts = data.split('_')
        reason_code = parts[1]
        user_id = int(parts[2])
        
        if reason_code == "fake": reason = "आपका स्क्रीनशॉट फेक या अमान्य है।"
        elif reason_code == "notrecv": reason = "हमें आपका पेमेंट बैंक में प्राप्त नहीं हुआ है।"
        elif reason_code == "wrong": reason = "आपने गलत अमाउंट भेजा है।"
        
        try: bot.send_message(user_id, f"❌ **Payment Denied!**\nकारण: {reason}\nअगर यह गलती है, तो {PERSONAL_USERNAME} पर संपर्क करें।")
        except: pass
        bot.edit_message_caption(f"❌ **Denied:** {reason}", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown")

# --- Flask Server for Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Payment Bot is Running Smoothly!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    
    def run_bot():
        print("बोट स्टार्ट हो गया है...")
        bot.infinity_polling(skip_pending=True)
        
    t = threading.Thread(target=run_bot)
    t.start()
    
    app.run(host="0.0.0.0", port=port)
