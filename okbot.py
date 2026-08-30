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
    "BOT_TOKEN", "8986044820:AAFgYI_F_MH0LQT5VX95_umWjkUaMx9cfug"
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
          "❌ <b>Your payment session (10 minutes) has expired! Please try again.</b>\n"
          "<i>(Aapka payment session expire ho gaya hai. Kripya wapas try karein.)</i>",
          parse_mode="HTML",
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
          "❌ <b>Auto-Expired (5 Mins)</b> - No Action Taken",
          chat_id=DB_CHANNEL_ID,
          message_id=admin_msg_id,
          reply_markup=None,
          parse_mode="HTML"
      )
    except:
      pass

    markup = InlineKeyboardMarkup()
    if CHAT_LINK:
      markup.row(InlineKeyboardButton("💬 Contact Directly", url=CHAT_LINK))
    try:
      bot.send_message(
          user_id,
          "⏳ <b>Time's up!</b>\nNo approval received from admin in 5 minutes. Please contact directly via chat:\n\n"
          "<i>(Time khatam! Admin ki taraf se 5 minute mein approval nahi mila. Kripya direct chat par message karein:)</i>",
          reply_markup=markup,
          parse_mode="HTML",
      )
    except:
      pass

    del pending_verifications[user_id]


# ==========================================
# 🛑 मास्टर कोर्स डिलीवरी (SAFE CAPTION SYSTEM) 🛑
# ==========================================
def send_course_to_user(chat_id, course):
  try:
    promo_items = json.loads(course["promo_media"])
  except:
    promo_items = []

  # 1. बटन्स तैयार करें
  markup = InlineKeyboardMarkup()
  markup.row(
      InlineKeyboardButton(
          f"🇮🇳 UPI (Pay ₹{course['amount']})",
          callback_data=f"pay_upi_{course['course_id']}",
      )
  )
  
  btn_row = []
  if INTERNATIONAL_LINK:
      btn_row.append(InlineKeyboardButton("🌍 International", url=INTERNATIONAL_LINK))
  if CHAT_LINK:
      btn_row.append(InlineKeyboardButton("💬 Chat with Me", url=CHAT_LINK))
  if btn_row: 
      markup.row(*btn_row)

  # 2. मीडिया फिल्टर करें
  media_items = [it for it in promo_items if it["type"] in ["photo", "video"]]

  # 3. पूरा कैप्शन कलेक्ट करें
  first_photo_caption = ""
  for it in media_items:
      if it.get("caption"):
          first_photo_caption = it["caption"].strip()
          break
          
  custom_caption = course.get("custom_caption", "").strip()

  final_album_caption = ""
  if first_photo_caption and custom_caption:
      final_album_caption = f"{first_photo_caption}\n\n{custom_caption}"
  elif first_photo_caption:
      final_album_caption = first_photo_caption
  elif custom_caption:
      final_album_caption = custom_caption

  if len(final_album_caption) > 1000:
      final_album_caption = final_album_caption[:1000] + "..."

  # --- CASE 1: सिर्फ 1 फोटो/वीडियो है ---
  if len(media_items) == 1:
    item = media_items[0]
    try:
      if item["type"] == "photo":
        bot.send_photo(chat_id, item["file_id"], caption=final_album_caption, reply_markup=markup, parse_mode="HTML")
      elif item["type"] == "video":
        bot.send_video(chat_id, item["file_id"], caption=final_album_caption, reply_markup=markup, parse_mode="HTML")
    except:
      if item["type"] == "photo":
        bot.send_photo(chat_id, item["file_id"], caption=final_album_caption, reply_markup=markup)
      elif item["type"] == "video":
        bot.send_video(chat_id, item["file_id"], caption=final_album_caption, reply_markup=markup)

  # --- CASE 2: मल्टीपल मीडिया (एल्बम) है ---
  elif len(media_items) > 1:
    media_group_html = []
    media_group_plain = []
    
    for i, item in enumerate(media_items):
      cap = final_album_caption if i == 0 else "" 
      if item["type"] == "photo":
        media_group_html.append(InputMediaPhoto(item["file_id"], caption=cap, parse_mode="HTML"))
        media_group_plain.append(InputMediaPhoto(item["file_id"], caption=cap))
      elif item["type"] == "video":
        media_group_html.append(InputMediaVideo(item["file_id"], caption=cap, parse_mode="HTML"))
        media_group_plain.append(InputMediaVideo(item["file_id"], caption=cap))

    try: 
      bot.send_media_group(chat_id, media_group_html)
    except: 
      try: bot.send_media_group(chat_id, media_group_plain)
      except Exception as e: print(f"MediaGroup Error: {e}")

    try:
      bot.send_message(
          chat_id,
          f"👆 <b>Choose an option to buy this course (₹{course['amount']}):</b>\n"
          f"<i>(Is course ko kharidne ke liye option chunein:)</i>",
          reply_markup=markup,
          parse_mode="HTML"
      )
    except:
      bot.send_message(
          chat_id, 
          f"👆 Choose an option to buy this course (₹{course['amount']}):\n(Is course ko kharidne ke liye option chunein:)", 
          reply_markup=markup
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
          f"📦 <b>{batch['title']}</b>\nAll courses are listed below:\n"
          f"<i>(Niche sabhi courses diye gaye hain:)</i>",
          parse_mode="HTML",
      )
      course_ids = json.loads(batch["course_ids"])
      for cid in course_ids:
        c_data = get_course_data(cid)
        if c_data:
          send_course_to_user(user_id, c_data)
    else:
      bot.send_message(user_id, "❌ <b>This batch link has expired.</b>\n<i>(Yeh batch link expire ho gaya hai.)</i>", parse_mode="HTML")

  elif param.startswith("c_"):
    course = get_course_data(param)
    if course:
      send_course_to_user(user_id, course)
    else:
      bot.send_message(user_id, "❌ <b>This link is not available.</b>\n<i>(Yeh link available nahi hai.)</i>", parse_mode="HTML")
  else:
    if user_id == ADMIN_ID:
      send_admin_panel(user_id)
    else:
      bot.send_message(
          user_id, "👋 <b>Hello! Please click on the correct course link to enter.</b>\n<i>(Namaste! Kripya sahi course link par click karke aayein.)</i>", parse_mode="HTML"
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
          "📦 Course Batch (Multi-Course)", callback_data="admin_create_batch"
      )
  )
  markup.row(
      InlineKeyboardButton("👥 User Info", callback_data="admin_user_info")
  )
  bot.send_message(
      chat_id,
      "🛠 <b>Admin Panel</b>\nPlease select an option:\n"
      "<i>(Kripya koi option chunein:)</i>",
      reply_markup=markup,
      parse_mode="HTML"
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
          f"✅ Batch title saved: <b>{admin_data[ADMIN_ID]['title']}</b>\n\n"
          "📝 <b>Send the promo media (photo/video) for the first course.</b>\n"
          "<i>(Pehle course ka promo media bhejein. Bhejne ke baad niche 'Next' button dabayein.)</i>",
          parse_mode="HTML",
          reply_markup=InlineKeyboardMarkup().row(
              InlineKeyboardButton("➡️ Next Step", callback_data="next_price")
          ),
      )
      return

    elif step == "PROMO":
      media_type, file_id = "text", None
      if message.photo:
        media_type, file_id = "photo", message.photo[-1].file_id
      elif message.video:
        media_type, file_id = "video", message.video.file_id

      admin_data[ADMIN_ID]["promo"].append({
          "type": media_type,
          "file_id": file_id,
          "caption": message.caption or message.text or "",
      })
      return

    elif step == "AMOUNT":
      clean_amt = re.sub(r"[^\d.]", "", message.text.strip())
      if not clean_amt:
        bot.send_message(
            ADMIN_ID, "❌ <b>Please enter the price in numbers only (e.g., 199 or 499).</b>\n<i>(Kripya sirf numbers mein price likhein.)</i>", parse_mode="HTML"
        )
        return
      admin_data[ADMIN_ID]["amount"] = clean_amt
      admin_data[ADMIN_ID]["step"] = "CAPTION"
      markup = InlineKeyboardMarkup().row(
          InlineKeyboardButton(
              "⏭ Skip (No Caption)", callback_data="skip_caption"
          )
      )
      bot.send_message(
          ADMIN_ID,
          f"✅ <b>Price ₹{clean_amt} saved!</b>\n\n📝 Type any extra caption or payment note, otherwise press 'Skip'.\n"
          "<i>(Koi extra caption likhna hai toh type karein, warna 'Skip' dabayein.)</i>",
          reply_markup=markup,
          parse_mode="HTML"
      )
      return

    elif step == "CAPTION":
      admin_data[ADMIN_ID]["caption"] = message.text.strip()
      admin_data[ADMIN_ID]["step"] = "SECRET"
      bot.send_message(
          ADMIN_ID, "✅ <b>Caption saved!</b>\n\n🔗 Now send the final secret link:\n<i>(Ab iska final secret link bhejein:)</i>", parse_mode="HTML"
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
            f"🎉 <b>Course created!</b>\n\n💰 Price: ₹{admin_data[ADMIN_ID]['amount']}\n👉 "
            f"<code>{link}</code>\n<i>(Course ban gaya hai!)</i>",
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
            f"✅ <b>Course saved! (Total: {len(admin_data[ADMIN_ID]['course_ids'])})</b>\n\n"
            "Do you want to add another course to this batch?\n"
            "<i>(Kya aap is batch mein ek aur course add karna chahte hain?)</i>",
            reply_markup=markup,
            parse_mode="HTML"
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
        user_id, 
        "⏳ <b>Your payment proof is received. It will be approved in 5 minutes...</b>\n"
        "<i>(Aapka payment proof mil gaya hai. 5 min mein approve ho jayega...)</i>", 
        parse_mode="HTML"
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
        f"🔔 <b>New Verification!</b>\n\n"
        f"👤 User: {first_name} {username}\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"📚 Course: <code>{course_id}</code>\n"
        f"💰 Amount: ₹{amt_text}\n"
        f"🔖 Order ID: <code>{order_id}</code>"
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
        admin_text += f"\n🔢 Submitted UTR: <code>{message.text.strip()}</code>"
        admin_msg = bot.send_message(
            DB_CHANNEL_ID,
            admin_text,
            reply_markup=markup,
            parse_mode="HTML",
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
      bot.send_message(ADMIN_ID, f"⚠️ Error: {e}")

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
          f"👤 <b>User:</b> {first_name} {username}\n"
          f"🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
          f"📅 <b>Date:</b> {datetime.now().strftime('%d-%m-%Y %I:%M %p')}\n"
          f"💰 <b>Amount:</b> ₹{clean_amt}\n"
          f"💳 <b>UPI ID (Tap to Copy):</b> <code>{UPI_ID}</code>\n"
      )
      if course.get("custom_caption"):
        invoice_text += f"\n📝 {course['custom_caption']}\n"

      invoice_text += (
          "\n👉 <b>Payment Instructions:</b>\n"
          "* Please send the <b>12-digit UTR No.</b> or <b>Payment Screenshot</b> here.\n"
          "<i>(Payment ke baad 12-digit UTR No. ya screenshot yahin bhejein.)</i>\n\n"
          "⏳ <i>The payment QR will expire in 10 minutes!</i>"
      )

      markup = InlineKeyboardMarkup()
      if CHAT_LINK:
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
        "📝 <b>Step 1/4: Promo Media</b>\nSend demo photo/video from gallery. Then press 'Next Step'.\n"
        "<i>(Gallery se demo photo/video bhejein. Phir 'Next Step' dabayein.)</i>",
        chat_id=chat_id,
        message_id=msg_id,
        reply_markup=markup,
        parse_mode="HTML"
    )

  elif data == "admin_create_batch":
    admin_data[ADMIN_ID] = {"mode": "batch", "step": "TITLE", "course_ids": []}
    bot.edit_message_text(
        "📦 <b>Create New Course Batch</b>\n\nPlease type and send the <b>Name/Title</b> for this batch:\n"
        "<i>(Kripya is batch ka naam/title type karke bhejein:)</i>",
        chat_id=chat_id,
        message_id=msg_id,
        parse_mode="HTML"
    )

  elif data == "next_price":
    if ADMIN_ID not in admin_data or not admin_data[ADMIN_ID].get("promo"):
      bot.answer_callback_query(
          call.id, "❌ Please send media first!", show_alert=True
      )
      return
    admin_data[ADMIN_ID]["step"] = "AMOUNT"
    bot.edit_message_text(
        "💰 <b>Step 2/4: Price</b>\n\nSend the price (₹) for this course (e.g., <code>299</code> or <code>499</code>):\n"
        "<i>(Is course ki price bhejein:)</i>",
        chat_id=chat_id,
        message_id=msg_id,
        parse_mode="HTML"
    )

  elif data == "skip_caption":
    if ADMIN_ID in admin_data:
      admin_data[ADMIN_ID]["caption"] = ""
      admin_data[ADMIN_ID]["step"] = "SECRET"
      bot.edit_message_text(
          "✅ <b>Caption Skipped!</b>\n\n🔗 <b>Step 4/4: Final Link</b>\nSend the final secret link.\n"
          "<i>(Final secret link bhejein.)</i>",
          chat_id=chat_id,
          message_id=msg_id,
          parse_mode="HTML"
      )

  elif data == "batch_add_next":
    admin_data[ADMIN_ID]["step"] = "PROMO"
    admin_data[ADMIN_ID]["promo"] = []
    admin_data[ADMIN_ID]["caption"] = ""
    markup = InlineKeyboardMarkup().row(
        InlineKeyboardButton("➡️ Next Step", callback_data="next_price")
    )
    bot.edit_message_text(
        "📝 <b>Send promo media for the next course</b>\nThen press 'Next Step'.\n"
        "<i>(Agle course ka promo media bhejein. Phir 'Next Step' dabayein.)</i>",
        chat_id=chat_id,
        message_id=msg_id,
        reply_markup=markup,
        parse_mode="HTML"
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
        f"🎉 <b>Course Batch Created!</b>\n\n📦 <b>Title:</b> {d['title']}\n📚 <b>Total"
        f" Courses:</b> {len(d['course_ids'])}\n\n👉 <code>{link}</code> 👈\n"
        "<i>(Course batch ban gaya hai!)</i>",
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
          "No one has bought a course yet.\n<i>(Abhi tak kisi ne course nahi kharida hai.)</i>",
          chat_id=chat_id,
          message_id=msg_id,
          parse_mode="HTML"
      )
    else:
      text = "👥 <b>Recent Purchases:</b>\n\n"
      for r in records:
        text += (
            f"👤 {r['username']} | 📅 {r['date'][:10]} | 📚 <code>{r['item_info']}</code>\n"
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
          f"✅ <b>[PAYMENT APPROVED & DELIVERED]</b>\n\n"
          f"👤 <b>User:</b> {user_name}\n"
          f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
          f"📚 <b>Course:</b> <code>{course_id}</code>\n"
          f"💰 <b>Rate:</b> ₹{course['amount']}\n"
          f"📅 <b>Date:</b> {date_now}"
      )

      if call.message.content_type == "photo":
        bot.edit_message_caption(
            receipt,
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="HTML",
        )
      else:
        bot.edit_message_text(
            receipt,
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="HTML",
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
      reason = "Your screenshot is invalid/fake. Chat now - @SaulGoodmanOp"
    elif reason_code == "notrecv":
      reason = "We haven't received your payment. Chat now - @SaulGoodmanOp"
    elif reason_code == "wrong":
      reason = "You have sent the wrong amount. Chat now - @SaulGoodmanOp"

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
            "🔄 Try Again (Generate QR)", callback_data=f"pay_upi_{course_id}"
        )
    )
    try:
      bot.send_message(
          user_id,
          f"❌ <b>Payment Denied!</b>\n\n<b>Reason:</b> {reason}\n\n"
          f"<i>(Payment reject kar diya gaya hai. Karan: {reason})</i>",
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
      conn.commit()

    receipt = (
        f"❌ <b>[PAYMENT REJECTED]</b>\n\n"
        f"👤 <b>User:</b> {user_name}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"📚 <b>Course:</b> <code>{course_id}</code>\n"
        f"💰 <b>Rate:</b> ₹{rate_amt}\n"
        f"📅 <b>Date:</b> {date_now}\n"
        f"⚠️ <b>Reason:</b> {reason}"
    )

    if call.message.content_type == "photo":
      bot.edit_message_caption(
          receipt,
          chat_id=chat_id,
          message_id=msg_id,
          parse_mode="HTML",
      )
    else:
      bot.edit_message_text(
          receipt,
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
    print("🚀 Bot is fully ready and started... (Bot puri tarah taiyar hokar start ho gaya hai...)")
    bot.infinity_polling(skip_pending=True)

  t = threading.Thread(target=run_bot, daemon=True)
  t.start()
  app.run(host="0.0.0.0", port=port)
