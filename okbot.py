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
    InputMediaDocument
)

# ==========================================
# 🛑 सेटिंग्स (लोकल और रेंडर दोनों के लिए) 🛑
# ==========================================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN", "8986044820:AAFgYI_F_MH0LQT5VX95_umWjkUaMx9cfug"
).strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8820964089").strip())
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003757631353").strip())
UPI_ID = os.environ.get("UPI_ID", "Q520245588@ybl").strip()
MERCHANT_NAME = os.environ.get("MERCHANT_NAME", "Study Wala").strip()

CHAT_LINK = os.environ.get("CHAT_LINK", "https://t.me/SaulGoodmanOp").strip()
INTERNATIONAL_LINK = os.environ.get(
    "INTERNATIONAL_LINK", "https://t.me/SaulGoodmanOp"
).strip()

bot = telebot.TeleBot(BOT_TOKEN)

# --- डेटाबेस और बैकअप सेटअप ---
DB_FILE = "shop_master_v7.db" 
BACKUP_FILE = "master_backup_v7.json"


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
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    cursor.execute("CREATE TABLE IF NOT EXISTS file_links (file_code TEXT PRIMARY KEY, media_data TEXT, button_data TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS menu_buttons (id INTEGER PRIMARY KEY AUTOINCREMENT, button_text TEXT, target_data TEXT)")
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

  qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
  qr.add_data(upi_url)
  qr.make(fit=True)
  qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
  w, h = qr_img.size

  box_w = int(w * 0.28)
  box_h = int(box_w * 0.40)
  box_x = (w - box_w) // 2
  box_y = (h - box_h) // 2
  draw = ImageDraw.Draw(qr_img)
  draw.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=6, fill="#ffffff", outline="#0b1329", width=2)

  lw = max(2, int(box_h * 0.12))
  let_w = box_w * 0.18
  let_h = box_h * 0.45
  gap = box_w * 0.08
  total_w = (let_w * 2) + gap * 2 + lw
  start_x = box_x + (box_w - total_w) // 2
  start_y = box_y + (box_h - let_h) // 2
  
  u_x = start_x
  draw.line([(u_x, start_y), (u_x, start_y + let_h)], fill="#097939", width=lw)
  draw.line([(u_x, start_y + let_h), (u_x + let_w, start_y + let_h)], fill="#097939", width=lw)
  draw.line([(u_x + let_w, start_y + let_h), (u_x + let_w, start_y)], fill="#097939", width=lw)
  p_x = u_x + let_w + gap
  draw.line([(p_x, start_y), (p_x, start_y + let_h)], fill="#F37021", width=lw)
  draw.line([(p_x, start_y), (p_x + let_w, start_y)], fill="#F37021", width=lw)
  draw.line([(p_x + let_w, start_y), (p_x + let_w, start_y + let_h // 2)], fill="#F37021", width=lw)
  draw.line([(p_x + let_w, start_y + let_h // 2), (p_x, start_y + let_h // 2)], fill="#F37021", width=lw)
  i_x = p_x + let_w + gap + lw // 2
  draw.line([(i_x, start_y), (i_x, start_y + let_h)], fill="#1a73e8", width=lw)

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
  if (chat_id in user_states and user_states[chat_id].get("course_id") == course_id):
    try:
      bot.delete_message(chat_id, message_id)
      bot.send_message(chat_id, "❌ <b>Your payment session (10 hours) has expired! Please try again.</b>", parse_mode="HTML")
      del user_states[chat_id]
    except: pass


def expire_verification(user_id, checking_msg_id, admin_msg_id, course_id):
  if (user_id in pending_verifications and pending_verifications[user_id].get("course_id") == course_id):
    try: bot.delete_message(user_id, checking_msg_id)
    except: pass
    try: bot.edit_message_caption("❌ <b>Auto-Expired (10 Hours)</b> - No Action Taken", chat_id=DB_CHANNEL_ID, message_id=admin_msg_id, reply_markup=None, parse_mode="HTML")
    except: pass
    markup = InlineKeyboardMarkup()
    if CHAT_LINK: markup.row(InlineKeyboardButton("💬 Contact Directly", url=CHAT_LINK))
    try: bot.send_message(user_id, "⏳ <b>Time's up!</b>\nNo approval received from admin in 10 hours. Please contact directly.", reply_markup=markup, parse_mode="HTML")
    except: pass
    del pending_verifications[user_id]


# ==========================================
# 🛑 मास्टर कोर्स डिलीवरी 🛑
# ==========================================
def send_course_to_user(chat_id, course):
  try: promo_items = json.loads(course["promo_media"])
  except: promo_items = []

  markup = InlineKeyboardMarkup()
  markup.row(InlineKeyboardButton(f"🇮🇳 UPI (Pay ₹{course['amount']})", callback_data=f"pay_upi_{course['course_id']}"))
  btn_row = []
  if INTERNATIONAL_LINK: btn_row.append(InlineKeyboardButton("🌍 International", url=INTERNATIONAL_LINK))
  if CHAT_LINK: btn_row.append(InlineKeyboardButton("💬 Chat with Me", url=CHAT_LINK))
  if btn_row: markup.row(*btn_row)

  media_items = [it for it in promo_items if it["type"] in ["photo", "video"]]
  first_photo_caption = ""
  for it in media_items:
      if it.get("caption"):
          first_photo_caption = it["caption"].strip()
          break
          
  custom_caption = course.get("custom_caption", "").strip()
  final_album_caption = ""
  if first_photo_caption and custom_caption: final_album_caption = f"{first_photo_caption}\n\n{custom_caption}"
  elif first_photo_caption: final_album_caption = first_photo_caption
  elif custom_caption: final_album_caption = custom_caption

  if len(final_album_caption) > 1000: final_album_caption = final_album_caption[:1000] + "..."

  if len(media_items) == 1:
    item = media_items[0]
    try:
      if item["type"] == "photo": bot.send_photo(chat_id, item["file_id"], caption=final_album_caption, reply_markup=markup, parse_mode="HTML")
      elif item["type"] == "video": bot.send_video(chat_id, item["file_id"], caption=final_album_caption, reply_markup=markup, parse_mode="HTML")
    except: pass
  elif len(media_items) > 1:
    media_group_html = []
    for i, item in enumerate(media_items):
      cap = final_album_caption if i == 0 else "" 
      if item["type"] == "photo": media_group_html.append(InputMediaPhoto(item["file_id"], caption=cap, parse_mode="HTML"))
      elif item["type"] == "video": media_group_html.append(InputMediaVideo(item["file_id"], caption=cap, parse_mode="HTML"))
    try: bot.send_media_group(chat_id, media_group_html)
    except: pass
    try: bot.send_message(chat_id, f"👆 <b>Choose an option to buy this pack (₹{course['amount']}):</b>\n", reply_markup=markup, parse_mode="HTML")
    except: pass

def send_batch_to_user(chat_id, batch):
    bot.send_message(chat_id, f"📦 <b>{batch['title']}</b>\nAll packs are listed below:\n<i>(Niche sabhi packs diye gaye hain:)</i>", parse_mode="HTML")
    course_ids = json.loads(batch["course_ids"])
    for cid in course_ids:
        c_data = get_course_data(cid)
        if c_data: send_course_to_user(chat_id, c_data)

# 🌟 DYNAMIC START MENU 🌟
def send_main_menu(chat_id):
    with get_db() as conn:
        buttons = conn.cursor().execute("SELECT * FROM menu_buttons").fetchall()
    
    markup = InlineKeyboardMarkup()
    for b in buttons:
        target = b['target_data']
        if target.startswith("http"): markup.row(InlineKeyboardButton(b['button_text'], url=target))
        else: markup.row(InlineKeyboardButton(b['button_text'], callback_data=f"mainmenu_{target}"))
    
    msg_text = (
        "👋 <b>Welcome to our Store!</b>\n\n"
        "Please select a course or pack from the menu below to get started:\n"
        "<i>(Niche diye gaye options mein se koi course chunein:)</i>"
    )
    bot.send_message(chat_id, msg_text, reply_markup=markup, parse_mode="HTML")

def send_admin_panel(chat_id):
  markup = InlineKeyboardMarkup()
  markup.row(InlineKeyboardButton("➕ Add Single Pack", callback_data="admin_add_course"))
  markup.row(InlineKeyboardButton("📦 Pack Batch (Multi-Pack)", callback_data="admin_create_batch"))
  markup.row(InlineKeyboardButton("🔗 Advanced File to Link", callback_data="admin_file_link"))
  markup.row(InlineKeyboardButton("📢 Advanced Broadcast", callback_data="admin_broadcast"))
  markup.row(InlineKeyboardButton("📋 Manage Main Menu", callback_data="admin_manage_menu"))
  markup.row(InlineKeyboardButton("👥 User Info", callback_data="admin_user_info"))
  bot.send_message(chat_id, "🛠 <b>Admin Panel</b>\nPlease select an option:\n", reply_markup=markup, parse_mode="HTML")

# ==========================================
# 1. स्टार्ट कमांड
# ==========================================
@bot.message_handler(commands=["start"])
def start_command(message):
  user_id = message.chat.id
  
  with get_db() as conn:
      conn.cursor().execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
      conn.commit()

  param = message.text.split()[1].strip() if len(message.text.split()) > 1 else ""

  if param.startswith("b_"):
    batch = get_batch_data(param)
    if batch: send_batch_to_user(user_id, batch)
    else: bot.send_message(user_id, "❌ <b>This pack link has expired.</b>", parse_mode="HTML")

  elif param.startswith("c_"):
    course = get_course_data(param)
    if course: send_course_to_user(user_id, course)
    else: bot.send_message(user_id, "❌ <b>This link is not available.</b>", parse_mode="HTML")
  
  elif param.startswith("f_"):
      with get_db() as conn:
          file_data = conn.cursor().execute("SELECT * FROM file_links WHERE file_code=?", (param,)).fetchone()
      if file_data:
          media_items = json.loads(file_data['media_data'])
          buttons = json.loads(file_data['button_data'])
          
          markup = InlineKeyboardMarkup()
          for b in buttons: markup.row(InlineKeyboardButton(b['text'], url=b['url']))
          
          if len(media_items) == 1:
              item = media_items[0]
              try:
                  if item['type'] == 'text': bot.send_message(user_id, item['caption'], reply_markup=markup, parse_mode="HTML")
                  elif item['type'] == 'photo': bot.send_photo(user_id, item['file_id'], caption=item['caption'], reply_markup=markup, parse_mode="HTML")
                  elif item['type'] == 'video': bot.send_video(user_id, item['file_id'], caption=item['caption'], reply_markup=markup, parse_mode="HTML")
                  elif item['type'] == 'document': bot.send_document(user_id, item['file_id'], caption=item['caption'], reply_markup=markup, parse_mode="HTML")
              except Exception as e:
                  bot.send_message(user_id, f"❌ Error: {e}")
          
          elif len(media_items) > 1:
              media_group = []
              for item in media_items:
                  if item['type'] == 'photo': media_group.append(InputMediaPhoto(item['file_id'], caption=item['caption'], parse_mode="HTML"))
                  elif item['type'] == 'video': media_group.append(InputMediaVideo(item['file_id'], caption=item['caption'], parse_mode="HTML"))
                  elif item['type'] == 'document': media_group.append(InputMediaDocument(item['file_id'], caption=item['caption'], parse_mode="HTML"))
              try:
                  if media_group: bot.send_media_group(user_id, media_group)
                  if buttons or any(i['type'] == 'text' for i in media_items): 
                      bot.send_message(user_id, "👇 <b>Check the link(s) below:</b>", reply_markup=markup, parse_mode="HTML")
              except Exception as e:
                  bot.send_message(user_id, f"❌ Error sending album: {e}")
      else:
          bot.send_message(user_id, "❌ <b>File not found or expired.</b>", parse_mode="HTML")
  
  else:
    if user_id == ADMIN_ID:
      send_admin_panel(user_id) 
    else:
      send_main_menu(user_id) 


# ==========================================
# 2. एडमिन और यूज़र मैसेज हैंडलर
# ==========================================
@bot.message_handler(content_types=["photo", "video", "document", "text"])
def handle_all_messages(message):
  user_id = message.chat.id

  # --- ADMIN FLOWS ---
  if user_id == ADMIN_ID and user_id in admin_data:
    step = admin_data[ADMIN_ID].get("step")

    # 🌟 1. ADVANCED BROADCAST MEDIA 🌟
    if step == "BC_MEDIA":
      media_type = "text"
      file_id = None
      caption = message.caption or message.text or ""
      
      if message.photo: media_type, file_id = "photo", message.photo[-1].file_id
      elif message.video: media_type, file_id = "video", message.video.file_id
      elif message.document: media_type, file_id = "document", message.document.file_id
      
      admin_data[ADMIN_ID].setdefault("media", []).append({"type": media_type, "file_id": file_id, "caption": caption})
      
      markup = InlineKeyboardMarkup().row(InlineKeyboardButton("✅ Done Adding Media/Text", callback_data="bc_done"))
      bot.send_message(ADMIN_ID, "✅ <b>Saved!</b>\nSend another Photo/Video/Text, OR click 'Done' if finished.", reply_markup=markup, parse_mode="HTML")
      return

    # 🌟 2. ADVANCED BROADCAST BUTTONS (STEP-BY-STEP) 🌟
    elif step == "BC_BUTTONS":
      btn_text = message.text.strip()
      if ' - ' in btn_text:
          try:
              text, url = btn_text.split(' - ', 1)
              admin_data[ADMIN_ID].setdefault("buttons", []).append({"text": text.strip(), "url": url.strip()})
              count = len(admin_data[ADMIN_ID]["buttons"])
              
              markup = InlineKeyboardMarkup().row(InlineKeyboardButton("🚀 Finish & Broadcast", callback_data="bc_finish"))
              bot.send_message(
                  ADMIN_ID, 
                  f"✅ <b>Button Added! (Total: {count})</b>\n\nWant to add another button? Send it in <code>Name - Link</code> format.\n\n<i>(OR click Finish to start broadcast)</i>", 
                  reply_markup=markup, 
                  parse_mode="HTML"
              )
          except Exception as e:
              bot.send_message(ADMIN_ID, "❌ Format Error. Use EXACTLY like this: <code>My Website - https://google.com</code> (Spaces around the hyphen are important!)", parse_mode="HTML")
      else:
          bot.send_message(ADMIN_ID, "❌ Format Error. Use EXACTLY like this: <code>My Website - https://google.com</code>", parse_mode="HTML")
      return

    # 🌟 3. ADVANCED FILE-TO-LINK MEDIA 🌟
    elif step == "FTL_MEDIA":
      media_type = "text"
      file_id = None
      caption = message.caption or message.text or ""
      
      if message.photo: media_type, file_id = "photo", message.photo[-1].file_id
      elif message.video: media_type, file_id = "video", message.video.file_id
      elif message.document: media_type, file_id = "document", message.document.file_id
      
      admin_data[ADMIN_ID].setdefault("media", []).append({"type": media_type, "file_id": file_id, "caption": caption})
      
      markup = InlineKeyboardMarkup().row(InlineKeyboardButton("✅ Done Adding Media/Text", callback_data="ftl_done"))
      bot.send_message(ADMIN_ID, "✅ <b>Saved!</b>\nSend another Photo/Video/Text, OR click 'Done' if finished.", reply_markup=markup, parse_mode="HTML")
      return
      
    # 🌟 4. ADVANCED FILE-TO-LINK BUTTONS (STEP-BY-STEP) 🌟
    elif step == "FTL_BUTTONS":
      btn_text = message.text.strip()
      if ' - ' in btn_text:
          try:
              text, url = btn_text.split(' - ', 1)
              admin_data[ADMIN_ID].setdefault("buttons", []).append({"text": text.strip(), "url": url.strip()})
              count = len(admin_data[ADMIN_ID]["buttons"])
              
              markup = InlineKeyboardMarkup().row(InlineKeyboardButton("🚀 Finish & Create Link", callback_data="ftl_finish"))
              bot.send_message(
                  ADMIN_ID, 
                  f"✅ <b>Button Added! (Total: {count})</b>\n\nWant to add another button? Send it in <code>Name - Link</code> format.\n\n<i>(OR click Finish to generate link)</i>", 
                  reply_markup=markup, 
                  parse_mode="HTML"
              )
          except:
              bot.send_message(ADMIN_ID, "❌ Format Error. Use EXACTLY like this: <code>My Website - https://google.com</code> (Spaces around the hyphen are important!)", parse_mode="HTML")
      else:
          bot.send_message(ADMIN_ID, "❌ Format Error. Use EXACTLY like this: <code>My Website - https://google.com</code>", parse_mode="HTML")
      return

    # --- Course Creation Flow ---
    elif step == "TITLE":
      admin_data[ADMIN_ID]["title"] = message.text.strip()
      admin_data[ADMIN_ID]["step"] = "PROMO"
      admin_data[ADMIN_ID]["promo"] = []
      bot.send_message(ADMIN_ID, f"✅ Batch title saved: <b>{admin_data[ADMIN_ID]['title']}</b>\n\n📝 <b>Send the promo media (photo/video).</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("➡️ Next Step", callback_data="next_price")))
      return

    elif step == "PROMO":
      media_type, file_id = "text", None
      if message.photo: media_type, file_id = "photo", message.photo[-1].file_id
      elif message.video: media_type, file_id = "video", message.video.file_id
      admin_data[ADMIN_ID]["promo"].append({"type": media_type, "file_id": file_id, "caption": message.caption or message.text or ""})
      return

    elif step == "AMOUNT":
      clean_amt = re.sub(r"[^\d.]", "", message.text.strip())
      if not clean_amt:
        bot.send_message(ADMIN_ID, "❌ <b>Please enter the price in numbers only.</b>", parse_mode="HTML")
        return
      admin_data[ADMIN_ID]["amount"] = clean_amt
      admin_data[ADMIN_ID]["step"] = "CAPTION"
      markup = InlineKeyboardMarkup().row(InlineKeyboardButton("⏭ Skip (No Caption)", callback_data="skip_caption"))
      bot.send_message(ADMIN_ID, f"✅ <b>Price ₹{clean_amt} saved!</b>\n📝 Type any extra caption.", reply_markup=markup, parse_mode="HTML")
      return

    elif step == "CAPTION":
      admin_data[ADMIN_ID]["caption"] = message.text.strip()
      admin_data[ADMIN_ID]["step"] = "SECRET"
      bot.send_message(ADMIN_ID, "✅ <b>Caption saved!</b>\n🔗 Now send the final secret link:", parse_mode="HTML")
      return

    elif step == "SECRET":
      secret = message.text.strip()
      course_id = "c_" + str(uuid.uuid4())[:6]
      promo_json = json.dumps(admin_data[ADMIN_ID]["promo"])

      with get_db() as conn:
        conn.cursor().execute("INSERT OR REPLACE INTO courses VALUES (?, ?, ?, ?, ?)", (course_id, promo_json, admin_data[ADMIN_ID]["amount"], admin_data[ADMIN_ID]["caption"], secret))
        conn.commit()

      bk = load_backup()
      bk["courses"][course_id] = {"promo_media": promo_json, "amount": admin_data[ADMIN_ID]["amount"], "custom_caption": admin_data[ADMIN_ID]["caption"], "secret_text": secret}
      save_backup(bk)

      mode = admin_data[ADMIN_ID].get("mode")
      if mode == "single":
        link = f"https://t.me/{bot.get_me().username}?start={course_id}"
        bot.send_message(ADMIN_ID, f"🎉 <b>Pack created!</b>\n💰 Price: ₹{admin_data[ADMIN_ID]['amount']}\n👉 <code>{link}</code>", parse_mode="HTML")
        del admin_data[ADMIN_ID]
        send_admin_panel(ADMIN_ID)

      elif mode == "batch":
        admin_data[ADMIN_ID]["course_ids"].append(course_id)
        admin_data[ADMIN_ID]["step"] = "NEXT_ACTION"
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("➕ Add Another Pack", callback_data="batch_add_next"))
        markup.row(InlineKeyboardButton("✅ Finish Batch", callback_data="batch_finish"))
        bot.send_message(ADMIN_ID, f"✅ <b>Pack saved! (Total: {len(admin_data[ADMIN_ID]['course_ids'])})</b>", reply_markup=markup, parse_mode="HTML")
      return

    # --- Menu Management Flow ---
    elif step == "MENU_TARGET":
        admin_data[ADMIN_ID]["menu_target"] = message.text.strip()
        admin_data[ADMIN_ID]["step"] = "MENU_TEXT"
        bot.send_message(ADMIN_ID, "📝 <b>Send Button Text:</b>\nWhat text should appear on the button?", parse_mode="HTML")
        return

    elif step == "MENU_TEXT":
        btn_text = message.text.strip()
        target = admin_data[ADMIN_ID]["menu_target"]
        with get_db() as conn:
            conn.cursor().execute("INSERT INTO menu_buttons (button_text, target_data) VALUES (?, ?)", (btn_text, target))
            conn.commit()
        bot.send_message(ADMIN_ID, f"✅ <b>Button Added!</b>\n\nText: {btn_text}\nLink: {target}", parse_mode="HTML")
        del admin_data[ADMIN_ID]
        send_admin_panel(ADMIN_ID)
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
      except: pass

    first_name = message.from_user.first_name or "User"
    username = f"(@{message.from_user.username})" if message.from_user.username else ""
    course = get_course_data(course_id)
    amt_text = course["amount"] if course else ""

    check_msg = bot.send_message(user_id, "⏳ <b>Your payment proof is received. It will be approved within 10 minutes...</b>", parse_mode="HTML")

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Approve", callback_data=f"app_{user_id}_{course_id}"),
        InlineKeyboardButton("❌ Deny", callback_data=f"den_{user_id}_{course_id}"),
    )

    admin_text = (
        f"🔔 <b>New Verification!</b>\n\n"
        f"👤 User: {first_name} {username}\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"📚 Pack: <code>{course_id}</code>\n"
        f"💰 Amount: ₹{amt_text}\n"
        f"🔖 Order ID: <code>{order_id}</code>"
    )

    try:
      if message.photo: admin_msg = bot.send_photo(DB_CHANNEL_ID, photo=message.photo[-1].file_id, caption=admin_text, reply_markup=markup, parse_mode="HTML")
      else:
        admin_text += f"\n🔢 Submitted UTR: <code>{message.text.strip()}</code>"
        admin_msg = bot.send_message(DB_CHANNEL_ID, admin_text, reply_markup=markup, parse_mode="HTML")

      pending_verifications[user_id] = {
          "checking_msg_id": check_msg.message_id,
          "admin_msg_id": admin_msg.message_id,
          "course_id": course_id,
      }
      threading.Timer(36000, expire_verification, args=(user_id, check_msg.message_id, admin_msg.message_id, course_id)).start()
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

  # 🌟 BROADCAST MEDIA DONE BUTTON 🌟
  if data == "bc_done":
      admin_data[ADMIN_ID]["step"] = "BC_BUTTONS"
      admin_data[ADMIN_ID]["buttons"] = []
      markup = InlineKeyboardMarkup().row(InlineKeyboardButton("🚀 Finish & Broadcast (No Buttons)", callback_data="bc_finish"))
      bot.send_message(
          ADMIN_ID, 
          "✅ <b>Media/Text Saved!</b>\n\nDo you want to add buttons below the message?\nSend your FIRST button like this:\n"
          "<code>My Website - https://google.com</code>\n\n"
          "<i>(Or click Finish to broadcast immediately without buttons)</i>", 
          reply_markup=markup,
          parse_mode="HTML"
      )
      return
      
  # 🌟 BROADCAST FINISH (EXECUTE) 🌟
  elif data == "bc_finish":
      media_items = admin_data[ADMIN_ID].get("media", [])
      buttons = admin_data[ADMIN_ID].get("buttons", [])
      
      markup = InlineKeyboardMarkup()
      for b in buttons: markup.row(InlineKeyboardButton(b['text'], url=b['url']))

      bot.send_message(ADMIN_ID, "⏳ Broadcasting started... Please wait.")
      
      with get_db() as conn:
          users = conn.cursor().execute("SELECT user_id FROM users").fetchall()
          
      success_count = 0
      for u in users:
          uid = u['user_id']
          try:
              if not media_items: continue
              
              if len(media_items) == 1:
                  item = media_items[0]
                  if item['type'] == 'text': bot.send_message(uid, item['caption'], reply_markup=markup, parse_mode="HTML")
                  elif item['type'] == 'photo': bot.send_photo(uid, item['file_id'], caption=item['caption'], reply_markup=markup, parse_mode="HTML")
                  elif item['type'] == 'video': bot.send_video(uid, item['file_id'], caption=item['caption'], reply_markup=markup, parse_mode="HTML")
                  elif item['type'] == 'document': bot.send_document(uid, item['file_id'], caption=item['caption'], reply_markup=markup, parse_mode="HTML")
              
              elif len(media_items) > 1:
                  media_group = []
                  for item in media_items:
                      if item['type'] == 'photo': media_group.append(InputMediaPhoto(item['file_id'], caption=item['caption'], parse_mode="HTML"))
                      elif item['type'] == 'video': media_group.append(InputMediaVideo(item['file_id'], caption=item['caption'], parse_mode="HTML"))
                      elif item['type'] == 'document': media_group.append(InputMediaDocument(item['file_id'], caption=item['caption'], parse_mode="HTML"))
                  
                  if media_group: bot.send_media_group(uid, media_group)
                  if buttons or any(i['type'] == 'text' for i in media_items): 
                      bot.send_message(uid, "👇 <b>Check the link(s) below:</b>", reply_markup=markup, parse_mode="HTML")
              success_count += 1
          except Exception as e:
              pass
              
      bot.send_message(ADMIN_ID, f"✅ <b>Broadcast Complete!</b>\nMessage successfully sent to {success_count} users.", parse_mode="HTML")
      del admin_data[ADMIN_ID]
      send_admin_panel(ADMIN_ID)
      return
  
  # 🌟 FTL MEDIA DONE BUTTON 🌟
  if data == "ftl_done":
      admin_data[ADMIN_ID]["step"] = "FTL_BUTTONS"
      admin_data[ADMIN_ID]["buttons"] = []
      markup = InlineKeyboardMarkup().row(InlineKeyboardButton("🚀 Finish & Create Link (No Buttons)", callback_data="ftl_finish"))
      bot.send_message(
          ADMIN_ID, 
          "✅ <b>Media/Text Saved!</b>\n\nDo you want to add buttons below the message?\nSend your FIRST button like this:\n"
          "<code>My Website - https://google.com</code>\n\n"
          "<i>(Or click Finish to create link immediately without buttons)</i>", 
          reply_markup=markup,
          parse_mode="HTML"
      )
      return
      
  # 🌟 FTL FINISH (EXECUTE) 🌟
  elif data == "ftl_finish":
      file_code = "f_" + str(uuid.uuid4())[:6]
      media_json = json.dumps(admin_data[ADMIN_ID].get("media", []))
      btn_json = json.dumps(admin_data[ADMIN_ID].get("buttons", []))
      
      with get_db() as conn:
          conn.cursor().execute("INSERT INTO file_links VALUES (?, ?, ?)", (file_code, media_json, btn_json))
          conn.commit()
          
      link = f"https://t.me/{bot.get_me().username}?start={file_code}"
      bot.send_message(ADMIN_ID, f"🎉 <b>File/Album Link Created Successfully!</b>\n\n🔗 Share this link:\n<code>{link}</code>", parse_mode="HTML")
      del admin_data[ADMIN_ID]
      send_admin_panel(ADMIN_ID)
      return

  # 🌟 MAIN MENU CLICKS 🌟
  if data.startswith("mainmenu_"):
      target = data.replace("mainmenu_", "")
      bot.answer_callback_query(call.id)
      if target.startswith("c_"):
          course = get_course_data(target)
          if course: send_course_to_user(chat_id, course)
      elif target.startswith("b_"):
          batch = get_batch_data(target)
          if batch: send_batch_to_user(chat_id, batch)
      return

  # --- USER: UPI QR VIEW ---
  if data.startswith("pay_upi_"):
    bot.answer_callback_query(call.id, "⏳ Generating Payment QR...", show_alert=False)
    course_id = data.replace("pay_upi_", "")
    course = get_course_data(course_id)
    if course:
      order_id = str(uuid.uuid4())[:8]
      user_states[chat_id] = {"course_id": course_id, "order_id": order_id}

      qr_img_bio, clean_amt = generate_upi_qr(course["amount"], order_id)
      first_name = call.from_user.first_name or "User"
      username = f"(@{call.from_user.username})" if call.from_user.username else ""

      invoice_text = (
          f"👤 <b>User:</b> {first_name} {username}\n"
          f"🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
          f"📅 <b>Date:</b> {datetime.now().strftime('%d-%m-%Y %I:%M %p')}\n"
          f"💰 <b>Amount:</b> ₹{clean_amt}\n"
          f"💳 <b>UPI ID:</b> <code>{UPI_ID}</code>\n"
      )
      if course.get("custom_caption"): invoice_text += f"\n📝 {course['custom_caption']}\n"
      invoice_text += "\n👉 <b>Payment Instructions:</b>\n* Please send the <b>Payment Screenshot</b> here.\n⏳ <i>The payment QR will expire in 10 minutes...!</i>"

      markup = InlineKeyboardMarkup()
      if CHAT_LINK: markup.row(InlineKeyboardButton("💬 Chat with Admin", url=CHAT_LINK))

      sent_msg = bot.send_photo(chat_id, photo=qr_img_bio, caption=invoice_text, reply_markup=markup, parse_mode="HTML")
      user_qr_messages[chat_id] = sent_msg.message_id
      threading.Timer(36000, expire_qr, args=(chat_id, sent_msg.message_id, course_id)).start()
    return

  bot.answer_callback_query(call.id)

  # --- ADMIN ACTIONS ---
  if data == "admin_add_course":
    admin_data[ADMIN_ID] = {"mode": "single", "step": "PROMO", "promo": [], "amount": None, "caption": ""}
    markup = InlineKeyboardMarkup().row(InlineKeyboardButton("➡️ Next Step", callback_data="next_price"))
    bot.edit_message_text("📝 <b>Step 1/4: Promo Media</b>\nSend demo photo/video.", chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="HTML")

  elif data == "admin_create_batch":
    admin_data[ADMIN_ID] = {"mode": "batch", "step": "TITLE", "course_ids": []}
    bot.edit_message_text("📦 <b>Create New Pack Batch</b>\nPlease send the Title:", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    
  elif data == "admin_file_link":
      admin_data[ADMIN_ID] = {"step": "FTL_MEDIA", "media": []}
      bot.edit_message_text("📎 <b>Advanced File to Link</b>\nSend your Photos, Videos, Documents, or Texts (with captions). You can send multiple for an Album!\n<i>(Apni file/photo/text yahan bhejein:)</i>", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")

  elif data == "admin_broadcast":
      admin_data[ADMIN_ID] = {"step": "BC_MEDIA", "media": []}
      bot.edit_message_text("📢 <b>Advanced Broadcast</b>\nSend the Text, Photo, Video, or Document that you want to broadcast.\n<i>(Apna broadcast message yahan bhejein:)</i>", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
      
  elif data == "admin_manage_menu":
      markup = InlineKeyboardMarkup()
      markup.row(InlineKeyboardButton("➕ Add Menu Button", callback_data="admin_menu_add"))
      markup.row(InlineKeyboardButton("🗑 Delete Menu Button", callback_data="admin_menu_del"))
      markup.row(InlineKeyboardButton("🔙 Back", callback_data="back_to_admin"))
      bot.edit_message_text("📋 <b>Manage Main Menu</b>", chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="HTML")

  elif data == "admin_menu_add":
      admin_data[ADMIN_ID] = {"step": "MENU_TARGET"}
      bot.edit_message_text("🔗 <b>Add Menu Button</b>\nSend the Course ID (c_...), Batch ID (b_...), or Website URL (http...):", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
      
  elif data == "admin_menu_del":
      with get_db() as conn:
          buttons = conn.cursor().execute("SELECT * FROM menu_buttons").fetchall()
      if not buttons:
          bot.edit_message_text("❌ No buttons currently in menu.", chat_id=chat_id, message_id=msg_id, reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("🔙 Back", callback_data="admin_manage_menu")))
          return
      markup = InlineKeyboardMarkup()
      for b in buttons: markup.add(InlineKeyboardButton(f"❌ {b['button_text']}", callback_data=f"delmenu_{b['id']}"))
      markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_manage_menu"))
      bot.edit_message_text("🗑 <b>Click a button to delete it:</b>", chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="HTML")

  elif data.startswith("delmenu_"):
      btn_id = data.replace("delmenu_", "")
      with get_db() as conn:
          conn.cursor().execute("DELETE FROM menu_buttons WHERE id=?", (btn_id,))
          conn.commit()
      bot.edit_message_text("✅ <b>Button Deleted!</b>", chat_id=chat_id, message_id=msg_id, reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("🔙 Back to Admin", callback_data="back_to_admin")), parse_mode="HTML")

  elif data == "next_price":
    if ADMIN_ID not in admin_data or not admin_data[ADMIN_ID].get("promo"): return
    admin_data[ADMIN_ID]["step"] = "AMOUNT"
    bot.edit_message_text("💰 <b>Step 2/4: Price</b>\nSend the price.", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")

  elif data == "skip_caption":
    if ADMIN_ID in admin_data:
      admin_data[ADMIN_ID]["caption"] = ""
      admin_data[ADMIN_ID]["step"] = "SECRET"
      bot.edit_message_text("✅ <b>Caption Skipped!</b>\n🔗 <b>Step 4/4: Final Link</b>\nSend the final secret link.", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")

  elif data == "batch_add_next":
    admin_data[ADMIN_ID]["step"] = "PROMO"
    admin_data[ADMIN_ID]["promo"] = []
    admin_data[ADMIN_ID]["caption"] = ""
    markup = InlineKeyboardMarkup().row(InlineKeyboardButton("➡️ Next Step", callback_data="next_price"))
    bot.edit_message_text("📝 <b>Send promo media for the next pack</b>", chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="HTML")

  elif data == "batch_finish":
    d = admin_data.get(ADMIN_ID)
    if not d or not d.get("course_ids"): return
    batch_id = "b_" + str(uuid.uuid4())[:6]
    c_ids_json = json.dumps(d["course_ids"])
    with get_db() as conn:
      conn.cursor().execute("INSERT OR REPLACE INTO batches VALUES (?, ?, ?)", (batch_id, d["title"], c_ids_json))
      conn.commit()
    bk = load_backup()
    bk["batches"][batch_id] = {"batch_id": batch_id, "title": d["title"], "course_ids": c_ids_json}
    save_backup(bk)
    link = f"https://t.me/{bot.get_me().username}?start={batch_id}"
    bot.edit_message_text(f"🎉 <b>Pack Batch Created!</b>\n👉 <code>{link}</code>", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    del admin_data[ADMIN_ID]
    send_admin_panel(ADMIN_ID)

  elif data == "admin_user_info":
    with get_db() as conn:
      records = conn.cursor().execute("SELECT username, date, item_info FROM purchases ORDER BY id DESC LIMIT 15").fetchall()
    if not records:
      bot.edit_message_text("No one has bought a pack yet.", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    else:
      text = "👥 <b>Recent Purchases:</b>\n\n"
      for r in records: text += f"👤 {r['username']} | 📅 {r['date'][:10]} | 📚 <code>{r['item_info']}</code>\n"
      markup = InlineKeyboardMarkup().row(InlineKeyboardButton("🔙 Back", callback_data="back_to_admin"))
      bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=markup, parse_mode="HTML")

  elif data == "back_to_admin":
    try: bot.delete_message(chat_id, msg_id)
    except: pass
    send_admin_panel(chat_id)

  # --- ADMIN: APPROVE ---
  elif data.startswith("app_"):
    parts = data.split("_", 2)
    user_id, course_id = int(parts[1]), parts[2]

    if user_id in pending_verifications:
      try: bot.delete_message(user_id, pending_verifications[user_id]["checking_msg_id"])
      except: pass
      del pending_verifications[user_id]

    course = get_course_data(course_id)
    if course:
      try: bot.send_message(user_id, f"🎉 <b>Payment Approved!</b>\n\n{course['secret_text']}", parse_mode="HTML")
      except: pass

      date_now = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
      
      try:
        user_info = bot.get_chat(user_id)
        if user_info.username: user_mention = f"@{user_info.username}"
        else:
            first_name = user_info.first_name or "User"
            user_mention = f"<a href='tg://user?id={user_id}'>{first_name}</a>"
      except: user_mention = f"<a href='tg://user?id={user_id}'>User</a>"

      with get_db() as conn:
        conn.cursor().execute("INSERT INTO purchases (user_id, username, item_info, date) VALUES (?, ?, ?, ?)", (user_id, user_mention, f"{course_id} | Rate: ₹{course['amount']} | APPROVED", date_now))
        conn.commit()

      receipt = (
          f"✅ <b>[PAYMENT APPROVED & DELIVERED]</b>\n\n"
          f"👤 <b>User:</b> {user_mention}\n"
          f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
          f"📚 <b>Pack:</b> <code>{course_id}</code>\n"
          f"💰 <b>Rate:</b> ₹{course['amount']}\n"
          f"📅 <b>Date:</b> {date_now}"
      )
      
      if call.message.content_type == "photo": bot.edit_message_caption(receipt, chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
      else: bot.edit_message_text(receipt, chat_id=chat_id, message_id=msg_id, parse_mode="HTML")

  # --- ADMIN: DENY ---
  elif data.startswith("den_"):
    parts = data.split("_", 2)
    user_id, course_id = parts[1], parts[2]
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("1️⃣ Fake Screenshot", callback_data=f"rsn_fake_{user_id}_{course_id}"))
    markup.row(InlineKeyboardButton("2️⃣ Payment Not Received", callback_data=f"rsn_notrecv_{user_id}_{course_id}"))
    markup.row(InlineKeyboardButton("3️⃣ Wrong Amount", callback_data=f"rsn_wrong_{user_id}_{course_id}"))
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=markup)

  # --- ADMIN: REASON SELECTED ---
  elif data.startswith("rsn_"):
    parts = data.split("_")
    reason_code, user_id, course_id = parts[1], int(parts[2]), parts[3]
    if reason_code == "fake": reason = "Your screenshot is invalid/fake. Chat now."
    elif reason_code == "notrecv": reason = "We haven't received your payment. Chat now."
    elif reason_code == "wrong": reason = "You have sent the wrong amount. Chat now."

    if user_id in pending_verifications:
      try: bot.delete_message(user_id, pending_verifications[user_id]["checking_msg_id"])
      except: pass
      del pending_verifications[user_id]

    course = get_course_data(course_id)
    rate_amt = course["amount"] if course else "-"

    retry_markup = InlineKeyboardMarkup().row(InlineKeyboardButton("🔄 Try Again", callback_data=f"pay_upi_{course_id}"))
    try: bot.send_message(user_id, f"❌ <b>Payment Denied!</b>\n\n<b>Reason:</b> {reason}", reply_markup=retry_markup, parse_mode="HTML")
    except: pass

    date_now = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")
    
    try:
      user_info = bot.get_chat(user_id)
      if user_info.username: user_mention = f"@{user_info.username}"
      else:
          first_name = user_info.first_name or "User"
          user_mention = f"<a href='tg://user?id={user_id}'>{first_name}</a>"
    except: user_mention = f"<a href='tg://user?id={user_id}'>User</a>"

    with get_db() as conn:
      conn.cursor().execute("INSERT INTO purchases (user_id, username, item_info, date) VALUES (?, ?, ?, ?)", (user_id, user_mention, f"{course_id} | Rate: ₹{rate_amt} | REJECTED: {reason}", date_now))
      conn.commit()

    receipt = (
        f"❌ <b>[PAYMENT REJECTED]</b>\n\n"
        f"👤 <b>User:</b> {user_mention}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"📚 <b>Pack:</b> <code>{course_id}</code>\n"
        f"💰 <b>Rate:</b> ₹{rate_amt}\n"
        f"📅 <b>Date:</b> {date_now}\n"
        f"⚠️ <b>Reason:</b> {reason}"
    )

    if call.message.content_type == "photo": bot.edit_message_caption(receipt, chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    else: bot.edit_message_text(receipt, chat_id=chat_id, message_id=msg_id, parse_mode="HTML")


# ==========================================
# 4. Flask Web Server (Render 24/7 Hosting)
# ==========================================
app = Flask(__name__)

@app.route("/")
def home(): return "Telegram Advanced Pack Bot is Running Smoothly 24/7!"

if __name__ == "__main__":
  port = int(os.environ.get("PORT", 10000))
  def run_bot(): bot.infinity_polling(skip_pending=True)
  t = threading.Thread(target=run_bot, daemon=True)
  t.start()
  app.run(host="0.0.0.0", port=port)
