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
# 🛑 ENVIRONMENT VARIABLES (Render से लोड होंगी) 🛑
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0").strip())
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "0").strip())
UPI_ID = os.environ.get("UPI_ID", "").strip()
MERCHANT_NAME = os.environ.get("MERCHANT_NAME", "Study Wala").strip()

# डायरेक्ट लिंक्स
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
    cursor.execute("""CREATE TABLE IF NOT EXISTS active_orders (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER,
            course_id TEXT,
            status TEXT,
            created_at TEXT
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


# --- क्रॉस-प्लेटफॉर्म ब्रांडेड QR जनरेटर ---
def generate_upi_qr(amount, order_id):
  clean_amt = re.sub(r"[^\d.]", "", str(amount))
  upi_url = f"upi://pay?pa={UPI_ID}&pn={MERCHANT_NAME}&am={clean_amt}&cu=INR&tn=Order_{order_id}"

  qr = qrcode.QRCode(
      version=None,
      error_correction=qrcode.constants.ERROR_CORRECT_H,
      box_size=12,
      border=3,
  )
  qr.add_data(upi_url)
  qr.make(fit=True)

  qr_img = qr.make_image(
      fill_color="#0b1329", back_color="#ffffff"
  ).convert("RGBA")
  w, h = qr_img.size

  box_w = int(w * 0.38)
  box_h = int(box_w * 0.48)
  box_x = (w - box_w) // 2
  box_y = (h - box_h) // 2

  draw = ImageDraw.Draw(qr_img)
  draw.rounded_rectangle(
      [box_x - 3, box_y - 3, box_x + box_w + 3, box_y + box_h + 3],
      radius=12,
      fill="#0b1329",
  )
  draw.rounded_rectangle(
      [box_x, box_y, box_x + box_w, box_y + box_h], radius=10, fill="#ffffff"
  )

  # UPI Arrows
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

  # Center Block & App Dots
  draw.rectangle(
      [
          arrow_x + arrow_w * 2 + 5,
          arrow_y + 2,
          arrow_x + arrow_w * 2 + 35,
          arrow_y + arrow_h - 2,
      ],
      fill="#111827",
  )

  strip_y = box_y + int(box_h * 0.68)
  draw.line(
      [(box_x + 8, strip_y), (box_x + box_w - 8, strip_y)],
      fill="#e2e8f0",
      width=1,
  )

  draw.ellipse(
      [
          box_x + int(box_w * 0.20),
          strip_y + 4,
          box_x + int(box_w * 0.20) + 8,
          strip_y + 12,
      ],
      fill="#1a73e8",
  )
  draw.ellipse(
      [
          box_x + int(box_w * 0.48),
          strip_y + 4,
          box_x + int(box_w * 0.48) + 8,
          strip_y + 12,
      ],
      fill="#5f259f",
  )
  draw.ellipse(
      [
          box_x + int(box_w * 0.76),
          strip_y + 4,
          box_x + int(box_w * 0.76) + 8,
          strip_y + 12,
      ],
      fill="#00b9f5",
  )

  bio = io.BytesIO()
  qr_img.save(bio, "PNG")
  bio.seek(0)
  return bio, clean_amt


# --- स्टेट मैनेजमेंट ---
admin_data = {}
user_qr_messages = {}
pending_verifications = {}


# --- टाइमर फंक्शन्स ---
def expire_qr(chat_id, message_id, order_id):
  try:
    with get_db() as conn:
      cursor = conn.cursor()
      cursor.execute(
          "SELECT status FROM active_orders WHERE order_id=?", (order_id,)
      )
      row = cursor.fetchone()
      if row and row["status"] == "WAITING_PAYMENT":
        cursor.execute(
            "UPDATE active_orders SET status='EXPIRED' WHERE order_id=?",
            (order_id,),
        )
        conn.commit()
        bot.delete_message(chat_id, message_id)
        bot.send_message(
            chat_id,
            "❌ <b>आपका पेमेंट सेशन (10 मिनट) एक्सपायर हो गया है!</b>\nकृपया फिर से"
            " शुरुआत करें।",
            parse_mode="HTML",
        )
  except:
    pass


def expire_verification(user_id, checking_msg_id, admin_msg_id, order_id):
  if (
      user_id in pending_verifications
      and pending_verifications[user_id].get("order_id") == order_id
  ):
    try:
      bot.delete_message(user_id, checking_msg_id)
    except:
      pass

    try:
      bot.edit_message_caption(
          "❌ <b>Auto-Expired (5 Mins)</b> - No Action Taken",
          chat_id=DB_CHANNEL_ID,
          message_id=admin_msg_id,
          reply_markup=None,
          parse_mode="HTML",
      )
    except:
      pass

    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("💬 डायरेक्ट संपर्क करें", url=CHAT_LINK))
    try:
      bot.send_message(
          user_id,
          "⏳ <b>समय समाप्त!</b>\nएडमिन की तरफ से 5 मिनट में अप्रूवल नहीं मिला"
          " है। कृपया सीधे चैट पर संपर्क करें:",
          reply_markup=markup,
          parse_mode="HTML",
      )
    except:
      pass

    del pending_verifications[user_id]


# --- कोर्स डिस्प्ले फंक्शन ---
def send_course_to_user(chat_id, course):
  promo_items = json.loads(course["promo_media"])

  markup = InlineKeyboardMarkup()
  markup.row(
      InlineKeyboardButton(
          f"🇮🇳 UPI (Pay ₹{course['amount']})",
          callback_data=f"pay_upi_{course['course_id']}",
      )
  )
  markup.row(
      InlineKeyboardButton("🌍 International", url=INTERNATIONAL_LINK),
      InlineKeyboardButton("💬 Chat with Me", url=CHAT_LINK),
  )

  if len(promo_items) == 1:
    item = promo_items[0]
    caption_text = item.get("caption", "").strip()
    full_caption = (
        f"{caption_text}\n\n💰 <b>Price:</b> ₹{course['amount']}"
        if caption_text
        else f"💰 <b>Price:</b> ₹{course['amount']}"
    )

    if item["type"] == "photo":
      bot.send_photo(
          chat_id,
          item["file_id"],
          caption=full_caption,
          reply_markup=markup,
          parse_mode="HTML",
      )
    elif item["type"] == "video":
      bot.send_video(
          chat_id,
          item["file_id"],
          caption=full_caption,
          reply_markup=markup,
          parse_mode="HTML",
      )
    elif item["type"] == "text":
      bot.send_message(
          chat_id, full_caption, reply_markup=markup, parse_mode="HTML"
      )
  else:
    media_group = []
    for i, item in enumerate(promo_items):
      cap = item.get("caption", "").strip() if i == 0 else ""
      if i == 0 and not cap:
        cap = f"📚 Course Materials (₹{course['amount']})"

      if item["type"] == "photo":
        media_group.append(
            InputMediaPhoto(item["file_id"], caption=cap, parse_mode="HTML")
        )
      elif item["type"] == "video":
        media_group.append(
            InputMediaVideo(item["file_id"], caption=cap, parse_mode="HTML")
        )

    if media_group:
      try:
        bot.send_media_group(chat_id, media_group)
      except:
        pass

    bot.send_message(
        chat_id,
        f"🏷️ <b>Course Price: ₹{course['amount']}</b>\n👇 <i>नीचे दिए गए बटन से"
        " पेमेंट करें:</i>",
        reply_markup=markup,
        parse_mode="HTML",
    )


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
          f"📦 <b>{batch['title']}</b>\nनीचे सभी कोर्सेज दिए गए हैं:",
          parse_mode="HTML",
      )
      course_ids = json.loads(batch["course_ids"])
      for cid in course_ids:
        c_data = get_course_data(cid)
        if c_data:
          send_course_to_user(user_id, c_data)
    else:
      bot.send_message(
          user_id, "❌ यह बैच लिंक एक्सपायर हो गया है।", parse_mode="HTML"
      )

  elif param.startswith("c_"):
    course = get_course_data(param)
    if course:
      send_course_to_user(user_id, course)
    else:
      bot.send_message(
          user_id, "❌ यह लिंक उपलब्ध नहीं है।", parse_mode="HTML"
      )
  else:
    if user_id == ADMIN_ID:
      send_admin_panel(user_id)
    else:
      bot.send_message(
          user_id,
          "👋 <b>नमस्ते!</b>\nकोर्स एक्सेस करने के लिए कोर्स लिंक पर क्लिक"
          " करके बॉट स्टार्ट करें।",
          parse_mode="HTML",
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
      "🛠 <b>एडमिन कंट्रोल पैनल</b>\nकृपया कोई विकल्प चुनें:",
      reply_markup=markup,
      parse_mode="HTML",
  )


# ==========================================
# 2. एडमिन और यूज़र मैसेज हैंडलर
# ==========================================
@bot.message_handler(content_types=["photo", "video", "document", "text"])
def handle_all_messages(message):
  user_id = message.chat.id

  # --- ADMIN FLOW ---
  if user_id == ADMIN_ID and user_id in admin_data:
    step = admin_data[ADMIN_ID].get("step")

    if step == "TITLE":
      admin_data[ADMIN_ID]["title"] = message.text.strip()
      admin_data[ADMIN_ID]["step"] = "PROMO"
      admin_data[ADMIN_ID]["promo"] = []
      bot.send_message(
          ADMIN_ID,
          f"✅ बैच टाइटल सेव: <b>{admin_data[ADMIN_ID]['title']}</b>\n\n📝"
          " <b>पहले कोर्स का प्रोमो मीडिया भेजें (फोटो/वीडियो)।</b>\n(भेजने के"
          " बाद नीचे 'Next' बटन दबाएं)",
          parse_mode="HTML",
          reply_markup=InlineKeyboardMarkup().row(
              InlineKeyboardButton("➡️ Next: Set Price", callback_data="next_price")
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
        bot.reply_to(
            message,
            f"✅ मीडिया सेव! (कुल: {len(admin_data[ADMIN_ID]['promo'])})",
        )
      return

    elif step == "AMOUNT":
      clean_amt = re.sub(r"[^\d.]", "", message.text.strip())
      if not clean_amt:
        bot.send_message(
            ADMIN_ID,
            "❌ कृपया केवल संख्या में कीमत लिखें (उदा: 199 या 499)।",
            parse_mode="HTML",
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
          f"✅ <b>कीमत ₹{clean_amt} सेव!</b>\n\n📝 कोई अतिरिक्त कैप्शन या पेमेंट"
          " नोट लिखना है तो टाइप करें, वरना 'Skip' दबाएं।",
          reply_markup=markup,
          parse_mode="HTML",
      )
      return

    elif step == "CAPTION":
      admin_data[ADMIN_ID]["caption"] = message.text.strip()
      admin_data[ADMIN_ID]["step"] = "SECRET"
      bot.send_message(
          ADMIN_ID,
          "✅ <b>कैप्शन सेव!</b>\n\n🔗 अब इसका फाइनल सीक्रेट लिंक/फाइल्स मैसेज"
          " भेजें:",
          parse_mode="HTML",
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
            f"🎉 <b>कोर्स बन गया!</b>\n\n💰 कीमत: ₹{admin_data[ADMIN_ID]['amount']}\n🔗"
            f" लिंक:\n<code>{link}</code>",
            parse_mode="HTML",
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
            f"✅ <b>कोर्स सेव हो गया! (Total:"
            f" {len(admin_data[ADMIN_ID]['course_ids'])})</b>\n\nक्या आप इस बैच"
            " में एक और कोर्स जोड़ना चाहते हैं?",
            reply_markup=markup,
            parse_mode="HTML",
        )
      return

  # --- USER PAYMENT VERIFICATION ---
  with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM active_orders WHERE user_id=? AND"
        " status='WAITING_PAYMENT' ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    active_order = cursor.fetchone()

  if active_order:
    order_id = active_order["order_id"]
    course_id = active_order["course_id"]

    if user_id in user_qr_messages:
      try:
        bot.delete_message(user_id, user_qr_messages[user_id])
        del user_qr_messages[user_id]
      except:
        pass

    first_name = message.from_user.first_name or "User"
    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "No Username"
    )
    course = get_course_data(course_id)
    amt_text = course["amount"] if course else ""

    check_msg = bot.send_message(
        user_id,
        "⏳ आपकी पेमेंट डिटेल्स मिल गई हैं। 5 मिनट के अंदर वेरिफिकेशन हो जाएगा...",
        parse_mode="HTML",
    )

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(
            "✅ Approve", callback_data=f"app_{user_id}_{course_id}_{order_id}"
        )
    )
    markup.row(
        InlineKeyboardButton(
            "❌ Deny", callback_data=f"den_{user_id}_{course_id}_{order_id}"
        )
    )

    date_str = datetime.now().strftime("%d-%m-%Y %I:%M %p")
    admin_text = (
        f"🔔 <b>Pending Payment Verification</b>\n\n"
        f"👤 <b>Name:</b> {first_name} ({username})\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"📚 <b>Course ID:</b> <code>{course_id}</code>\n"
        f"💰 <b>Amount (Rate):</b> ₹{amt_text}\n"
        f"📅 <b>Date:</b> {date_str}\n"
        f"🔖 <b>Order ID:</b> <code>{order_id}</code>"
    )

    try:
      if message.photo:
        admin_msg = bot.send_photo(
            DB_CHANNEL_ID,
            photo=message.photo[-1].file_id,
            caption=admin_text,
            reply_markup=markup,
            parse_mode="HTML",
        )
      else:
        admin_text += (
            f"\n🔢 <b>Submitted UTR:</b> <code>{message.text.strip()}</code>"
        )
        admin_msg = bot.send_message(
            DB_CHANNEL_ID,
            admin_text,
            reply_markup=markup,
            parse_mode="HTML",
        )

      with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE active_orders SET status='VERIFYING' WHERE order_id=?",
            (order_id,),
        )
        conn.commit()

      pending_verifications[user_id] = {
          "checking_msg_id": check_msg.message_id,
          "admin_msg_id": admin_msg.message_id,
          "order_id": order_id,
      }
      threading.Timer(
          300,
          expire_verification,
          args=(user_id, check_msg.message_id, admin_msg.message_id, order_id),
      ).start()
    except Exception as e:
      bot.send_message(
          ADMIN_ID, f"⚠️ चैनल एरर: {e}", parse_mode="HTML"
      )


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
        call.id,
        "⏳ Generating your secure UPI QR... Please wait!",
        show_alert=False,
    )
    bot.send_chat_action(chat_id, "upload_photo")

    course_id = data.replace("pay_upi_", "")
    course = get_course_data(course_id)
    if course:
      order_id = str(uuid.uuid4())[:8]
      date_now = datetime.now().strftime("%d-%m-%Y %I:%M %p")

      with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO active_orders VALUES (?, ?, ?, ?, ?)",
            (order_id, chat_id, course_id, "WAITING_PAYMENT", date_now),
        )
        conn.commit()

      qr_img_bio, clean_amt = generate_upi_qr(course["amount"], order_id)

      first_name = call.from_user.first_name or "User"
      username = (
          f"(@{call.from_user.username})" if call.from_user.username else ""
      )

      invoice_text = (
          f"👤 <b>User:</b> {first_name} {username}\n"
          f"🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
          f"📅 <b>Date:</b> {date_now}\n"
          f"💰 <b>Amount:</b> ₹{clean_amt}\n"
          f"💳 <b>UPI ID (Tap to Copy):</b> <code>{UPI_ID}</code>\n"
      )
      if course.get("custom_caption"):
        invoice_text += f"\n📝 {course['custom_caption']}\n"

      invoice_text += (
          "\n👉 <b>Payment Instructions:</b>\n"
          "1. Scan the QR code using any UPI app (<b>PhonePe / GPay /"
          " Paytm</b>) or copy the UPI ID above.\n"
          "2. After payment, send the <b>12-digit UTR Number</b> or"
          " <b>Screenshot</b> here in chat.\n\n"
          "⏳ <i>Note: This QR code is valid for 10 minutes.</i>"
      )

      markup = InlineKeyboardMarkup()
      markup.row(InlineKeyboardButton("💬 Chat with Admin", url=CHAT_LINK))

      sent_msg = bot.send_photo(
          chat_id,
          photo=qr_img_bio,
          caption=invoice_text,
          reply_markup=markup,
          parse_mode="HTML",
      )
      user_qr_messages[chat_id] = sent_msg.message_id
      threading.Timer(
          600, expire_qr, args=(chat_id, sent_msg.message_id, order_id)
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
        InlineKeyboardButton("➡️ Next: Set Price", callback_data="next_price")
    )
    bot.edit_message_text(
        "📝 <b>Step 1/4: प्रोमो मीडिया</b>\nगैलरी से डेमो फोटो/वीडियो भेजें"
        " (एल्बम के लिए एक साथ चुनें)।\nभेजने के बाद 'Next: Set Price' दबाएं।",
        chat_id=chat_id,
        message_id=msg_id,
        reply_markup=markup,
        parse_mode="HTML",
    )

  elif data == "admin_create_batch":
    admin_data[ADMIN_ID] = {"mode": "batch", "step": "TITLE", "course_ids": []}
    bot.edit_message_text(
        "📦 <b>नया कोर्स बैच बनाएँ</b>\n\nकृपया इस बैच का <b>नाम/टाइटल</b>"
        " टाइप करके भेजें:",
        chat_id=chat_id,
        message_id=msg_id,
        parse_mode="HTML",
    )

  elif data == "next_price":
    if ADMIN_ID not in admin_data or not admin_data[ADMIN_ID].get("promo"):
      bot.answer_callback_query(
          call.id, "❌ पहले कम से कम 1 फोटो/वीडियो भेजें!", show_alert=True
      )
      return
    admin_data[ADMIN_ID]["step"] = "AMOUNT"
    bot.edit_message_text(
        "💰 <b>Step 2/4: कीमत (Price)</b>\n\nइस कोर्स की कीमत (₹) टाइप करके"
        " भेजें (उदा: <code>299</code> या <code>499</code>):",
        chat_id=chat_id,
        message_id=msg_id,
        parse_mode="HTML",
    )

  elif data == "skip_caption":
    if ADMIN_ID in admin_data:
      admin_data[ADMIN_ID]["caption"] = ""
      admin_data[ADMIN_ID]["step"] = "SECRET"
      bot.edit_message_text(
          "✅ <b>कैप्शन स्किप!</b>\n\n🔗 <b>Step 4/4: फाइनल लिंक</b>\nफाइनल"
          " सीक्रेट लिंक/मैसेज भेजें।",
          chat_id=chat_id,
          message_id=msg_id,
          parse_mode="HTML",
      )

  elif data == "batch_add_next":
    admin_data[ADMIN_ID]["step"] = "PROMO"
    admin_data[ADMIN_ID]["promo"] = []
    admin_data[ADMIN_ID]["caption"] = ""
    markup = InlineKeyboardMarkup().row(
        InlineKeyboardButton("➡️ Next: Set Price", callback_data="next_price")
    )
    bot.edit_message_text(
        "📝 <b>अगले कोर्स का प्रोमो मीडिया भेजें</b>\nफिर 'Next: Set Price'"
        " दबाएं।",
        chat_id=chat_id,
        message_id=msg_id,
        reply_markup=markup,
        parse_mode="HTML",
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
        f"🎉 <b>कोर्स बैच बन गया!</b>\n\n📦 <b>Title:</b> {d['title']}\n📚"
        f" <b>Total Courses:</b> {len(d['course_ids'])}\n\n👉"
        f" <code>{link}</code> 👈",
        chat_id=chat_id,
        message_id=msg_id,
        parse_mode="HTML",
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
          parse_mode="HTML",
      )
    else:
      text = "👥 <b>Recent Purchases:</b>\n\n"
      for r in records:
        text += (
            f"👤 {r['username']} | 📅 {r['date'][:10]} | 📚"
            f" <code>{r['item_info']}</code>\n"
        )
      markup = InlineKeyboardMarkup().row(
          InlineKeyboardButton("🔙 Back", callback_data="back_to_admin")
      )
      bot.edit_message_text(
          text,
          chat_id=chat_id,
          message_id=msg_id,
          reply_markup=markup,
          parse_mode="HTML",
      )

  elif data == "back_to_admin":
    try:
      bot.delete_message(chat_id, msg_id)
    except:
      pass
    send_admin_panel(chat_id)

  # --- ADMIN: APPROVE ---
  elif data.startswith("app_"):
    parts = data.split("_")
    user_id, course_id, order_id = int(parts[1]), parts[2], parts[3]

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
            f"🎉 <b>Payment Approved!</b>\n\n{course['secret_text']}",
            parse_mode="HTML",
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

      course_detail = (
          course.get("custom_caption") if course.get("custom_caption") else "-"
      )

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
        cursor.execute(
            "UPDATE active_orders SET status='APPROVED' WHERE order_id=?",
            (order_id,),
        )
        conn.commit()

      approved_receipt = (
          f"✅ <b>[PAYMENT APPROVED & DELIVERED]</b>\n\n"
          f"👤 <b>User Name:</b> {user_name}\n"
          f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
          f"📚 <b>Course ID:</b> <code>{course_id}</code>\n"
          f"📝 <b>Course Info:</b> {course_detail}\n"
          f"💰 <b>Rate / Price:</b> ₹{course['amount']}\n"
          f"📅 <b>Approved On:</b> {date_now}\n"
          f"⚡ <b>Status:</b> Access Granted & Files Sent"
      )

      if call.message.content_type == "photo":
        bot.edit_message_caption(
            approved_receipt,
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="HTML",
        )
      else:
        bot.edit_message_text(
            approved_receipt,
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="HTML",
        )

  # --- ADMIN: DENY ---
  elif data.startswith("den_"):
    parts = data.split("_")
    user_id, course_id, order_id = parts[1], parts[2], parts[3]
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(
            "1️⃣ Fake Screenshot / UTR",
            callback_data=f"rsn_fake_{user_id}_{course_id}_{order_id}",
        )
    )
    markup.row(
        InlineKeyboardButton(
            "2️⃣ Payment Not Received",
            callback_data=f"rsn_notrecv_{user_id}_{course_id}_{order_id}",
        )
    )
    markup.row(
        InlineKeyboardButton(
            "3️⃣ Wrong Amount",
            callback_data=f"rsn_wrong_{user_id}_{course_id}_{order_id}",
        )
    )
    bot.edit_message_reply_markup(
        chat_id=chat_id, message_id=msg_id, reply_markup=markup
    )

  # --- ADMIN: REASON SELECTED ---
  elif data.startswith("rsn_"):
    parts = data.split("_")
    reason_code, user_id, course_id, order_id = (
        parts[1],
        int(parts[2]),
        parts[3],
        parts[4],
    )
    if reason_code == "fake":
      reason = "आपका UTR या स्क्रीनशॉट अमान्य/फेक है।"
    elif reason_code == "notrecv":
      reason = "हमें आपका पेमेंट बैंक में प्राप्त नहीं हुआ है।"
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
    course_detail = (
        course.get("custom_caption") if course and course.get("custom_caption") else "-"
    )

    retry_markup = InlineKeyboardMarkup().row(
        InlineKeyboardButton(
            "🔄 Try Again (QR जनरेट करें)", callback_data=f"pay_upi_{course_id}"
        )
    )
    try:
      bot.send_message(
          user_id,
          f"❌ <b>Payment Denied!</b>\n\n<b>कारण:</b> {reason}",
          reply_markup=retry_markup,
          parse_mode="HTML",
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
      cursor.execute(
          "UPDATE active_orders SET status='REJECTED' WHERE order_id=?",
          (order_id,),
      )
      conn.commit()

    denied_receipt = (
        f"❌ <b>[PAYMENT REJECTED / DENIED]</b>\n\n"
        f"👤 <b>User Name:</b> {user_name}\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"📚 <b>Course ID:</b> <code>{course_id}</code>\n"
        f"📝 <b>Course Info:</b> {course_detail}\n"
        f"💰 <b>Rate / Price:</b> ₹{rate_amt}\n"
        f"📅 <b>Date & Time:</b> {date_now}\n"
        f"⚠️ <b>Reason:</b> {reason}"
    )

    if call.message.content_type == "photo":
      bot.edit_message_caption(
          denied_receipt,
          chat_id=chat_id,
          message_id=msg_id,
          parse_mode="HTML",
      )
    else:
      bot.edit_message_text(
          denied_receipt,
          chat_id=chat_id,
          message_id=msg_id,
          parse_mode="HTML",
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
    print("🚀 बोट पूरी तरह तैयार होकर स्टार्ट हो गया है...")
    bot.infinity_polling(skip_pending=True)

  t = threading.Thread(target=run_bot, daemon=True)
  t.start()
  app.run(host="0.0.0.0", port=port)
