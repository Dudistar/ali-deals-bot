# ==========================================
# DrDeals Premium – STABILITY FIX (Based on Logs)
# ==========================================
import telebot
import requests
import time
import hashlib
import logging
import io
import sys
import os
import json
import html  # <--- קריטי למניעת הקריסה בלוגים
from telebot import types
from PIL import Image, ImageDraw, ImageFont
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from deep_translator import GoogleTranslator
import google.generativeai as genai

# ==========================================
# 👮 הגדרות מנהל
# ==========================================
ADMIN_ID = 173837076

# ==========================================
# 🔑 הגדרות AI (חייב להיות ב-Environment Variables)
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

HAS_AI = False
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        HAS_AI = True
        print("✅ AI Connected via Server Variables")
    except Exception as e:
        print(f"❌ AI Error: {e}")
else:
    print("⚠️ WARNING: No GEMINI_API_KEY found. Bot will run in 'Dumb Mode' (No filters).")

# ==========================================
# ⚙️ הגדרות בוט ואליאקספרס
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
bot = telebot.TeleBot(BOT_TOKEN)
session = requests.Session()
adapter = HTTPAdapter(max_retries=Retry(connect=3, backoff_factor=1))
session.mount('https://', adapter)

# ==========================================
# 🛡️ פונקציית ההגנה (התיקון לקריסה בלוג)
# ==========================================
def clean_text(text):
    """
    מנקה את הטקסט מתווים שגורמים לקריסה (Error 400).
    חובה להשתמש בזה בכל פעם ששולחים טקסט דינמי לטלגרם ב-HTML.
    """
    if not text: return ""
    return html.escape(str(text))

# ==========================================
# 🎨 מנוע גרפי (קולאז' 2x2 עם מספרים)
# ==========================================
def create_collage(urls):
    images = []
    for u in urls[:4]:
        try:
            resp = session.get(u, timeout=4)
            img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((500, 500))
            images.append(img)
        except:
            images.append(Image.new("RGB", (500, 500), "white"))
    
    while len(images) < 4:
        images.append(Image.new("RGB", (500, 500), "white"))

    canvas = Image.new("RGB", (1000, 1000), "white")
    positions = [(0, 0), (500, 0), (0, 500), (500, 500)]
    for i, pos in enumerate(positions):
        canvas.paste(images[i], pos)

    draw = ImageDraw.Draw(canvas)
    
    # נסיון לטעון פונט, אם אין - משתמש בברירת מחדל
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
    except:
        font = ImageFont.load_default()

    # מיקומים למספרים
    text_positions = [(30, 30), (530, 30), (30, 530), (530, 530)]
    
    for i, (x, y) in enumerate(text_positions):
        # ריבוע צהוב
        draw.rectangle([x, y, x+100, y+100], fill="#FFD700", outline="black", width=4)
        # מספר
        num = str(i + 1)
        # כיוונון מיקום הטקסט
        tx, ty = x + 30, y + 10
        if "default" in str(font): tx, ty = x + 40, y + 30
        draw.text((tx, ty), num, fill="black", font=font, font_size=60)

    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=95)
    out.seek(0)
    return out

# ==========================================
# 🧠 AI Logic
# ==========================================
def analyze_with_ai(user_query, product_title, price):
    if not HAS_AI:
        return {"valid": True, "title": product_title[:40], "desc": "מוצר פופולרי"}

    # פרומפט קצר וממוקד למהירות
    prompt = f"""
    Filter this AliExpress product.
    User wants: "{user_query}"
    Product: "{product_title}"
    Price: {price}
    
    1. RELEVANCE: Is it EXACTLY what user wants? (Accessory/Part = INVALID).
    2. HEBREW: Rewrite title (max 5 words) + Sales pitch (max 5 words).
    
    JSON format: {{"valid": true, "title": "...", "desc": "..."}}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except:
        return {"valid": True, "title": product_title[:40], "desc": "מוצר מומלץ"}

# ==========================================
# 🔧 אליאקספרס
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query):
    # הסרתי את min_sale_price כדי לא לפספס מציאות, ה-AI יסנן זבל
    params = {
        "app_key": APP_KEY, "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "format": "json",
        "sign_method": "md5", "v": "2.0", "partner_id": "top-autopilot",
        "keywords": query, "target_currency": "ILS", "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC", "page_size": "40"
    }
    params["sign"] = generate_sign(params)
    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        if "aliexpress_affiliate_product_query_response" not in data: return []
        products = data["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
        return products if isinstance(products, list) else [products]
    except: return []

def get_short_link(url):
    if not url: return None
    clean = url.split("?")[0]
    params = {
        "app_key": APP_KEY, "method": "aliexpress.affiliate.link.generate",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "format": "json",
        "sign_method": "md5", "v": "2.0", "partner_id": "top-autopilot",
        "promotion_link_type": "0", "source_values": clean, "tracking_id": TRACKING_ID
    }
    params["sign"] = generate_sign(params)
    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=5).json()
        link = r["aliexpress_affiliate_link_generate_response"]["resp_result"]["result"]["promotion_links"]["promotion_link"][0]
        return link.get("promotion_short_link") or link.get("promotion_link")
    except: return clean

# ==========================================
# 🚀 הבוט
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    if not m.text.startswith("חפש לי"): return
    query_he = m.text.replace("חפש לי","").strip()
    
    # שליחת הודעה למנהל (Spy)
    try:
        # שימוש ב-clean_text גם כאן כדי למנוע קריסה אם למשתמש יש שם מוזר
        user_info = f"{clean_text(m.from_user.first_name)} (@{clean_text(m.from_user.username)})"
        bot.send_message(ADMIN_ID, f"🔔 חיפוש: {clean_text(query_he)}\n👤 {user_info}")
    except: pass

    # הודעת סטטוס
    status_msg = bot.reply_to(m, f"🔎 מחפש: <b>{clean_text(query_he)}</b>...", parse_mode="HTML")
    bot.send_chat_action(m.chat.id, "upload_photo")

    # תרגום
    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except: query_en = query_he

    raw_products = get_ali_products(query_en)
    final_products = []
    
    # סינון
    for p in raw_products:
        if len(final_products) >= 4: break
        
        # דילוג על זבל מוחלט (בלי תמונה או מחיר)
        if not p.get("product_main_image_url") or not p.get("target_sale_price"):
            continue

        # AI
        ai_res = analyze_with_ai(query_he, p["product_title"], p["target_sale_price"])
        
        if ai_res.get("valid"):
            p["display_title"] = ai_res.get("title")
            p["display_desc"] = ai_res.get("desc")
            final_products.append(p)

    if not final_products:
        bot.delete_message(m.chat.id, status_msg.message_id)
        bot.send_message(m.chat.id, "😕 לא מצאתי תוצאות איכותיות.")
        return

    # קולאז'
    collage = create_collage([p.get("product_main_image_url") for p in final_products])

    # טקסט (עם הגנה מקריסות!)
    text = f"🛍️ <b>תוצאות עבור: {clean_text(query_he)}</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(final_products):
        link = get_short_link(p.get("product_detail_url"))
        price = p.get("target_sale_price")
        rating = p.get("evaluate_rate", "4.5")
        orders = p.get("last_volume", "100+")
        
        # שימוש ב-clean_text כדי למנוע את Error 400
        safe_title = clean_text(p['display_title'])
        safe_desc = clean_text(p['display_desc'])

        text += f"<b>{i+1}. {safe_title}</b>\n"
        text += f"ℹ️ <i>{safe_desc}</i>\n"
        text += f"💰 {price}₪  |  ⭐ {rating}  |  🛒 {orders}\n"
        text += f"🔗 {link}\n\n" # קישור גולמי

        kb.add(types.InlineKeyboardButton(f"🛒 קנה מוצר {i+1}", url=link))

    bot.delete_message(m.chat.id, status_msg.message_id)
    try:
        # שליחה ב-HTML עם הגנות
        bot.send_photo(m.chat.id, collage, caption=text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        bot.send_message(m.chat.id, f"שגיאה בשליחה: {e}")

print("🚀 Bot Started (Log Fixes Applied)")
bot.infinity_polling(timeout=25, long_polling_timeout=10)
