import io
import json
import os
import random
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta

from flask import Flask, request
from PIL import Image, ImageDraw
import pymongo
import qrcode
import telebot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)

# ==========================================
# 🛑 ENVIRONMENT VARIABLES (Render से लेगा)
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "telegram_store_bot")

UPI_ID = os.environ.get("UPI_ID")
MERCHANT_NAME = os.environ.get("MERCHANT_NAME", "Store")
SMS_HOOK_SECRET = os.environ.get("SMS_HOOK_SECRET")

CHAT_LINK = os.environ.get("CHAT_LINK")
INTERNATIONAL_LINK = os.environ.get("INTERNATIONAL_LINK")

# 🔒 Content Protection Toggle (Render से True/False कंट्रोल करें)
PROTECT_CONTENT = os.environ.get("PROTECT_CONTENT", "False").strip().lower() == "true"

QR_EXPIRY_SECONDS = 600              # 10 मिनट
INACTIVITY_CLEANUP_SECONDS = 86400   # 24 घंटे

# ज़रूरी वेरिएबल्स चेक करें
try:
    ADMIN_ID = int(os.environ.get("ADMIN_ID"))
    DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID"))
except (TypeError, ValueError):
    print("❌ ERROR: 'ADMIN_ID' या 'DB_CHANNEL_ID' Environment Variable सही से सेट नहीं है।")
    sys.exit(1)

if not BOT_TOKEN or not MONGO_URI or not UPI_ID or not SMS_HOOK_SECRET:
    print("❌ ERROR: कोई महत्वपूर्ण Environment Variable (BOT_TOKEN, MONGO_URI, UPI_ID, SMS_HOOK_SECRET) मिसिंग है।")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# 🇮🇳 IST Timezone
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_time():
    return datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p")


# ==========================================
# 🍃 MONGODB SETUP
# ==========================================
try:
    mongo_client = pymongo.MongoClient(MONGO_URI)
    db = mongo_client.get_database(MONGO_DB_NAME)
    users_col = db["users"]
    courses_col = db["courses"]
    batches_col = db["batches"]
    purchases_col = db["purchases"]
    file_links_col = db["file_links"]
    settings_col = db["settings"]
    orders_col = db["orders"]          # लाइव ऑर्डर और 5 घंटे की मेमोरी
    sms_pool_col = db["sms_pool"]      # SMS बफर पूल
    offers_col = db["offers"]          # डिस्काउंट ऑफर्स

    # ऑटो-डिलीट (TTL): SMS 5 घंटे में और ऑर्डर्स 48 घंटे में डिलीट होंगे
    try:
        sms_pool_col.create_index("created_at_dt", expireAfterSeconds=18000)
        orders_col.create_index("created_at_dt", expireAfterSeconds=172800)
    except Exception:
        pass
    print(f"✅ MongoDB Connected! (Database: {MONGO_DB_NAME})")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")
    sys.exit(1)


# ==========================================
# 📝 TEXT FORMATTING & ACTIVITY TRACKER
# ==========================================
def get_formatted_text(message):
    if hasattr(message, "html_text") and message.html_text:
        return message.html_text
    if hasattr(message, "html_caption") and message.html_caption:
        return message.html_caption
    return message.caption or message.text or ""

user_chat_messages = {}
user_inactivity_timers = {}
tracker_lock = threading.Lock()

def clear_inactive_chat(chat_id):
    with tracker_lock:
        msg_ids = user_chat_messages.pop(chat_id, [])
        user_inactivity_timers.pop(chat_id, None)
    for mid in msg_ids:
        try: bot.delete_message(chat_id, mid)
        except Exception: pass

def register_activity(chat_id, message_id=None):
    if not isinstance(chat_id, int) or chat_id <= 0 or chat_id == ADMIN_ID: return
    with tracker_lock:
        if chat_id not in user_chat_messages: user_chat_messages[chat_id] = []
        if message_id and message_id not in user_chat_messages[chat_id]: user_chat_messages[chat_id].append(message_id)
        if chat_id in user_inactivity_timers: user_inactivity_timers[chat_id].cancel()
        new_timer = threading.Timer(INACTIVITY_CLEANUP_SECONDS, clear_inactive_chat, args=(chat_id,))
        user_inactivity_timers[chat_id] = new_timer
        new_timer.start()

orig_send_message = bot.send_message
orig_send_photo = bot.send_photo
orig_send_video = bot.send_video
orig_send_document = bot.send_document
orig_send_media_group = bot.send_media_group

def tracked_send_message(chat_id, *args, **kwargs):
    msg = orig_send_message(chat_id, *args, **kwargs)
    register_activity(chat_id, msg.message_id)
    return msg
bot.send_message = tracked_send_message
bot.send_photo = lambda cid, *a, **kw: register_activity(cid, orig_send_photo(cid, *a, **kw).message_id) or orig_send_photo(cid, *a, **kw)
bot.send_video = lambda cid, *a, **kw: register_activity(cid, orig_send_video(cid, *a, **kw).message_id) or orig_send_video(cid, *a, **kw)
bot.send_document = lambda cid, *a, **kw: register_activity(cid, orig_send_document(cid, *a, **kw).message_id) or orig_send_document(cid, *a, **kw)


# ==========================================
# 💳 UPI QR कोड जनरेटर
# ==========================================
def generate_upi_qr(amount, order_id):
    clean_amt = re.sub(r"[^\d.]", "", str(amount))
    upi_url = f"upi://pay?pa={UPI_ID}&pn={MERCHANT_NAME}&am={clean_amt}&cu=INR&tn=Order_{order_id}"

    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(upi_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    w, h = qr_img.size
    box_w, box_h = int(w * 0.28), int(int(w * 0.28) * 0.40)
    box_x, box_y = (w - box_w) // 2, (h - box_h) // 2
    draw = ImageDraw.Draw(qr_img)
    draw.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=6, fill="#ffffff", outline="#0b1329", width=2)

    lw = max(2, int(box_h * 0.12))
    let_w, let_h, gap = box_w * 0.18, box_h * 0.45, box_w * 0.08
    start_x = box_x + (box_w - ((let_w * 2) + gap * 2 + lw)) // 2
    start_y = box_y + (box_h - let_h) // 2

    # U, P, I Drawing logic
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


# --- इन-मेमोरी स्टेट्स ---
admin_data = {}
user_states = {}
user_qr_messages = {}
pending_orders = {}
all_orders_cache = {}
pending_lock = threading.Lock()

def generate_unique_amount(base_amount):
    base_clean = round(float(base_amount))
    flat_key = f"{base_clean:.2f}"
    with pending_lock:
        if flat_key not in pending_orders: return flat_key
        for _ in range(300):
            paise = random.randint(1, 98)
            candidate = f"{base_clean + (paise / 100):.2f}"
            if candidate not in pending_orders: return candidate
        return f"{base_clean + (random.randint(1, 99) / 100):.2f}"


# ==========================================
# 🔄 लाइव चैनल स्टेटस अपडेटर
# ==========================================
def update_channel_order_status(order, status_type, extra_text=""):
    channel_msg_id = order.get("channel_msg_id")
    if not channel_msg_id: return

    user_mention = order.get("user_mention", f"User ({order['user_id']})")
    discount_info = f"\n🎟 <b>Offer Applied:</b> {order.get('discount_percent')}% OFF (Original: ₹{order.get('original_amount')})" if order.get("discount_percent") else ""

    if status_type == "EXPIRED":
        new_text = f"🔴 <b>[UNPAID / QR EXPIRED]</b>\n\n👤 <b>User:</b> {user_mention}\n🔖 <b>Order ID:</b> <code>{order['order_id']}</code>\n📚 <b>Pack:</b> <code>{order['course_id']}</code>\n💰 <b>Amount:</b> ₹{order['amount']}{discount_info}\n⏰ <b>Initiated at:</b> {order.get('created_at_str', '')}\n⏳ <b>Status:</b> ⚠️ 10 मिनट में पेमेंट नहीं आई (स्क्रीनशॉट पेंडिंग)"
    elif status_type == "AUTO_VERIFIED":
        new_text = f"🟢 <b>[PAYMENT COMPLETED & AUTO-DELIVERED]</b>\n\n👤 <b>User:</b> {user_mention}\n🔖 <b>Order ID:</b> <code>{order['order_id']}</code>\n📚 <b>Pack:</b> <code>{order['course_id']}</code>\n💰 <b>Amount Paid:</b> ₹{order['amount']}{discount_info}\n⏰ <b>Delivered at:</b> {get_ist_time()}\n⚡ <b>Status:</b> ✅ ऑटो-वेरिफाइड (SMS द्वारा)\n\n📩 <code>{extra_text[:180]}</code>"
    elif status_type == "MANUAL_APPROVED":
        new_text = f"✅ <b>[MANUAL-APPROVED & DELIVERED]</b>\n\n👤 <b>User:</b> {user_mention}\n🔖 <b>Order ID:</b> <code>{order['order_id']}</code>\n📚 <b>Pack:</b> <code>{order['course_id']}</code>\n💰 <b>Amount:</b> ₹{order['amount']}{discount_info}\n⏰ <b>Approved at:</b> {get_ist_time()}\n⚡ <b>Status:</b> ✅ एडमिन द्वारा स्क्रीनशॉट देखकर अप्रूव किया गया"
    else: return

    try: bot.edit_message_text(new_text, chat_id=DB_CHANNEL_ID, message_id=channel_msg_id, parse_mode="HTML")
    except Exception: pass

def expire_qr(chat_id, message_id, course_id, amount_key, order_id):
    order = all_orders_cache.get(order_id)
    if order and order.get("status") == "PENDING":
        order["status"] = "EXPIRED"
        orders_col.update_one({"order_id": order_id}, {"$set": {"status": "EXPIRED"}})
        update_channel_order_status(order, "EXPIRED")

    with pending_lock: pending_orders.pop(amount_key, None)
    if chat_id in user_states and user_states[chat_id].get("amount_key") == amount_key: del user_states[chat_id]
    if chat_id in user_qr_messages and user_qr_messages[chat_id] == message_id: del user_qr_messages[chat_id]
    try: bot.delete_message(chat_id, message_id)
    except Exception: pass

    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📸 Send Screenshot (मैन्युअल वेरिफिकेशन)", callback_data=f"send_ss_{order_id}"))
    markup.row(InlineKeyboardButton("🔄 Regenerate QR", callback_data=f"pay_upi_{course_id}"))
    try: bot.send_message(chat_id, "⏳ <b>10 मिनट का समय समाप्त हो गया है! / Session Expired!</b>\n\nअगर पैसे कट चुके हैं तो नीचे <b>'📸 Send Screenshot'</b> दबाएं।", reply_markup=markup, parse_mode="HTML")
    except Exception: pass

def deliver_course_to_buyer(order, sms_text=None, is_manual=False):
    order_id, chat_id, user_id, course_id = order["order_id"], order["chat_id"], order["user_id"], order["course_id"]
    course = courses_col.find_one({"course_id": course_id})
    new_status = "COMPLETED_MANUAL" if is_manual else "COMPLETED_AUTO"
    order["status"] = new_status
    orders_col.update_one({"order_id": order_id}, {"$set": {"status": new_status, "delivered_at": get_ist_time()}})

    with pending_lock: pending_orders.pop(order.get("amount"), None)
    if user_id in user_states and user_states[user_id].get("order_id") == order_id: del user_states[user_id]
    
    # QR Delete logic (Updated)
    qr_msg_id = user_qr_messages.get(chat_id) or order.get("qr_msg_id")
    if qr_msg_id:
        try: bot.delete_message(chat_id, qr_msg_id)
        except Exception: pass
    if chat_id in user_qr_messages:
        del user_qr_messages[chat_id]

    if not course:
        try: bot.send_message(chat_id, "⚠️ Payment verify ho gayi hai, par pack nahi mila. Admin se sampark karein.")
        except Exception: pass
        return

    try:
        bot.send_message(chat_id, f"🎉 <b>Payment Verified Successfully!</b>\n\n{course['secret_text']}", parse_mode="HTML", protect_content=PROTECT_CONTENT)
    except Exception: pass

    date_now = get_ist_time()
    verify_type = "MANUAL-APPROVED" if is_manual else "AUTO-VERIFIED"
    purchases_col.insert_one({"user_id": user_id, "username": order.get("user_mention", f"User ({user_id})"), "item_info": f"{course_id} | Rate: ₹{order['amount']} | {verify_type} (order {order_id})", "date": date_now})
    if order.get("offer_id"): offers_col.update_one({"offer_code": order["offer_id"]}, {"$inc": {"used_count": 1}})
    update_channel_order_status(order, "MANUAL_APPROVED" if is_manual else "AUTO_VERIFIED", extra_text=sms_text or "")


# ==========================================
# ⏱️ बैकग्राउंड चेकर
# ==========================================
def background_order_checker(order_id, amount_str):
    for _ in range(30):
        time.sleep(20)
        order = all_orders_cache.get(order_id)
        if not order or order.get("status") != "PENDING": break
        sms_rec = sms_pool_col.find_one({"amount": amount_str, "status": "UNUSED"})
        if sms_rec:
            sms_pool_col.update_one({"_id": sms_rec["_id"]}, {"$set": {"status": "PROCESSED"}})
            deliver_course_to_buyer(order, sms_text=sms_rec.get("raw_text"), is_manual=False)
            break

# ==========================================
# 🛑 कोर्स डिलीवरी एवं प्लान मेन्यू
# ==========================================
def send_course_to_user(chat_id, course):
    raw_promo = course.get("promo_media", [])
    if isinstance(raw_promo, str):
        try: promo_items = json.loads(raw_promo)
        except Exception: promo_items = []
    elif isinstance(raw_promo, list): promo_items = raw_promo
    else: promo_items = []

    markup = InlineKeyboardMarkup().row(InlineKeyboardButton(f"🇮🇳 UPI (Pay ₹{course['amount']})", callback_data=f"pay_upi_{course['course_id']}"))
    btn_row = []
    if INTERNATIONAL_LINK: btn_row.append(InlineKeyboardButton("🌍 International", url=INTERNATIONAL_LINK))
    if CHAT_LINK: btn_row.append(InlineKeyboardButton("💬 Chat with Me", url=CHAT_LINK))
    if btn_row: markup.row(*btn_row)

    media_items = [it for it in promo_items if isinstance(it, dict) and it.get("type") in ["photo", "video"]]
    text_items = [it for it in promo_items if isinstance(it, dict) and it.get("type") == "text"]

    first_photo_caption = media_items[0].get("caption", "").strip() if media_items else ""
    custom_caption = course.get("custom_caption", "").strip()
    final_cap = f"{first_photo_caption}\n\n{custom_caption}" if first_photo_caption and custom_caption else (first_photo_caption or custom_caption)

    if not media_items:
        full_text = "".join(t.get("caption", "") + "\n\n" for t in text_items) + custom_caption
        if not full_text.strip(): full_text = f"📚 <b>Pack: {course['course_id']}</b>\nPrice: ₹{course['amount']}"
        bot.send_message(chat_id, full_text.strip(), reply_markup=markup, parse_mode="HTML", protect_content=PROTECT_CONTENT)
    elif len(media_items) == 1:
        it = media_items[0]
        try:
            if it["type"] == "photo": bot.send_photo(chat_id, it["file_id"], caption=final_cap, reply_markup=markup, parse_mode="HTML", protect_content=PROTECT_CONTENT)
            elif it["type"] == "video": bot.send_video(chat_id, it["file_id"], caption=final_cap, reply_markup=markup, parse_mode="HTML", protect_content=PROTECT_CONTENT)
        except Exception: pass
    else:
        media_group_html = []
        for i, item in enumerate(media_items):
            cap = final_cap if i == 0 else ""
            if item["type"] == "photo": media_group_html.append(InputMediaPhoto(item["file_id"], caption=cap, parse_mode="HTML"))
            elif item["type"] == "video": media_group_html.append(InputMediaVideo(item["file_id"], caption=cap, parse_mode="HTML"))
        try:
            sent_grp = orig_send_media_group(chat_id, media_group_html, protect_content=PROTECT_CONTENT)
            for m in sent_grp: register_activity(chat_id, m.message_id)
        except Exception: pass
        try: bot.send_message(chat_id, f"👆 <b>Choose an option to buy (₹{course['amount']}):</b>\n", reply_markup=markup, parse_mode="HTML")
        except Exception: pass

def send_batch_to_user(chat_id, batch):
    bot.send_message(chat_id, f"📦 <b>{batch['title']}</b>\nAll packs are listed below:", parse_mode="HTML")
    raw_cids = batch.get("course_ids", [])
    course_ids = json.loads(raw_cids) if isinstance(raw_cids, str) else raw_cids if isinstance(raw_cids, list) else []
    for cid in course_ids:
        c_data = courses_col.find_one({"course_id": cid})
        if c_data: send_course_to_user(chat_id, c_data)

def send_custom_start_menu(chat_id):
    cfg = settings_col.find_one({"_id": "start_menu"})
    markup = InlineKeyboardMarkup().row(InlineKeyboardButton("📋 View All Plans / Packs", callback_data="user_view_plans"))
    if cfg:
        for b in cfg.get("buttons", []):
            if b["url"].startswith("http"): markup.row(InlineKeyboardButton(b["text"], url=b["url"]))
            else: markup.row(InlineKeyboardButton(b["text"], callback_data=f"mainmenu_{b['url']}"))
        m_type, txt, fid = cfg.get("media_type"), cfg.get("text", ""), cfg.get("file_id")
        if m_type == "photo" and fid: bot.send_photo(chat_id, fid, caption=txt, reply_markup=markup, parse_mode="HTML")
        elif m_type == "video" and fid: bot.send_video(chat_id, fid, caption=txt, reply_markup=markup, parse_mode="HTML")
        else: bot.send_message(chat_id, txt or "👋 Welcome to our Store!", reply_markup=markup, parse_mode="HTML")
    else: bot.send_message(chat_id, "👋 <b>Welcome to our Store!</b>\n\nSelect an option below to get started:", reply_markup=markup, parse_mode="HTML")

def send_admin_panel(chat_id):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("➕ Add Single Pack", callback_data="admin_add_course"))
    markup.row(InlineKeyboardButton("🗑 Delete Pack", callback_data="admin_delete_course"))
    markup.row(InlineKeyboardButton("📦 Pack Batch (Multi-Pack)", callback_data="admin_create_batch"))
    markup.row(InlineKeyboardButton("🎟 Create Promo Offer", callback_data="admin_create_offer"))
    markup.row(InlineKeyboardButton("📋 Manage Store Plans", callback_data="admin_manage_plans"))
    markup.row(InlineKeyboardButton("🎨 Customize Start Menu", callback_data="admin_custom_menu"))
    markup.row(InlineKeyboardButton("🔗 Advanced File to Link", callback_data="admin_file_link"))
    markup.row(InlineKeyboardButton("📢 Advanced Broadcast", callback_data="admin_broadcast"))
    markup.row(InlineKeyboardButton("👥 User Info", callback_data="admin_user_info"))
    bot.send_message(chat_id, "🛠 <b>Admin Panel</b>\nPlease select an option:\n", reply_markup=markup, parse_mode="HTML")


# ==========================================
# 1. कमांड्स
# ==========================================
@bot.message_handler(commands=["start"])
def start_command(message):
    user_id = message.chat.id
    register_activity(user_id, message.message_id)
    users_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "updated_at": get_ist_time()}}, upsert=True)
    param = message.text.split()[1].strip() if len(message.text.split()) > 1 else ""

    if param.startswith("off_"):
        offer = offers_col.find_one({"offer_code": param})
        if not offer:
            bot.send_message(user_id, "❌ <b>यह ऑफर अमान्य है या समाप्त हो चुका है।</b>", parse_mode="HTML")
            return send_custom_start_menu(user_id)
        now_ts = time.time()
        if offer.get("expires_at_ts") and now_ts > offer["expires_at_ts"]:
            bot.send_message(user_id, "⏳ <b>यह ऑफर समाप्त (Expired) हो चुका है!</b>", parse_mode="HTML")
            return send_custom_start_menu(user_id)
        if offer.get("max_users", -1) != -1 and offer.get("used_count", 0) >= offer["max_users"]:
            bot.send_message(user_id, "⚠️ <b>इस ऑफर की अधिकतम सीमा समाप्त हो चुकी है!</b>", parse_mode="HTML")
            return send_custom_start_menu(user_id)

        users_col.update_one({"user_id": user_id}, {"$set": {"active_offer": offer}}, upsert=True)
        bot.send_message(user_id, f"🎉 <b>बधाई हो! {offer['discount_percent']}% का डिस्काउंट एक्टिवेट हो गया है!</b>\n\nयह छूट {'सभी कोर्सेज' if offer['target_type'] == 'all' else 'विशिष्ट कोर्स (' + offer['target_course_id'] + ')'} पर लागू होगी।", parse_mode="HTML")
        if offer["target_type"] == "single":
            c = courses_col.find_one({"course_id": offer["target_course_id"]})
            if c: send_course_to_user(user_id, c)
            else: send_custom_start_menu(user_id)
        else: send_custom_start_menu(user_id)

    elif param.startswith("b_"):
        batch = batches_col.find_one({"batch_id": param})
        if batch: send_batch_to_user(user_id, batch)
        else: bot.send_message(user_id, "❌ <b>This link has expired.</b>", parse_mode="HTML")

    elif param.startswith("c_"):
        course = courses_col.find_one({"course_id": param})
        if course: send_course_to_user(user_id, course)
        else: bot.send_message(user_id, "❌ <b>This link is not available.</b>", parse_mode="HTML")

    elif param.startswith("f_"):
        file_data = file_links_col.find_one({"file_code": param})
        if file_data:
            m_items, btns = file_data.get("media_data", []), file_data.get("button_data", [])
            markup = InlineKeyboardMarkup()
            for b in btns: markup.row(InlineKeyboardButton(b["text"], url=b["url"]))
            if len(m_items) == 1:
                it = m_items[0]
                try:
                    if it["type"] == "text": bot.send_message(user_id, it["caption"], reply_markup=markup, parse_mode="HTML", protect_content=PROTECT_CONTENT)
                    elif it["type"] == "photo": bot.send_photo(user_id, it["file_id"], caption=it["caption"], reply_markup=markup, parse_mode="HTML", protect_content=PROTECT_CONTENT)
                    elif it["type"] == "video": bot.send_video(user_id, it["file_id"], caption=it["caption"], reply_markup=markup, parse_mode="HTML", protect_content=PROTECT_CONTENT)
                    elif it["type"] == "document": bot.send_document(user_id, it["file_id"], caption=it["caption"], reply_markup=markup, parse_mode="HTML", protect_content=PROTECT_CONTENT)
                except Exception as e: bot.send_message(user_id, f"❌ Error: {e}")
            elif len(m_items) > 1:
                m_group = []
                for it in m_items:
                    if it["type"] == "photo": m_group.append(InputMediaPhoto(it["file_id"], caption=it["caption"], parse_mode="HTML"))
                    elif it["type"] == "video": m_group.append(InputMediaVideo(it["file_id"], caption=it["caption"], parse_mode="HTML"))
                    elif it["type"] == "document": m_group.append(InputMediaDocument(it["file_id"], caption=it["caption"], parse_mode="HTML"))
                try:
                    sent = orig_send_media_group(user_id, m_group, protect_content=PROTECT_CONTENT)
                    for m in sent: register_activity(user_id, m.message_id)
                    if btns or any(i["type"] == "text" for i in m_items): bot.send_message(user_id, "👇 <b>Check the link(s) below:</b>", reply_markup=markup, parse_mode="HTML")
                except Exception as e: bot.send_message(user_id, f"❌ Error: {e}")
        else: bot.send_message(user_id, "❌ <b>File not found or expired.</b>", parse_mode="HTML")
    else:
        if user_id == ADMIN_ID: send_admin_panel(user_id)
        else: send_custom_start_menu(user_id)


# ==========================================
# 2. मैसेज हैंडलर (एडमिन + स्क्रीनशॉट)
# ==========================================
@bot.message_handler(content_types=["photo", "video", "document", "text"])
def handle_all_messages(message):
    user_id = message.chat.id
    register_activity(user_id, message.message_id)

    # 📸 यूज़र पेमेंट स्क्रीनशॉट
    if user_id in user_states and user_states[user_id].get("step") == "WAITING_PAYMENT_SS":
        order_id = user_states[user_id].get("order_id")
        order = all_orders_cache.get(order_id) or orders_col.find_one({"order_id": order_id})
        if not message.photo and not message.document:
            bot.send_message(user_id, "❌ <b>कृपया फोटो या डॉक्यूमेंट में स्क्रीनशॉट भेजें।</b>", parse_mode="HTML")
            return
        fid = message.photo[-1].file_id if message.photo else message.document.file_id
        bot.send_message(user_id, "⏳ <b>वेरिफिकेशन पेंडिंग है...</b>\n\nस्क्रीनशॉट एडमिन को भेज दिया गया है।", parse_mode="HTML")
        del user_states[user_id]

        u_str = f"@{message.from_user.username}" if message.from_user.username else "No Username"
        u_men = f"<a href='tg://user?id={user_id}'>{message.from_user.first_name}</a> ({u_str})"
        cap = f"📩 <b>[MANUAL APPROVAL - PAYMENT SCREENSHOT]</b>\n\n👤 <b>User:</b> {u_men}\n🆔 <b>ID:</b> <code>{user_id}</code>\n🔖 <b>Order:</b> <code>{order_id}</code>\n📚 <b>Pack:</b> <code>{order['course_id'] if order else 'N/A'}</code>\n💰 <b>Amount:</b> ₹{order['amount'] if order else 'N/A'}\n⏰ <b>Time:</b> {get_ist_time()}"
        
        c_url = f"https://t.me/{message.from_user.username}" if message.from_user.username else f"tg://user?id={user_id}"
        m_admin = InlineKeyboardMarkup().row(InlineKeyboardButton("✅ Approve", callback_data=f"man_appr_{order_id}"), InlineKeyboardButton("❌ Deny", callback_data=f"man_deny_{order_id}")).row(InlineKeyboardButton("💬 Chat with User", url=c_url))
        try:
            if message.photo: orig_send_photo(DB_CHANNEL_ID, fid, caption=cap, reply_markup=m_admin, parse_mode="HTML")
            else: orig_send_document(DB_CHANNEL_ID, fid, caption=cap, reply_markup=m_admin, parse_mode="HTML")
        except Exception as e: orig_send_message(ADMIN_ID, f"❌ Channel error: {e}")
        return

    # --- ADMIN WORKFLOWS ---
    if user_id == ADMIN_ID and user_id in admin_data:
        step = admin_data[ADMIN_ID].get("step")

        if step == "DELETE_COURSE":
            cid = message.text.strip()
            if courses_col.delete_one({"course_id": cid}).deleted_count:
                settings_col.update_one({"_id": "store_plans"}, {"$pull": {"course_ids": cid}})
                bot.send_message(ADMIN_ID, f"✅ <b>कोर्स <code>{cid}</code> डिलीट कर दिया गया है!</b>", parse_mode="HTML")
            else: bot.send_message(ADMIN_ID, f"❌ <b>कोर्स <code>{cid}</code> नहीं मिला।</b>", parse_mode="HTML")
            del admin_data[ADMIN_ID]
            return send_admin_panel(ADMIN_ID)

        elif step == "ADD_PLAN_ID":
            cid = message.text.strip()
            if courses_col.find_one({"course_id": cid}):
                settings_col.update_one({"_id": "store_plans"}, {"$addToSet": {"course_ids": cid}}, upsert=True)
                bot.send_message(ADMIN_ID, f"✅ <b>कोर्स <code>{cid}</code> स्टोर प्लान में जोड़ दिया गया है!</b>", parse_mode="HTML")
            else: bot.send_message(ADMIN_ID, f"❌ <b>यह कोर्स ID उपलब्ध नहीं है।</b>", parse_mode="HTML")
            del admin_data[ADMIN_ID]
            return send_admin_panel(ADMIN_ID)

        elif step == "OFFER_DISCOUNT":
            try:
                disc = int(re.sub(r"[^\d]", "", message.text.strip()))
                if not (1 <= disc <= 100): raise ValueError()
                admin_data[ADMIN_ID]["discount"] = disc
                admin_data[ADMIN_ID]["step"] = "OFFER_TARGET"
                m = InlineKeyboardMarkup().row(InlineKeyboardButton("🌐 सभी कोर्सेज पर", callback_data="offtarget_all")).row(InlineKeyboardButton("🎯 किसी एक कोर्स पर", callback_data="offtarget_single"))
                bot.send_message(ADMIN_ID, f"✅ डिस्काउंट <b>{disc}%</b> सेट हो गया!\nअब चुनें कि यह किस पर लागू होगा:", reply_markup=m, parse_mode="HTML")
            except Exception: bot.send_message(ADMIN_ID, "❌ कृपया 1 से 100 के बीच एक सही प्रतिशत लिखें।")
            return

        elif step == "OFFER_SINGLE_CID":
            cid = message.text.strip()
            if not courses_col.find_one({"course_id": cid}):
                return bot.send_message(ADMIN_ID, "❌ <b>यह कोर्स ID नहीं मिली। सही ID भेजें:</b>", parse_mode="HTML")
            admin_data[ADMIN_ID]["target_course_id"] = cid
            admin_data[ADMIN_ID]["step"] = "OFFER_LIMIT"
            bot.send_message(ADMIN_ID, "👥 <b>यह ऑफर कितने यूजर्स के लिए है?</b>\n(असीमित के लिए 0 लिखें):", parse_mode="HTML")
            return

        elif step == "OFFER_LIMIT":
            try:
                lim = int(re.sub(r"[^\d]", "", message.text.strip()))
                admin_data[ADMIN_ID]["max_users"] = -1 if lim == 0 else lim
                admin_data[ADMIN_ID]["step"] = "OFFER_HOURS"
                bot.send_message(ADMIN_ID, "⏳ <b>यह ऑफर कितने घंटों तक एक्टिव रहेगा?</b> (जैसे 24 या 48):", parse_mode="HTML")
            except Exception: bot.send_message(ADMIN_ID, "❌ कृपया एक सही संख्या लिखें।")
            return

        elif step == "OFFER_HOURS":
            try:
                hrs = float(re.sub(r"[^\d.]", "", message.text.strip()))
                off_code, now_ts = "off_" + str(uuid.uuid4())[:6], time.time()
                exp_str = (datetime.now(IST) + timedelta(hours=hrs)).strftime("%d-%m-%Y %I:%M %p")
                doc = {
                    "offer_code": off_code, "discount_percent": admin_data[ADMIN_ID]["discount"],
                    "target_type": admin_data[ADMIN_ID]["target_type"], "target_course_id": admin_data[ADMIN_ID].get("target_course_id"),
                    "max_users": admin_data[ADMIN_ID]["max_users"], "used_count": 0, "created_at_ts": now_ts,
                    "expires_at_ts": now_ts + (hrs * 3600), "expires_str": exp_str
                }
                offers_col.insert_one(doc)
                l = f"https://t.me/{bot.get_me().username}?start={off_code}"
                bot.send_message(ADMIN_ID, f"🎉 <b>डिस्काउंट ऑफर लिंक बन गया!</b>\n\n🎟 <b>Discount:</b> {doc['discount_percent']}%\n👉 <code>{l}</code>", parse_mode="HTML")
                del admin_data[ADMIN_ID]
                send_admin_panel(ADMIN_ID)
            except Exception: bot.send_message(ADMIN_ID, "❌ कृपया घंटों की सही संख्या भेजें।")
            return

        elif step == "MENU_CUSTOM_CONTENT":
            mt, fid = "text", None
            if message.photo: mt, fid = "photo", message.photo[-1].file_id
            elif message.video: mt, fid = "video", message.video.file_id
            admin_data[ADMIN_ID]["menu_content"] = {"media_type": mt, "file_id": fid, "text": get_formatted_text(message)}
            admin_data[ADMIN_ID]["buttons"], admin_data[ADMIN_ID]["step"] = [], "MENU_ADD_BUTTONS"
            m = InlineKeyboardMarkup().row(InlineKeyboardButton("🚀 Finish & Save", callback_data="menu_finish_save"))
            bot.send_message(ADMIN_ID, "✅ <b>Content Saved!</b>\nबटन जोड़ें: <code>Button Name - Link</code> या Finish दबाएं।", reply_markup=m, parse_mode="HTML")
            return

        elif step == "MENU_ADD_BUTTONS":
            txt = message.text.strip()
            if " - " in txt:
                try:
                    t, u = txt.split(" - ", 1)
                    admin_data[ADMIN_ID]["buttons"].append({"text": t.strip(), "url": u.strip()})
                    m = InlineKeyboardMarkup().row(InlineKeyboardButton("🚀 Finish & Save Menu", callback_data="menu_finish_save"))
                    bot.send_message(ADMIN_ID, f"✅ <b>Button Added! ({len(admin_data[ADMIN_ID]['buttons'])})</b>", reply_markup=m, parse_mode="HTML")
                except Exception: bot.send_message(ADMIN_ID, "❌ Format error. <code>Name - Link</code>", parse_mode="HTML")
            return

        elif step == "PROMO":
            mt, fid = "text", None
            if message.photo: mt, fid = "photo", message.photo[-1].file_id
            elif message.video: mt, fid = "video", message.video.file_id
            admin_data[ADMIN_ID]["promo"].append({"type": mt, "file_id": fid, "caption": get_formatted_text(message)})
            m = InlineKeyboardMarkup().row(InlineKeyboardButton("➡️ Next Step (Price)", callback_data="next_price"))
            bot.send_message(ADMIN_ID, f"✅ <b>{mt.capitalize()} saved!</b>", reply_markup=m, parse_mode="HTML")
            return

        elif step == "AMOUNT":
            amt = re.sub(r"[^\d.]", "", message.text.strip())
            if not amt: return bot.send_message(ADMIN_ID, "❌ <b>Numbers only.</b>", parse_mode="HTML")
            admin_data[ADMIN_ID]["amount"], admin_data[ADMIN_ID]["step"] = amt, "CAPTION"
            m = InlineKeyboardMarkup().row(InlineKeyboardButton("⏭ Skip (No Caption)", callback_data="skip_caption"))
            bot.send_message(ADMIN_ID, f"✅ <b>Price ₹{amt} saved!</b>\n📝 Type optional extra caption, or skip:", reply_markup=m, parse_mode="HTML")
            return

        elif step == "CAPTION":
            admin_data[ADMIN_ID]["caption"], admin_data[ADMIN_ID]["step"] = get_formatted_text(message), "SECRET"
            bot.send_message(ADMIN_ID, "✅ <b>Caption saved!</b>\n🔗 Now send final secret link or content:", parse_mode="HTML")
            return

        elif step == "SECRET":
            cid = "c_" + str(uuid.uuid4())[:6]
            courses_col.update_one({"course_id": cid}, {"$set": {"course_id": cid, "promo_media": admin_data[ADMIN_ID]["promo"], "amount": admin_data[ADMIN_ID]["amount"], "custom_caption": admin_data[ADMIN_ID]["caption"], "secret_text": get_formatted_text(message)}}, upsert=True)
            try: bot.send_message(DB_CHANNEL_ID, f"🆕 <b>[NEW COURSE CREATED]</b>\n\n🆔 <code>{cid}</code>\n💰 ₹{admin_data[ADMIN_ID]['amount']}\n📝 {admin_data[ADMIN_ID].get('caption') or 'None'}", parse_mode="HTML")
            except Exception: pass
            
            if admin_data[ADMIN_ID].get("mode") == "single":
                bot.send_message(ADMIN_ID, f"🎉 <b>Pack created!</b>\n👉 <code>https://t.me/{bot.get_me().username}?start={cid}</code>", parse_mode="HTML")
                del admin_data[ADMIN_ID]
                send_admin_panel(ADMIN_ID)
            elif admin_data[ADMIN_ID].get("mode") == "batch":
                admin_data[ADMIN_ID]["course_ids"].append(cid)
                admin_data[ADMIN_ID]["step"] = "NEXT_ACTION"
                m = InlineKeyboardMarkup().row(InlineKeyboardButton("➕ Add Another", callback_data="batch_add_next")).row(InlineKeyboardButton("✅ Finish Batch", callback_data="batch_finish"))
                bot.send_message(ADMIN_ID, f"✅ <b>Pack saved!</b>", reply_markup=m, parse_mode="HTML")
            return

        elif step == "TITLE":
            admin_data[ADMIN_ID]["title"], admin_data[ADMIN_ID]["step"], admin_data[ADMIN_ID]["promo"] = message.text.strip(), "PROMO", []
            m = InlineKeyboardMarkup().row(InlineKeyboardButton("➡️ Next Step", callback_data="next_price"))
            bot.send_message(ADMIN_ID, f"✅ Title saved. <b>Send promo media/text:</b>", reply_markup=m, parse_mode="HTML")
            return
            
        elif step in ["BC_MEDIA", "FTL_MEDIA"]:
            mt, fid = "text", None
            if message.photo: mt, fid = "photo", message.photo[-1].file_id
            elif message.video: mt, fid = "video", message.video.file_id
            elif message.document: mt, fid = "document", message.document.file_id
            admin_data[ADMIN_ID].setdefault("media", []).append({"type": mt, "file_id": fid, "caption": get_formatted_text(message)})
            cb = "bc_done" if step == "BC_MEDIA" else "ftl_done"
            m = InlineKeyboardMarkup().row(InlineKeyboardButton("✅ Done Adding", callback_data=cb))
            bot.send_message(ADMIN_ID, "✅ <b>Saved!</b> Send another or click Done.", reply_markup=m, parse_mode="HTML")
            return

        elif step in ["BC_BUTTONS", "FTL_BUTTONS"]:
            txt = message.text.strip()
            if " - " in txt:
                try:
                    t, u = txt.split(" - ", 1)
                    admin_data[ADMIN_ID].setdefault("buttons", []).append({"text": t.strip(), "url": u.strip()})
                    cb = "bc_finish" if step == "BC_BUTTONS" else "ftl_finish"
                    m = InlineKeyboardMarkup().row(InlineKeyboardButton("🚀 Finish", callback_data=cb))
                    bot.send_message(ADMIN_ID, f"✅ <b>Button Added!</b>", reply_markup=m, parse_mode="HTML")
                except Exception: bot.send_message(ADMIN_ID, "❌ Format Error.", parse_mode="HTML")
            return


# ==========================================
# 3. कॉलबैक बटन्स हैंडलर
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    data, chat_id, msg_id = call.data, call.message.chat.id, call.message.message_id
    register_activity(chat_id)

    if data == "user_view_plans":
        bot.answer_callback_query(call.id)
        plans = settings_col.find_one({"_id": "store_plans"})
        c_ids = plans.get("course_ids", []) if plans else [c["course_id"] for c in courses_col.find().limit(10)]
        if not c_ids: return bot.send_message(chat_id, "ℹ️ कोई प्लान उपलब्ध नहीं है।", parse_mode="HTML")
        bot.send_message(chat_id, "📚 <b>उपलब्ध कोर्सेज/प्लान्स:</b>", parse_mode="HTML")
        for cid in c_ids:
            c = courses_col.find_one({"course_id": cid})
            if c: send_course_to_user(chat_id, c)
        return

    if data == "admin_create_offer":
        bot.answer_callback_query(call.id)
        admin_data[ADMIN_ID] = {"step": "OFFER_DISCOUNT"}
        bot.edit_message_text("🎟 <b>डिस्काउंट ऑफर बनाएं:</b>\nकितने प्रतिशत का डिस्काउंट देना है? (जैसे 50):", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
        return
    elif data == "offtarget_all":
        bot.answer_callback_query(call.id)
        admin_data[ADMIN_ID]["target_type"], admin_data[ADMIN_ID]["step"] = "all", "OFFER_LIMIT"
        bot.edit_message_text("👥 <b>ऑफर कितने यूजर्स क्लेम कर सकते हैं?</b> (0 = असीमित):", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
        return
    elif data == "offtarget_single":
        bot.answer_callback_query(call.id)
        admin_data[ADMIN_ID]["target_type"], admin_data[ADMIN_ID]["step"] = "single", "OFFER_SINGLE_CID"
        bot.edit_message_text("🎯 <b>कोर्स ID भेजें:</b> (e.g. <code>c_abc123</code>)", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
        return

    if data == "admin_delete_course":
        bot.answer_callback_query(call.id)
        admin_data[ADMIN_ID] = {"step": "DELETE_COURSE"}
        bot.edit_message_text("🗑 <b>कोर्स डिलीट करें:</b>\nCourse ID भेजें:", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
        return

    if data == "admin_manage_plans":
        bot.answer_callback_query(call.id)
        c_ids = (settings_col.find_one({"_id": "store_plans"}) or {}).get("course_ids", [])
        text = f"📋 <b>Manage Store Plans ({len(c_ids)}):</b>\n" + "".join(f"• <code>{cid}</code>\n" for cid in c_ids)
        m = InlineKeyboardMarkup().row(InlineKeyboardButton("➕ Add Course", callback_data="plan_add_id")).row(InlineKeyboardButton("🗑 Clear All", callback_data="plan_clear_all")).row(InlineKeyboardButton("🔙 Back", callback_data="back_to_admin"))
        bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=m, parse_mode="HTML")
        return
    elif data == "plan_add_id":
        bot.answer_callback_query(call.id)
        admin_data[ADMIN_ID] = {"step": "ADD_PLAN_ID"}
        bot.edit_message_text("➕ लिस्ट में जोड़ने के लिए <b>Course ID</b> भेजें:", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
        return
    elif data == "plan_clear_all":
        settings_col.delete_one({"_id": "store_plans"})
        bot.answer_callback_query(call.id, "सभी प्लान्स रीसेट कर दिए गए हैं!", show_alert=True)
        return send_admin_panel(chat_id)

    if data == "admin_custom_menu":
        m = InlineKeyboardMarkup().row(InlineKeyboardButton("✏️ Set New", callback_data="menu_set_new")).row(InlineKeyboardButton("🗑 Reset Default", callback_data="menu_reset_default")).row(InlineKeyboardButton("🔙 Back", callback_data="back_to_admin"))
        bot.edit_message_text("🎨 <b>Customize Start Menu</b>", chat_id=chat_id, message_id=msg_id, reply_markup=m, parse_mode="HTML")
        return
    elif data == "menu_set_new":
        admin_data[ADMIN_ID] = {"step": "MENU_CUSTOM_CONTENT"}
        bot.edit_message_text("📝 <b>Start Menu Content</b>\nफ़ोटो, वीडियो या टेक्स्ट भेजें:", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
        return
    elif data == "menu_finish_save":
        c = admin_data.get(ADMIN_ID, {}).get("menu_content", {})
        settings_col.update_one({"_id": "start_menu"}, {"$set": {"media_type": c.get("media_type", "text"), "file_id": c.get("file_id"), "text": c.get("text", ""), "buttons": admin_data.get(ADMIN_ID, {}).get("buttons", []), "updated_at": get_ist_time()}}, upsert=True)
        del admin_data[ADMIN_ID]
        bot.edit_message_text("🎉 <b>Saved!</b>", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
        return send_admin_panel(chat_id)
    elif data == "menu_reset_default":
        settings_col.delete_one({"_id": "start_menu"})
        bot.edit_message_text("✅ <b>Reset!</b>", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
        return send_admin_panel(chat_id)

    if data.startswith("send_ss_"):
        bot.answer_callback_query(call.id)
        user_states[chat_id] = {"step": "WAITING_PAYMENT_SS", "order_id": data.replace("send_ss_", "")}
        bot.send_message(chat_id, "📸 <b>कृपया अपनी पेमेंट का स्क्रीनशॉट भेजें।</b>", parse_mode="HTML")
        return
    if data.startswith("man_appr_"):
        oid = data.replace("man_appr_", "")
        o = all_orders_cache.get(oid) or orders_col.find_one({"order_id": oid})
        if not o: return bot.answer_callback_query(call.id, "❌ Order not found.", show_alert=True)
        deliver_course_to_buyer(o, sms_text="Manual Approval", is_manual=True)
        bot.answer_callback_query(call.id, "✅ Approved!", show_alert=True)
        try:
            bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
            orig_send_message(chat_id, f"✅ <b>ORDER {oid} APPROVED</b>\n⏰ {get_ist_time()}", reply_to_message_id=msg_id, parse_mode="HTML")
        except Exception: pass
        return
    if data.startswith("man_deny_"):
        oid = data.replace("man_deny_", "")
        o = all_orders_cache.get(oid) or orders_col.find_one({"order_id": oid})
        if not o: return bot.answer_callback_query(call.id, "❌ Not found.", show_alert=True)
        m = InlineKeyboardMarkup().row(InlineKeyboardButton("💬 Contact Admin", url=CHAT_LINK)) if CHAT_LINK else None
        try: bot.send_message(o["chat_id"], f"❌ <b>Payment Failed!</b>\nऑर्डर <code>{oid}</code> रिजेक्ट कर दिया गया है।", reply_markup=m, parse_mode="HTML")
        except Exception: pass
        bot.answer_callback_query(call.id, "❌ Rejected.", show_alert=True)
        try:
            bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
            orig_send_message(chat_id, f"❌ <b>ORDER {oid} REJECTED</b>", reply_to_message_id=msg_id, parse_mode="HTML")
        except Exception: pass
        return

    # 💳 UPI पेमेंट जनरेटर
    if data.startswith("pay_upi_"):
        bot.answer_callback_query(call.id, "⏳ Generating Fresh QR...", show_alert=False)
        course_id = data.replace("pay_upi_", "")
        course = courses_col.find_one({"course_id": course_id})
        if course:
            if chat_id in user_states:
                with pending_lock: pending_orders.pop(user_states[chat_id].get("amount_key"), None)
                if chat_id in user_qr_messages:
                    try: bot.delete_message(chat_id, user_qr_messages.pop(chat_id))
                    except Exception: pass

            base_price = float(course["amount"])
            active_off = (users_col.find_one({"user_id": call.from_user.id}) or {}).get("active_offer")
            disc_pct, off_code, final_base = None, None, base_price

            if active_off:
                now_ts = time.time()
                valid_e = not (active_off.get("expires_at_ts") and now_ts > active_off["expires_at_ts"])
                valid_l = not (active_off.get("max_users", -1) != -1 and active_off.get("used_count", 0) >= active_off["max_users"])
                valid_t = active_off.get("target_type") == "all" or active_off.get("target_course_id") == course_id
                if valid_e and valid_l and valid_t:
                    disc_pct, off_code = active_off["discount_percent"], active_off["offer_code"]
                    final_base = round(base_price * (1.0 - (disc_pct / 100.0)), 2)

            order_id, amt_key = str(uuid.uuid4())[:8], generate_unique_amount(final_base)
            u_men = f"<a href='tg://user?id={call.from_user.id}'>{call.from_user.first_name}</a> (@{call.from_user.username or ''})"
            
            o_data = {
                "order_id": order_id, "course_id": course_id, "user_id": call.from_user.id, "chat_id": chat_id,
                "user_mention": u_men, "amount": amt_key, "original_amount": str(base_price), "discount_percent": disc_pct,
                "offer_id": off_code, "status": "PENDING", "created_at_dt": datetime.now(timezone.utc),
                "created_at_str": get_ist_time(), "created_at": time.time(), "channel_msg_id": None
            }

            d_log = f"\n🎟 <b>Offer Applied:</b> {disc_pct}% OFF (Original: ₹{base_price})" if disc_pct else ""
            ch_txt = f"🟡 <b>[ORDER INITIATED - QR]</b>\n\n👤 <b>User:</b> {u_men}\n🆔 <b>ID:</b> <code>{call.from_user.id}</code>\n🔖 <b>Order:</b> <code>{order_id}</code>\n📚 <b>Pack:</b> <code>{course_id}</code>\n💰 <b>Amount:</b> ₹{amt_key}{d_log}\n⏰ <b>Time:</b> {get_ist_time()}\n⏳ <b>Status:</b> ⏳ पेमेंट का इंतज़ार है"
            c_url = f"https://t.me/{call.from_user.username}" if call.from_user.username else f"tg://user?id={call.from_user.id}"
            try:
                ch_msg = bot.send_message(DB_CHANNEL_ID, ch_txt, reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("💬 Chat", url=c_url)), parse_mode="HTML")
                o_data["channel_msg_id"] = ch_msg.message_id
            except Exception: pass

            orders_col.insert_one(o_data.copy())
            with pending_lock:
                pending_orders[amt_key] = o_data
                all_orders_cache[order_id] = o_data
            user_states[chat_id] = {"course_id": course_id, "order_id": order_id, "amount_key": amt_key}

            sms_rec = sms_pool_col.find_one({"amount": amt_key, "status": "UNUSED"})
            if sms_rec:
                sms_pool_col.update_one({"_id": sms_rec["_id"]}, {"$set": {"status": "PROCESSED"}})
                return deliver_course_to_buyer(o_data, sms_text=sms_rec.get("raw_text"), is_manual=False)

            qr_img_bio, clean_amt = generate_upi_qr(amt_key, order_id)
            inv = f"👤 <b>User:</b> {call.from_user.first_name}\n🆔 <b>Order:</b> <code>{order_id}</code>\n📅 <b>Time:</b> {get_ist_time()}\n💰 <b>Amount:</b> ₹{clean_amt}\n"
            if disc_pct: inv += f"🎉 <i>Discount: {disc_pct}% OFF (₹{base_price} ➔ ₹{clean_amt})</i>\n"
            if course.get("custom_caption"): inv += f"\n📝 {course['custom_caption']}\n"
            inv += f"\n⚠️ <b>Exact Amount Pay Karein.</b>\n⏳ <i>QR {QR_EXPIRY_SECONDS // 60} min mein expire hoga.</i>"

            m = InlineKeyboardMarkup()
            if CHAT_LINK: m.row(InlineKeyboardButton("💬 Chat with Admin", url=CHAT_LINK))
            sent_msg = bot.send_photo(chat_id, photo=qr_img_bio, caption=inv, reply_markup=m, parse_mode="HTML")
            user_qr_messages[chat_id] = sent_msg.message_id
            
            # QR मैसेज की ID डेटाबेस में सेव करें
            orders_col.update_one({"order_id": order_id}, {"$set": {"qr_msg_id": sent_msg.message_id}})

            threading.Timer(QR_EXPIRY_SECONDS, expire_qr, args=(chat_id, sent_msg.message_id, course_id, amt_key, order_id)).start()
            threading.Thread(target=background_order_checker, args=(order_id, amt_key), daemon=True).start()
        return

    bot.answer_callback_query(call.id)
    if data == "admin_add_course":
        admin_data[ADMIN_ID] = {"mode": "single", "step": "PROMO", "promo": [], "amount": None, "caption": ""}
        bot.edit_message_text("📝 <b>Step 1/4: Promo Media OR Text</b>", chat_id=chat_id, message_id=msg_id, reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("➡️ Next", callback_data="next_price")), parse_mode="HTML")
    elif data == "admin_create_batch":
        admin_data[ADMIN_ID] = {"mode": "batch", "step": "TITLE", "course_ids": []}
        bot.edit_message_text("📦 <b>Create Pack Batch</b>\nSend Title:", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    elif data in ["admin_file_link", "admin_broadcast"]:
        admin_data[ADMIN_ID] = {"step": "FTL_MEDIA" if data == "admin_file_link" else "BC_MEDIA", "media": []}
        bot.edit_message_text(f"{'📎 File to Link' if data == 'admin_file_link' else '📢 Broadcast'}\nSend Media/Text.", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    elif data == "next_price" and ADMIN_ID in admin_data:
        admin_data[ADMIN_ID]["step"] = "AMOUNT"
        bot.edit_message_text("💰 <b>Step 2/4: Price (INR)</b>", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    elif data == "skip_caption" and ADMIN_ID in admin_data:
        admin_data[ADMIN_ID]["caption"], admin_data[ADMIN_ID]["step"] = "", "SECRET"
        bot.edit_message_text("✅ <b>Step 4/4: Secret Link/Text</b>", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    elif data == "batch_add_next":
        admin_data[ADMIN_ID]["step"], admin_data[ADMIN_ID]["promo"], admin_data[ADMIN_ID]["caption"] = "PROMO", [], ""
        bot.edit_message_text("📝 <b>Send promo for next pack:</b>", chat_id=chat_id, message_id=msg_id, reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("➡️ Next", callback_data="next_price")), parse_mode="HTML")
    elif data == "batch_finish":
        d = admin_data.get(ADMIN_ID)
        if d and d.get("course_ids"):
            bid = "b_" + str(uuid.uuid4())[:6]
            batches_col.update_one({"batch_id": bid}, {"$set": {"batch_id": bid, "title": d["title"], "course_ids": d["course_ids"]}}, upsert=True)
            bot.edit_message_text(f"🎉 <b>Batch Created!</b>\n👉 <code>https://t.me/{bot.get_me().username}?start={bid}</code>", chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
            del admin_data[ADMIN_ID]
            send_admin_panel(ADMIN_ID)
    elif data == "admin_user_info":
        recs = list(purchases_col.find().sort("_id", -1).limit(15))
        txt = "👥 <b>Recent Purchases:</b>\n\n" + "".join(f"👤 {r.get('username')} | 📅 {r.get('date', '')[:10]} | 📚 <code>{r.get('item_info')}</code>\n" for r in recs) if recs else "No purchases yet."
        bot.edit_message_text(txt, chat_id=chat_id, message_id=msg_id, reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("🔙 Back", callback_data="back_to_admin")), parse_mode="HTML")
    elif data == "back_to_admin":
        try: bot.delete_message(chat_id, msg_id)
        except Exception: pass
        send_admin_panel(chat_id)
    elif data.startswith("mainmenu_"):
        t = data.replace("mainmenu_", "")
        if t.startswith("c_"):
            c = courses_col.find_one({"course_id": t})
            if c: send_course_to_user(chat_id, c)
        elif t.startswith("b_"):
            b = batches_col.find_one({"batch_id": t})
            if b: send_batch_to_user(chat_id, b)
    elif data == "bc_done":
        admin_data[ADMIN_ID]["step"], admin_data[ADMIN_ID]["buttons"] = "BC_BUTTONS", []
        bot.send_message(ADMIN_ID, "✅ <b>Media Saved!</b> Add button or Finish.", reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("🚀 Finish", callback_data="bc_finish")), parse_mode="HTML")
    elif data == "bc_finish":
        m_items, btns = admin_data[ADMIN_ID].get("media", []), admin_data[ADMIN_ID].get("buttons", [])
        m = InlineKeyboardMarkup()
        for b in btns: m.row(InlineKeyboardButton(b["text"], url=b["url"]))
        bot.send_message(ADMIN_ID, "⏳ Broadcasting started...")
        success = 0
        for u in users_col.find():
            uid = u["user_id"]
            try:
                if not m_items: continue
                if len(m_items) == 1:
                    it = m_items[0]
                    if it["type"] == "text": bot.send_message(uid, it["caption"], reply_markup=m, parse_mode="HTML")
                    elif it["type"] == "photo": bot.send_photo(uid, it["file_id"], caption=it["caption"], reply_markup=m, parse_mode="HTML")
                    elif it["type"] == "video": bot.send_video(uid, it["file_id"], caption=it["caption"], reply_markup=m, parse_mode="HTML")
                    elif it["type"] == "document": bot.send_document(uid, it["file_id"], caption=it["caption"], reply_markup=m, parse_mode="HTML")
                else:
                    m_group = [InputMediaPhoto(it["file_id"], caption=it["caption"], parse_mode="HTML") if it["type"] == "photo" else InputMediaVideo(it["file_id"], caption=it["caption"], parse_mode="HTML") if it["type"] == "video" else InputMediaDocument(it["file_id"], caption=it["caption"], parse_mode="HTML") for it in m_items]
                    sent = orig_send_media_group(uid, m_group)
                    for sg in sent: register_activity(uid, sg.message_id)
                    if btns or any(i["type"] == "text" for i in m_items): bot.send_message(uid, "👇", reply_markup=m, parse_mode="HTML")
                success += 1
            except Exception: pass
        bot.send_message(ADMIN_ID, f"✅ <b>Broadcast Complete!</b> ({success} users).", parse_mode="HTML")
        del admin_data[ADMIN_ID]
        send_admin_panel(ADMIN_ID)
    elif data == "ftl_done":
        admin_data[ADMIN_ID]["step"], admin_data[ADMIN_ID]["buttons"] = "FTL_BUTTONS", []
        bot.send_message(ADMIN_ID, "✅ <b>Media Saved!</b> Add button or Finish.", reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("🚀 Finish", callback_data="ftl_finish")), parse_mode="HTML")
    elif data == "ftl_finish":
        fid = "f_" + str(uuid.uuid4())[:6]
        file_links_col.update_one({"file_code": fid}, {"$set": {"file_code": fid, "media_data": admin_data[ADMIN_ID].get("media", []), "button_data": admin_data[ADMIN_ID].get("buttons", [])}}, upsert=True)
        bot.send_message(ADMIN_ID, f"🎉 <b>Link Created!</b>\n👉 <code>https://t.me/{bot.get_me().username}?start={fid}</code>", parse_mode="HTML")
        del admin_data[ADMIN_ID]
        send_admin_panel(ADMIN_ID)


# ==========================================
# 4. Flask Web Server & SMS Webhook (GET + POST)
# ==========================================
app = Flask(__name__)
AMOUNT_RE_DECIMAL = re.compile(r"(?:Rs\.?|₹|INR)\s?([\d,]+\.\d{2})", re.IGNORECASE)
AMOUNT_RE_INT = re.compile(r"(?:Rs\.?|₹|INR)\s?([\d,]+)(?!\.\d)", re.IGNORECASE)

@app.route("/")
def home():
    return "Telegram Bot API Running."

@app.route("/sms-webhook/<secret>", methods=["GET", "POST"])
def sms_webhook(secret):
    if secret != SMS_HOOK_SECRET: return "forbidden", 403
    sms_text = (request.get_json(silent=True) or request.form).get("text", "").strip() if request.method == "POST" else request.args.get("text", "").strip()
    if not sms_text: return "no 'text' param", 400

    m = AMOUNT_RE_DECIMAL.search(sms_text)
    has_dec = bool(m)
    if not m: m = AMOUNT_RE_INT.search(sms_text)
    if not m: return "no amount", 200

    amt_str = m.group(1).replace(",", "")
    f_round = f"{float(amt_str):.2f}" if not has_dec else amt_str

    sms_pool_col.insert_one({"amount": f_round, "raw_text": sms_text, "status": "UNUSED", "created_at_dt": datetime.now(timezone.utc), "created_at_str": get_ist_time()})

    order, amb = None, False
    with pending_lock:
        cands = [amt_str] if has_dec and amt_str in pending_orders else [f_round] if not has_dec and f_round in pending_orders else [k for k in pending_orders if not has_dec and k.startswith(amt_str + ".")]
        if len(cands) == 1: order = pending_orders.pop(cands[0])
        else: amb = len(cands) > 1

    if not order: order = orders_col.find_one({"amount": f_round, "status": "PENDING"})
    
    if order:
        sms_pool_col.update_one({"amount": f_round, "status": "UNUSED"}, {"$set": {"status": "PROCESSED"}})
        deliver_course_to_buyer(order, sms_text=sms_text, is_manual=False)
        return "matched", 200

    if amb:
        try: orig_send_message(DB_CHANNEL_ID, f"⚠️ <b>Ambiguous</b> ₹{amt_str}\n📩 <code>{sms_text[:300]}</code>", parse_mode="HTML")
        except Exception: pass
        return "ambiguous", 200
    return "saved_to_pool", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    app.run(host="0.0.0.0", port=port)
