import io
import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime
from flask import Flask
from PIL import Image, ImageDraw
import qrcode
import telebot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)

# ==========================================
# 🛑 सेटिंग्स (लोकल और रेंडर दोनों के लिए) 🛑
# ==========================================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN", "8986044820:AAH_NrdyJ1A0ZCsSwPoQ4PuWdLNWXSUYB3U"
).strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8994976810").strip())
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003757631353").strip())
UPI_ID = os.environ.get("UPI_ID", "Q520245588@ybl").strip()
MERCHANT_NAME = os.environ.get("MERCHANT_NAME", "Study Wala").strip()

CHAT_LINK = os.environ.get("CHAT_LINK", "https://t.me/princemaan00").strip()
INTERNATIONAL_LINK = os.environ.get(
    "INTERNATIONAL_LINK", "https://t.me/princemaan00"
).strip()

bot = telebot.TeleBot(BOT_TOKEN)

# --- डेटाबेस और बैकअप सेटअप ---
DB_FILE = "shop_master_v5.db"
BACKUP_FILE = "master_backup_v5.json"


def get_db():
  conn = sqlite3.connect(DB_FILE, timeout=30)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            username TEXT, 
            item_info TEXT, 
            date TEXT
        )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS courses (
            course_id TEXT PRIMARY KEY, 
            promo_media TEXT, 
            amount TEXT, 
            custom_caption TEXT, 
            secret_text TEXT
        )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT PRIMARY KEY, 
            title TEXT, 
            course_ids TEXT
        )""")
    conn.commit()


init_db()


def load_backup():
  if os.path.exists(BACKUP_FILE):
    try:
      with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except:
      pass
  return {"courses": {}, "batches": {}}


def save_backup(data):
  with open(BACKUP_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)


def get_course_data(course_id):
  with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM courses WHERE course_id=?", (course_id,))
    row = cursor.fetchone()
    if row:
      return dict(row)
  return load_backup().get("courses", {}).get(course_id)


def get_batch_data(batch_id):
  with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,))
    row = cursor.fetchone()
    if row:
      return dict(row)
  return load_backup().get("batches", {}).get(batch_id)


# --- ऑटोमैटिक UPI QR जनरेटर ---
def generate_upi_qr(amount, order_id):
  clean_amt = re.sub(r"[^\d.]", "", str(amount))
  upi_url = f"upi://pay?pa={UPI_ID}&pn={MERCHANT_NAME}&am={clean_amt}&cu=INR&tn=Order_{order_id}"

  qr = qrcode.QRCode(
      version=None,
      error_correction=qrcode.constants.ERROR_CORRECT_H,
      box_size=10,
      border=2,
  )
  qr.add_data(upi_url)
  qr.make(fit=True)

  qr_img = qr.make_image(fill_color="black", back_color="white").convert(
      "RGBA"
  )
  w, h = qr_img.size

  box_w = int(w * 0.36)
  box_h = int(box_w * 0.50)
  box_x = (w - box_w) // 2
  box_y = (h - box_h) // 2

  draw = ImageDraw.Draw(qr_img)
  draw.rounded_rectangle(
      [box_x - 2, box_y - 2, box_x + box_w + 2, box_y + box_h + 2],
      radius=8,
      fill="#0b1329",
  )
  draw.rounded_rectangle(
      [box_x, box_y, box_x + box_w, box_y + box_h], radius=6, fill="#ffffff"
  )

  arrow_x = box_x + int(box_w * 0.12)
  arrow_y = box_y + int(box_h * 0.18)
  arrow_h = int(box_h * 0.42)
  arrow_w = int(arrow_h * 0.55)

  draw.polygon(
      [
          (arrow_x, arrow_y),
          (arrow_x + arrow_w, arrow_y + (arrow_h // 2)),
          (arrow_x, arrow_y + arrow_h),
          (arrow_x + int(arrow_w * 0.4), arrow_y + (arrow_h // 2)),
      ],
      fill="#097939",
  )

  ox = arrow_x + int(arrow_w * 0.6)
  draw.polygon(
      [
          (ox, arrow_y),
          (ox + arrow_w, arrow_y + (arrow_h // 2)),
          (ox, arrow_y + arrow_h),
          (ox + int(arrow_w * 0.4), arrow_y + (arrow_h // 2)),
      ],
      fill="#F37021",
  )

  draw.rectangle(
      [
          arrow_x + arrow_w * 2 + 4,
          arrow_y + 2,
          arrow_x + arrow_w * 2 + 28,
          arrow_y + arrow_h - 2,
      ],
      fill="#111827",
  )

  strip_y = box_y + int(box_h * 0.68)
  draw.line(
      [(box_x + 6, strip_y), (box_x + box_w - 6, strip_y)],
      fill="#e2e8f0",
      width=1,
  )

  draw.ellipse(
      [
          box_x + int(box_w * 0.20),
          strip_y + 3,
          box_x + int(box_w * 0.20) + 6,
          strip_y + 9,
      ],
      fill="#1a73e8",
  )
  draw.ellipse(
      [
          box_x + int(box_w * 0.48),
          strip_y + 3,
          box_x + int(box_w * 0.48) + 6,
          strip_y + 9,
      ],
      fill="#5f259f",
  )
  draw.ellipse(
      [
          box_x + int(box_w * 0.76),
          strip_y + 3,
          box_x + int(box_w * 0.76) + 6,
          strip_y + 9,
      ],
      fill="#00b9f5",
  )

  bio = io.BytesIO()
  qr_img.save(bio, "PNG")
  bio.seek(0)
  return bio, clean_amt


# --- स्टेट मैनेजमेंट ---
admin_data = {}
user_states = {}
user_qr_messages = {}
pending_verifications = {}


# --- टाइमर फंक्शन्स ---
def expire_qr(chat_id, message_id, course_id):
  if (
      chat_id in user_states
      and user_states[chat_id].get("course_id") == course_id
  ):
    try:
      bot.delete_message(chat_id, message_id)
      bot.send_message(
          chat_id,
          "❌ **आपका पेमेंट सेशन (10 मिनट) एक्सपायर हो गया है!**\nकृपया फिर से"
          " शुरुआत करें।",
          parse_mode="Markdown",
      )
      del user_states[chat_id]
    except:
      pass


def expire_verification(user_id, checking_msg_id, admin_msg_id, course_id):
  if (
      user_id in pending_verifications
      and pending_verifications[user_id].get("course_id") == course_id
  ):
    try:
      bot.delete_message(user_id, checking_msg_id)
    except:
      pass

    try:
      bot.edit_message_caption(
          "❌ **Auto-Expired (5 Mins)** - No Action Taken",
          chat_id=DB_CHANNEL_ID,
          message_id=admin_msg_id,
          reply_markup=None,
      )
    except:
      pass

    markup = InlineKeyboardMarkup()
    if CHAT_LINK:
      markup.row(InlineKeyboardButton("💬 डायरेक्ट संपर्क करें", url=CHAT_LINK))
    try:
      bot.send_message(
          user_id,
          "⏳ **समय समाप्त!**\nएडमिन की तरफ से 5 मिनट में अप्रूवल नहीं मिला है।"
          " कृपया सीधे चैट पर संपर्क करें:",
          reply_markup=markup,
          parse_mode="Markdown",
      )
    except:
      pass

    del pending_verifications[user_id]


# --- मास्टर कोर्स डिस्प्ले फ़ंक्शन (100% गारंटीड कैप्शन और बटन डिलीवरी) ---
def send_course_to_user(chat_id, course):
  promo_items = json.loads(course["promo_media"])

  # 1. सारे बटन्स तैयार करना
  markup = InlineKeyboardMarkup()
  markup.row(
      InlineKeyboardButton(
          f"🇮🇳 UPI (Pay ₹{course['amount']})",
          callback_data=f"pay_upi_{course['course_id']}",
      )
  )
  
  bottom_buttons = []
  if INTERNATIONAL_LINK:
      bottom_buttons.append(InlineKeyboardButton("🌍 International", url=INTERNATIONAL_LINK))
  if CHAT_LINK:
      bottom_buttons.append(InlineKeyboardButton("💬 Chat with Me", url=CHAT_LINK))
  
  if bottom_buttons:
      markup.row(*bottom_buttons)

  # 2. मीडिया और कैप्शन को अलग-अलग करना
  media_group = []
  text_captions = []

  for item in promo_items:
      if item["type"] in ["photo", "video"] and item.get("file_id"):
          media_group.append(item)
      
      # सभी कैप्शन्स और टेक्स्ट मैसेजेस को एक साथ जोड़ना
      if item.get("caption"):
          text_captions.append(item["caption"].strip())
      elif item["type"] == "text" and item.get("caption"):
          text_captions.append(item["caption"].strip())

  # सभी टेक्स्ट को मिलाकर एक फाइनल कैप्शन बनाना
  combined_caption = "\n\n".join([t for t in text_captions if t])

  # --- CASE 1: अगर केवल 1 फोटो या 1 वीडियो है ---
  # (टेलीग्राम इसके साथ सीधे बटन और कैप्शन लगाने देता है)
  if len(media_group) == 1:
      item = media_group[0]
      final_text = f"{combined_caption}\n\n💰 **Price: ₹{course['amount']}**" if combined_caption else f"💰 **Price: ₹{course['amount']}**"
      
      try:
          if item["type"] == "photo":
              bot.send_photo(chat_id, item["file_id"], caption=final_text, reply_markup=markup, parse_mode="HTML")
          elif item["type"] == "video":
              bot.send_video(chat_id, item["file_id"], caption=final_text, reply_markup=markup, parse_mode="HTML")
      except:
          # HTML पार्सिंग फेल होने पर बिना पार्सिंग के भेजना
          if item["type"] == "photo":
              bot.send_photo(chat_id, item["file_id"], caption=final_text, reply_markup=markup)
          elif item["type"] == "video":
              bot.send_video(chat_id, item["file_id"], caption=final_text, reply_markup=markup)

  # --- CASE 2: अगर मल्टीपल मीडिया फाइल्स (Album) हैं ---
  # (एल्बम के साथ बटन नहीं लग सकते, इसलिए एल्बम पहले जाएगा, फिर कैप्शन+बटन का मैसेज)
  elif len(media_group) > 1:
      tg_media = []
      for it in media_group:
          if it["type"] == "photo":
              tg_media.append(InputMediaPhoto(it["file_id"]))
          elif it["type"] == "video":
              tg_media.append(InputMediaVideo(it["file_id"]))
      
      if tg_media:
          try:
              bot.send_media_group(chat_id, tg_media)
          except Exception as e:
              print(f"MediaGroup Error: {e}")
      
      # एल्बम के ठीक नीचे पूरा कैप्शन और बटन्स भेजें
      final_text = f"{combined_caption}\n\n👆 **इस कोर्स (₹{course['amount']}) को खरीदने के लिए विकल्प चुनें:**" if combined_caption else f"👆 **इस कोर्स (₹{course['amount']}) को खरीदने के लिए विकल्प चुनें:**"
      
      try:
          bot.send_message(chat_id, final_text, reply_markup=markup, parse_mode="HTML")
      except:
          bot.send_message(chat_id, final_text, reply_markup=markup)

  # --- CASE 3: अगर कोई फोटो/वीडियो नहीं है (सिर्फ टेक्स्ट) ---
  else:
      final_text = f"{combined_caption}\n\n💰 **Price: ₹{course['amount']}**" if combined_caption else f"💰 **Price: ₹{course['amount']}**"
      try:
          bot.send_message(chat_id, final_text, reply_markup=markup, parse_mode="HTML")
      except:
          bot.send_message(chat_id, final_text, reply_markup=markup)


# ==========================================
# 1. स्टार्ट कमांड
# ==========================================
@bot.message_handler(commands=["start"])
def start_command(message):
  param = (
      message.text.split()[1].strip() if len(message.text.split()) > 1 else ""
  )
  user_id = message.chat.id

  if param.startswith("b_"):
    batch = get_batch_data(param)
    if batch:
      bot.send_message(
          user_id,
          f"📦 **{batch['title']}**\nनीचे सभी कोर्सेज दिए गए हैं:",
          parse_mode="Markdown",
      )
      course_ids = json.loads(batch["course_ids"])
      for cid in course_ids:
        c_data = get_course_data(cid)
        if c_data:
          send_course_to_user(user_id, c_data)
    else:
      bot.send_message(user_id, "❌ यह बैच लिंक एक्सपायर हो गया है।")

  elif param.startswith("c_"):
    course = get_course_data(param)
    if course:
      send_course_to_user(user_id, course)
    else:
      bot.send_message(user_id, "❌ यह लिंक उपलब्ध नहीं है।")
  else:
    if user_id == ADMIN_ID:
      send_admin_panel(user_id)
    else:
      bot.send_message(
          user_id, "नमस्कार! कृपया कोर्स के सही लिंक पर क्लिक करके आएँ।"
      )


def send_admin_panel(chat_id):
  markup = InlineKeyboardMarkup()
  markup.row(
      InlineKeyboardButton(
          "➕ Add Single Course", callback_data="admin_add_course"
      )
  )
  markup.row(
      InlineKeyboardButton(
          "📦 Course Batch (मल्टी-कोर्स)", callback_data="admin_create_batch"
      )
  )
  markup.row(
      InlineKeyboardButton("👥 User Info", callback_data="admin_user_info")
  )
  bot.send_message(
      chat_id,
      "🛠 **एडमिन पैनल**\nकृपया कोई विकल्प चुनें:",
      reply_markup=markup,
  )


# ==========================================
# 2. एडमिन और यूज़र मैसेज हैंडलर
# ==========================================
@bot.message_handler(content_types=["photo", "video", "document", "text"])
def handle_all_messages(message):
  user_id = message.chat.id

  # --- ADMIN CREATION FLOW ---
  if user_id == ADMIN_ID and user_id in admin_data:
    step = admin_data[ADMIN_ID].get("step")

    if step == "TITLE":
      admin_data[ADMIN_ID]["title"] = message.text.strip()
      admin_data[ADMIN_ID]["step"] = "PROMO"
      admin_data[ADMIN_ID]["promo"] = []
      bot.send_message(
          ADMIN_ID,
          f"✅ बैच टाइटल सेव: **{admin_data[ADMIN_ID]['title']}**\n\n📝 **पहले"
          " कोर्स का प्रोमो मीडिया भेजें (फोटो/वीडियो)।**\n(भेजने के बाद नीचे"
          " 'Next' बटन दबाएं)",
          parse_mode="Markdown",
          reply_markup=InlineKeyboardMarkup().row(
              InlineKeyboardButton("➡️ Next Step", callback_data="next_price")
          ),
      )
      return

    elif step == "PROMO":
      media_type, file_id = None, None
      if message.photo:
        media_type, file_id = "photo", message.photo[-1].file_id
      elif message.video:
        media_type, file_id = "video", message.video.file_id
      elif message.text:
        media_type, file_id = "text", None

      if media_type:
        caption_text = message.caption or message.text or ""
        admin_data[ADMIN_ID]["promo"].append({
            "type": media_type,
            "file_id": file_id,
            "caption": caption_text,
        })
        bot.reply_to(message, f"✅ मीडिया/टेक्स्ट सेव! (कुल: {len(admin_data[ADMIN_ID]['promo'])})")
      return

    elif step == "AMOUNT":
      clean_amt = re.sub(r"[^\d.]", "", message.text.strip())
      if not clean_amt:
        bot.send_message(
            ADMIN_ID, "❌ कृपया केवल संख्या में कीमत लिखें (उदा: 199 या 499)।"
        )
        return
      admin_data[ADMIN_ID]["amount"] = clean_amt
      admin_data[ADMIN_ID]["step"] = "CAPTION"
      markup = InlineKeyboardMarkup().row(
          InlineKeyboardButton(
              "⏭ Skip (कोई कैप्शन नहीं)", callback_data="skip_caption"
          )
      )
      bot.send_message(
          ADMIN_ID,
          f"✅ **कीमत ₹{clean_amt} सेव!**\n\n📝 कोई अतिरिक्त कैप्शन या पेमेंट"
          " नोट लिखना है तो टाइप करें, वरना 'Skip' दबाएं।",
          reply_markup=markup,
      )
      return

    elif step == "CAPTION":
      admin_data[ADMIN_ID]["caption"] = message.text.strip()
      admin_data[ADMIN_ID]["step"] = "SECRET"
      bot.send_message(
          ADMIN_ID, "✅ **कैप्शन सेव!**\n\n🔗 अब इसका फाइनल सीक्रेट लिंक भेजें:"
      )
      return

    elif step == "SECRET":
      secret = message.text.strip()
      course_id = "c_" + str(uuid.uuid4())[:6]
      promo_json = json.dumps(admin_data[ADMIN_ID]["promo"])

      with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO courses VALUES (?, ?, ?, ?, ?)",
            (
                course_id,
                promo_json,
                admin_data[ADMIN_ID]["amount"],
                admin_data[ADMIN_ID]["caption"],
                secret,
            ),
        )
        conn.commit()

      bk = load_backup()
      bk["courses"][course_id] = {
          "promo_media": promo_json,
          "amount": admin_data[ADMIN_ID]["amount"],
          "custom_caption": admin_data[ADMIN_ID]["caption"],
          "secret_text": secret,
      }
      save_backup(bk)

      mode = admin_data[ADMIN_ID].get("mode")
      if mode == "single":
        link = f"https://t.me/{bot.get_me().username}?start={course_id}"
        bot.send_message(
            ADMIN_ID,
            f"🎉 **कोर्स बन गया!**\n\n💰 कीमत: ₹{admin_data[ADMIN_ID]['amount']}\n👉"
            f" `{link}`",
            parse_mode="Markdown",
        )
        del admin_data[ADMIN_ID]
        send_admin_panel(ADMIN_ID)

      elif mode == "batch":
        admin_data[ADMIN_ID]["course_ids"].append(course_id)
        admin_data[ADMIN_ID]["step"] = "NEXT_ACTION"
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton(
                "➕ Add Another Course", callback_data="batch_add_next"
            )
        )
        markup.row(
            InlineKeyboardButton("✅ Finish Batch", callback_data="batch_finish")
        )
        bot.send_message(
            ADMIN_ID,
            f"✅ **कोर्स सेव हो गया! (Total:"
            f" {len(admin_data[ADMIN_ID]['course_ids'])})**\n\nक्या आप इस बैच"
            " में एक और कोर्स जोड़ना चाहते हैं?",
            reply_markup=markup,
        )
      return

  # --- USER PAYMENT SUBMISSION ---
  if user_id in user_states and (message.photo or message.text):
    state_info = user_states[user_id]
    course_id = state_info["course_id"]
    order_id = state_info["order_id"]

    if user_id in user_qr_messages:
      try:
        bot.delete_message(user_id, user_qr_messages[user_id])
        del user_qr_messages[user_id]
      except:
        pass

    first_name = message.from_user.first_name or "User"
    username = (
        f"(@{message.from_user.username})" if message.from_user.username else ""
    )
    course = get_course_data(course_id)
    amt_text = course["amount"] if course else ""

    check_msg = bot.send_message(
        user_id, "⏳ आपका पेमेंट प्रूफ मिल गया है। 5 मिनट में अप्रूव हो जाएगा..."
    )

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(
            "✅ Approve", callback_data=f"app_{user_id}_{course_id}"
        ),
        InlineKeyboardButton(
            "❌ Deny", callback_data=f"den_{user_id}_{course_id}"
        ),
    )

    admin_text = (
        f"🔔 **New Verification!**\n\n"
        f"👤 User: {first_name} {username}\n"
        f"🆔 User ID: `{user_id}`\n"
        f"📚 Course: `{course_id}`\n"
        f"💰 Amount: ₹{amt_text}\n"
        f"🔖 Order ID: `{order_id}`"
    )

    try:
      if message.photo:
        admin_msg = bot.send_photo(
            DB_CHANNEL_ID,
            photo=message.photo[-1].file_id,
            caption=admin_text,
            reply_markup=markup,
            parse_mode="Markdown",
        )
      else:
        admin_text += f"\n🔢 Submitted UTR: `{message.text.strip()}`"
        admin_msg = bot.send_message(
            DB_CHANNEL_ID,
            admin_text,
            reply_markup=markup,
            parse_mode="Markdown",
        )

      pending_verifications[user_id] = {
          "checking_msg_id": check_msg.message_id,
          "admin_msg_id": admin_msg.message_id,
          "course_id": course_id,
      }
      threading.Timer(
          300,
          expire_verification,
          args=(user_id, check_msg.message_id, admin_msg.message_id, course_id),
      ).start()
    except Exception as e:
      bot.send_message(ADMIN_ID, f"⚠️ चैनल एरर: {e}")

    del user_states[user_id]


# ==========================================
# 3. सभी बटन्स को हैंडल करना
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
  data = call.data
  chat_id = call.message.chat.id
  msg_id = call.message.message_id

  # --- USER: UPI QR VIEW ---
  if data.startswith("pay_upi_"):
    bot.answer_callback_query(
        call.id, "⏳ Generating Payment QR...", show_alert=False
    )
    course_id = data.replace("pay_upi_", "")
    course = get_course_data(course_id)
    if course:
      order_id = str(uuid.uuid4())[:8]
      user_states[chat_id] = {"course_id": course_id, "order_id": order_id}

      qr_img_bio, clean_amt = generate_upi_qr(course["amount"], order_id)

      first_name = call.from_user.first_name or "User"
      username = (
          f"(@{call.from_user.username})" if call.from_user.username else ""
      )

      invoice_text = (
          f"👤 **User:** {first_name} {username}\n"
          f"🆔 **Order ID:** `{order_id}`\n"
          f"📅 **Date:** {datetime.now().strftime('%d-%m-%Y %I:%M %p')}\n"
          f"💰 **Amount:** ₹{clean_amt}\n"
          f"💳 **UPI ID (Tap to Copy):** `{UPI_ID}`\n"
      )
      if course.get("custom_caption"):
        invoice_text += f"\n📝 {course['custom_caption']}\n"

      invoice_text += (
          "\n👉 **Payment Instructions:**\n"
          "1. ऊपर दिए QR कोड को किसी भी UPI ऐप (PhonePe / GPay / Paytm) से स्कैन करें या UPI ID कॉपी करें।\n"
          "2. पेमेंट के बाद **12-अंकों का UTR No.** या **स्क्रीनशॉट** यहीं भेजें।\n\n"
          "⏳ *पेमेंट QR 10 मिनट में एक्सपायर हो जाएगा!*"
      )

      markup = InlineKeyboardMarkup()
      if CHAT_LINK:
        markup.row(InlineKeyboardButton("💬 Chat with Admin", url=CHAT_LINK))

      sent_msg = bot.send_photo(
          chat_id,
          photo=qr_img_bio,
          caption=invoice_text,
          reply_markup=markup,
          parse_mode="Markdown",
      )
      user_qr_messages[chat_id] = sent_msg.message_id
      threading.Timer(
          600, expire_qr, args=(chat_id, sent_msg.message_id, course_id)
      ).start()
    return

  bot.answer_callback_query(call.id)

  # --- ADMIN ACTIONS ---
  if data == "admin_add_course":
    admin_data[ADMIN_ID] = {
        "mode": "single",
        "step": "PROMO",
        "promo": [],
        "amount": None,
        "caption": "",
    }
    markup = InlineKeyboardMarkup().row(
        InlineKeyboardButton("➡️ Next Step", callback_data="next_price")
    )
    bot.edit_message_text(
        "📝 **Step 1/4: प्रोमो मीडिया**\nगैलरी से डेमो फोटो/वीडियो भेजें (एल्बम"
        " के लिए एक साथ चुनें)। फिर 'Next Step' दबाएं।",
        chat_id=chat_id,
        message_id=msg_id,
        reply_markup=markup,
    )

  elif data == "admin_create_batch":
    admin_data[ADMIN_ID] = {"mode": "batch", "step": "TITLE", "course_ids": []}
    bot.edit_message_text(
        "📦 **नया कोर्स बैच बनाएँ**\n\nकृपया इस बैच का **नाम/टाइटल** टाइप करके"
        " भेजें:",
        chat_id=chat_id,
        message_id=msg_id,
    )

  elif data == "next_price":
    if ADMIN_ID not in admin_data or not admin_data[ADMIN_ID].get("promo"):
      bot.answer_callback_query(
          call.id, "❌ पहले मीडिया भेजें!", show_alert=True
      )
      return
    admin_data[ADMIN_ID]["step"] = "AMOUNT"
    bot.edit_message_text(
        "💰 **Step 2/4: कीमत**\n\nइस कोर्स की कीमत (₹) भेजें (उदा: `299` या"
        " `499`):",
        chat_id=chat_id,
        message_id=msg_id,
    )

  elif data == "skip_caption":
    if ADMIN_ID in admin_data:
      admin_data[ADMIN_ID]["caption"] = ""
      admin_data[ADMIN_ID]["step"] = "SECRET"
      bot.edit_message_text(
          "✅ **कैप्शन स्किप!**\n\n🔗 **Step 4/4: फाइनल लिंक**\nफाइनल सीक्रेट"
          " लिंक भेजें।",
          chat_id=chat_id,
          message_id=msg_id,
      )

  elif data == "batch_add_next":
    admin_data[ADMIN_ID]["step"] = "PROMO"
    admin_data[ADMIN_ID]["promo"] = []
    admin_data[ADMIN_ID]["caption"] = ""
    markup = InlineKeyboardMarkup().row(
        InlineKeyboardButton("➡️ Next Step", callback_data="next_price")
    )
    bot.edit_message_text(
        "📝 **अगले कोर्स का प्रोमो मीडिया भेजें**\nफिर 'Next Step' दबाएं।",
        chat_id=chat_id,
        message_id=msg_id,
        reply_markup=markup,
    )

  elif data == "batch_finish":
    d = admin_data.get(ADMIN_ID)
    if not d or not d.get("course_ids"):
      return

    batch_id = "b_" + str(uuid.uuid4())[:6]
    c_ids_json = json.dumps(d["course_ids"])

    with get_db() as conn:
      cursor = conn.cursor()
      cursor.execute(
          "INSERT OR REPLACE INTO batches VALUES (?, ?, ?)",
          (batch_id, d["title"], c_ids_json),
      )
      conn.commit()

    bk = load_backup()
    bk["batches"][batch_id] = {
        "batch_id": batch_id,
        "title": d["title"],
        "course_ids": c_ids_json,
    }
    save_backup(bk)

    link = f"https://t.me/{bot.get_me().username}?start={batch_id}"
    bot.edit_message_text(
        f"🎉 **कोर्स बैच बन गया!**\n\n📦 **Title:** {d['title']}\n📚 **Total"
        f" Courses:** {len(d['course_ids'])}\n\n👉 `{link}` 👈",
        chat_id=chat_id,
        message_id=msg_id,
        parse_mode="Markdown",
    )
    del admin_data[ADMIN_ID]
    send_admin_panel(ADMIN_ID)

  elif data == "admin_user_info":
    with get_db() as conn:
      cursor = conn.cursor()
      cursor.execute(
          "SELECT username, date, item_info FROM purchases ORDER BY id DESC"
          " LIMIT 15"
      )
      records = cursor.fetchall()

    if not records:
      bot.edit_message_text(
          "अभी तक किसी ने कोर्स नहीं खरीदा है।",
          chat_id=chat_id,
          message_id=msg_id,
      )
    else:
      text = "👥 **Recent Purchases:**\n\n"
      for r in records:
        text += (
            f"👤 {r['username']} | 📅 {r['date'][:10]} | 📚 `{r['item_info']}`\n"
        )
      markup = InlineKeyboardMarkup().row(
          InlineKeyboardButton("🔙 Back", callback_data="back_to_admin")
      )
      bot.edit_message_text(
          text,
          chat_id=chat_id,
          message_id=msg_id,
          reply_markup=markup,
          parse_mode="Markdown",
      )

  elif data == "back_to_admin":
    try:
      bot.delete_message(chat_id, msg_id)
    except:
      pass
    send_admin_panel(chat_id)

  # --- ADMIN: APPROVE ---
  elif data.startswith("app_"):
    parts = data.split("_", 2)
    user_id, course_id = int(parts[1]), parts[2]

    if user_id in pending_verifications:
      try:
        bot.delete_message(
            user_id, pending_verifications[user_id]["checking_msg_id"]
        )
      except:
        pass
      del pending_verifications[user_id]

    course = get_course_data(course_id)
    if course:
      try:
        bot.send_message(
            user_id,
            f"🎉 **Payment Approved!**\n\n{course['secret_text']}",
            parse_mode="Markdown",
        )
      except:
        pass

      date_now = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
      try:
        user_info = bot.get_chat(user_id)
        user_name = (
            f"{user_info.first_name} (@{user_info.username})"
            if user_info.username
            else f"{user_info.first_name}"
        )
        uname = (
            f"@{user_info.username}" if user_info.username else user_info.first_name
        )
      except:
        user_name = "User"
        uname = "User"

      with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO purchases (user_id, username, item_info, date) VALUES"
            " (?, ?, ?, ?)",
            (
                user_id,
                uname,
                f"{course_id} | Rate: ₹{course['amount']} | APPROVED",
                date_now,
            ),
        )
        conn.commit()

      receipt = (
          f"✅ **[PAYMENT APPROVED & DELIVERED]**\n\n"
          f"👤 **User:** {user_name}\n"
          f"🆔 **ID:** `{user_id}`\n"
          f"📚 **Course:** `{course_id}`\n"
          f"💰 **Rate:** ₹{course['amount']}\n"
          f"📅 **Date:** {date_now}"
      )

      if call.message.content_type == "photo":
        bot.edit_message_caption(
            receipt,
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="Markdown",
        )
      else:
        bot.edit_message_text(
            receipt,
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="Markdown",
        )

  # --- ADMIN: DENY ---
  elif data.startswith("den_"):
    parts = data.split("_", 2)
    user_id, course_id = parts[1], parts[2]
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(
            "1️⃣ Fake Screenshot",
            callback_data=f"rsn_fake_{user_id}_{course_id}",
        )
    )
    markup.row(
        InlineKeyboardButton(
            "2️⃣ Payment Not Received",
            callback_data=f"rsn_notrecv_{user_id}_{course_id}",
        )
    )
    markup.row(
        InlineKeyboardButton(
            "3️⃣ Wrong Amount", callback_data=f"rsn_wrong_{user_id}_{course_id}"
        )
    )
    bot.edit_message_reply_markup(
        chat_id=chat_id, message_id=msg_id, reply_markup=markup
    )

  # --- ADMIN: REASON SELECTED ---
  elif data.startswith("rsn_"):
    parts = data.split("_")
    reason_code, user_id, course_id = parts[1], int(parts[2]), parts[3]
    if reason_code == "fake":
      reason = "आपका स्क्रीनशॉट अमान्य/फेक है।"
    elif reason_code == "notrecv":
      reason = "हमें आपका पेमेंट प्राप्त नहीं हुआ।"
    elif reason_code == "wrong":
      reason = "आपने गलत राशि भेजी है।"

    if user_id in pending_verifications:
      try:
        bot.delete_message(
            user_id, pending_verifications[user_id]["checking_msg_id"]
        )
      except:
        pass
      del pending_verifications[user_id]

    course = get_course_data(course_id)
    rate_amt = course["amount"] if course else "-"

    retry_markup = InlineKeyboardMarkup().row(
        InlineKeyboardButton(
            "🔄 Try Again (QR जनरेट करें)", callback_data=f"pay_upi_{course_id}"
        )
    )
    try:
      bot.send_message(
          user_id,
          f"❌ **Payment Denied!**\n\n**कारण:** {reason}",
          reply_markup=retry_markup,
          parse_mode="Markdown",
      )
    except:
      pass

    date_now = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
    try:
      user_info = bot.get_chat(user_id)
      user_name = (
          f"{user_info.first_name} (@{user_info.username})"
          if user_info.username
          else f"{user_info.first_name}"
      )
      uname = (
          f"@{user_info.username}" if user_info.username else user_info.first_name
      )
    except:
      user_name = "User"
      uname = "User"

    with get_db() as conn:
      cursor = conn.cursor()
      cursor.execute(
          "INSERT INTO purchases (user_id, username, item_info, date) VALUES"
          " (?, ?, ?, ?)",
          (
              user_id,
              uname,
              f"{course_id} | Rate: ₹{rate_amt} | REJECTED: {reason}",
              date_now,
          ),
      )
      conn.commit()

    receipt = (
        f"❌ **[PAYMENT REJECTED]**\n\n"
        f"👤 **User:** {user_name}\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"📚 **Course:** `{course_id}`\n"
        f"💰 **Rate:** ₹{rate_amt}\n"
        f"📅 **Date:** {date_now}\n"
        f"⚠️ **Reason:** {reason}"
    )

    if call.message.content_type == "photo":
      bot.edit_message_caption(
          receipt,
          chat_id=chat_id,
          message_id=msg_id,
          parse_mode="Markdown",
      )
    else:
      bot.edit_message_text(
          receipt,
          chat_id=chat_id,
          message_id=msg_id,
          parse_mode="Markdown",
      )


# ==========================================
# 4. Flask Web Server (Render 24/7 Hosting)
# ==========================================
app = Flask(__name__)


@app.route("/")
def home():
  return "Telegram Advanced Course Bot is Running Smoothly 24/7!"


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 10000))

  def run_bot():
    print("🚀 बोट पूरी तरह ओरिजिनल फ्लो में स्टार्ट हो गया है...")
    bot.infinity_polling(skip_pending=True)

  t = threading.Thread(target=run_bot, daemon=True)
  t.start()
  app.run(host="0.0.0.0", port=port)
