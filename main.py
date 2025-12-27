import telebot
import requests
import time
import os
import io
import hashlib
import logging
from telebot import types
from PIL import Image, ImageDraw
from deep_translator import GoogleTranslator

# ==========================================
# ⚙️ הגדרות
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

logging.basicConfig(level=logging.INFO)
bot = telebot.TeleBot(BOT_TOKEN)
session = requests.Session()

# ==========================================
# 🧠 מיפוי קטגוריות קשיח
# ==========================================
CATEGORY_FORCE = {
    "מעיל": {
        "category_id": "200001901",  # Women's Coats
        "must_words": ["coat", "jacket", "trench", "winter"],
        "blacklist": [
            "aluminum", "metal", "jaw", "clamp", "tool",
            "protector", "guard", "industrial", "machinery",
            "mount", "bracket", "cover", "frame"
        ]
    }
}

# ==========================================
# 🔐 חתימה
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

# ==========================================
# 🌍 תרגום
# ==========================================
def to_en(text):
    return GoogleTranslator(source='auto', target='en').translate(text)

def to_he(text):
    return GoogleTranslator(source='auto', target='iw').translate(text)

# ==========================================
# 🎯 חיפוש AliExpress
# ==========================================
def search_ali(query_en, category_id):
    params = {
        "app_key": APP_KEY,
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "sign_method": "md5",
        "method": "aliexpress.affiliate.product.query",
        "partner_id": "top-autopilot",
        "format": "json",
        "v": "2.0",
        "keywords": query_en,
        "category_ids": category_id,
        "target_currency": "ILS",
        "ship_to_country": "IL",
        "page_size": "50",
        "sort": "LAST_VOLUME_DESC"
    }
    params["sign"] = generate_sign(params)

    r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
    data = r.json()
    products = data.get(
        "aliexpress_affiliate_product_query_response", {}
    ).get("resp_result", {}).get("result", {}).get("products", {}).get("product", [])

    if isinstance(products, dict):
        products = [products]

    return products

# ==========================================
# 🛑 פילטר קטלני (העיקר!)
# ==========================================
def strict_filter(products, rules):
    final = []

    for p in products:
        title = p.get("product_title", "").lower()

        # ❌ blacklist
        if any(bad in title for bad in rules["blacklist"]):
            continue

        # ✅ חייב להכיל מילה רלוונטית
        if not any(good in title for good in rules["must_words"]):
            continue

        final.append(p)

    return final[:3]

# ==========================================
# 🔗 קיצור קישור
# ==========================================
def short_link(url):
    clean = url.split("?")[0]
    params = {
        "app_key": APP_KEY,
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "sign_method": "md5",
        "method": "aliexpress.affiliate.link.generate",
        "partner_id": "top-autopilot",
        "format": "json",
        "v": "2.0",
        "promotion_link_type": "0",
        "source_values": clean,
        "tracking_id": TRACKING_ID
    }
    params["sign"] = generate_sign(params)

    r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=5).json()
    res = r.get("aliexpress_affiliate_link_generate_response", {}) \
           .get("resp_result", {}).get("result", {}) \
           .get("promotion_links", {}).get("promotion_link", [])

    if res:
        return res[0].get("promotion_short_link")

    return clean

# ==========================================
# 🖼️ קולאז'
# ==========================================
def collage(imgs):
    images = []
    for url in imgs:
        try:
            img = Image.open(io.BytesIO(session.get(url).content)).resize((500, 500))
            images.append(img)
        except:
            images.append(Image.new("RGB", (500, 500), "white"))

    base = Image.new("RGB", (1000, 1000), "white")
    pos = [(0,0),(500,0),(0,500)]
    draw = ImageDraw.Draw(base)

    for i, img in enumerate(images):
        base.paste(img, pos[i])
        draw.ellipse((pos[i][0]+20, pos[i][1]+20, pos[i][0]+80, pos[i][1]+80), fill="#FFD700")
        draw.text((pos[i][0]+40, pos[i][1]+30), str(i+1), fill="black")

    out = io.BytesIO()
    base.save(out, format="JPEG")
    out.seek(0)
    return out

# ==========================================
# 🤖 בוט
# ==========================================
@bot.message_handler(func=lambda m: True)
def handle(m):
    if not m.text.startswith("חפש לי"):
        bot.reply_to(m, "כתוב: חפש לי מעיל אלגנטי...")
        return

    query_he = m.text.replace("חפש לי", "").strip()
    rule = CATEGORY_FORCE.get("מעיל")

    query_en = to_en(query_he)
    products = search_ali(query_en, rule["category_id"])
    final = strict_filter(products, rule)

    if not final:
        bot.send_message(m.chat.id, "❌ לא נמצא מעיל אמיתי. סיננתי הכל בכוונה.")
        return

    imgs = [p["product_main_image_url"] for p in final]
    bot.send_photo(m.chat.id, collage(imgs), caption=f"🏆 הבחירות עבור: {query_he}")

    text = ""
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(final):
        title = to_he(p["product_title"])[:60]
        price = p.get("target_sale_price", "?")
        link = short_link(p["product_detail_url"])
        text += f"{i+1}. {title}\n💰 {price}₪\n🔗 {link}\n\n"
        kb.add(types.InlineKeyboardButton(f"🛒 מוצר {i+1}", url=link))

    bot.send_message(m.chat.id, text, reply_markup=kb, disable_web_page_preview=True)

bot.infinity_polling()
