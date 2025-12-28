# ==========================================
# DrDeals Premium – UNLIMITED EDITION
# ==========================================
# ✅ ללא הגבלת מחיר (זול זה טוב!)
# ✅ עיצוב מספרים מקצועי (עיגולים צהובים)
# ✅ ללא רשימות שחורות (AI חכם בלבד)

import telebot
import requests
import time
import hashlib
import logging
import io
import sys
import os
import json
from telebot import types
from PIL import Image, ImageDraw, ImageFont
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from deep_translator import GoogleTranslator
import google.generativeai as genai

# ==========================================
# 👮 הגדרות הבלש
# ==========================================
ADMIN_ID = 173837076

# ==========================================
# 🔑 הגדרות AI
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
HAS_AI = False
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        HAS_AI = True
        print("✅ AI Connected!")
    except: pass

# ==========================================
# ⚙️ הגדרות בוט
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
# 🎨 מנוע גרפי: המספרים היפים (עיגולים)
# ==========================================
def create_collage_with_numbers(urls):
    images = []
    # הורדת תמונות
    for u in urls[:4]:
        try:
            resp = session.get(u, timeout=4)
            img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((500, 500))
            images.append(img)
        except:
            images.append(Image.new("RGB", (500, 500), "white"))
    
    while len(images) < 4:
        images.append(Image.new("RGB", (500, 500), "white"))

    # יצירת קנבס
    canvas = Image.new("RGB", (1000, 1000), "white")
    canvas.paste(images[0], (0, 0))
    canvas.paste(images[1], (500, 0))
    canvas.paste(images[2], (0, 500))
    canvas.paste(images[3], (500, 500))

    draw = ImageDraw.Draw(canvas)
    
    # נסיון טעינת פונט עבה וברור
    font = ImageFont.load_default()
    try:
        # נסיון למצוא פונט מודגש בשרת לינוקס
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
    except:
        pass

    # מיקומים של העיגולים
    positions = [(30, 30), (530, 30), (30, 530), (530, 530)]
    
    for i, (x, y) in enumerate(positions):
        # 1. עיגול צהוב (במקום ריבוע)
        # זה העיצוב שאהבת בקודים הישנים
        draw.ellipse([x, y, x+80, y+80], fill="#FFD700", outline="black", width=3)
        
        # 2. המספר במרכז
        num_str = str(i + 1)
        
        # חישוב מרכז בסיסי
        text_x = x + 25
        text_y = y + 10
        
        # התאמה לפונט ברירת מחדל אם אין פונט יפה
        if font.getname()[0] == "DejaVu Sans":
             text_x = x + 23
             text_y = y + 5
        
        draw.text((text_x, text_y), num_str, fill="black", font=font, font_size=50)

    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=95)
    out.seek(0)
    return out

# ==========================================
# 🧠 AI ללא רשימות שחורות
# ==========================================
def analyze_with_ai(user_query, product_title, price):
    if not HAS_AI:
        # אם אין AI, מאשרים הכל (כדי לא לחסום מוצרים זולים)
        return {"valid": True, "title": product_title[:40], "desc": "מוצר פופולרי"}

    prompt = f"""
    Role: eCommerce Filter.
    User Search: "{user_query}"
    Item Found: "{product_title}"
    Price: {price}
    
    INSTRUCTIONS:
    1. RELEVANCE ONLY: Check if the Item matches the User Search.
       - If User wants "Drone" and Item is "Drone Battery" -> INVALID (False).
       - If User wants "Pen" and Item is "Pen" (Price 1$) -> VALID (True).
       - Do NOT filter by price. Cheap is OK.
    
    2. HEBREW:
       - Title: Simple Hebrew name (max 5 words).
       - Desc: Short marketing text (max 6 words).
    
    Output JSON: {{"valid": true, "title": "...", "desc": "..."}}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except:
        return {"valid": True, "title": product_title[:40], "desc": "מוצר מומלץ"}

# ==========================================
# 🔧 תשתית (ללא הגבלת מחיר!)
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query):
    # הסרתי את min_sale_price לחלוטין!
    params = {
        "app_key": APP_KEY, "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "format": "json",
        "sign_method": "md5", "v": "2.0", "partner_id": "top-autopilot",
        "keywords": query, "target_currency": "ILS", "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC", "page_size": "25" # מושך יותר כדי שיהיה ממה לסנן
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
# 🚀 בוט ראשי
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    if not m.text.startswith("חפש לי"): return
    query_he = m.text.replace("חפש לי","").strip()
    
    # 1. מלשינון
    try:
        first = m.from_user.first_name or ""
        user_name = f"@{m.from_user.username}" if m.from_user.username else ""
        bot.send_message(ADMIN_ID, f"🔔 <b>חיפוש:</b> {query_he}\n👤 {first} {user_name}", parse_mode="HTML")
    except: pass

    status_msg = bot.reply_to(m, f"🔎 מחפש: <b>{query_he}</b>...", parse_mode="HTML")
    bot.send_chat_action(m.chat.id, "upload_photo")

    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except: query_en = query_he

    # 2. חיפוש ללא הגבלות
    raw_products = get_ali_products(query_en)
    final_products = []
    
    # 3. סינון AI (על רלוונטיות בלבד)
    for p in raw_products:
        if len(final_products) >= 4: break
        
        # שליחה ל-AI לאישור
        ai_res = analyze_with_ai(query_he, p["product_title"], p["target_sale_price"])
        
        if ai_res.get("valid"):
            p["display_title"] = ai_res.get("title")
            p["display_desc"] = ai_res.get("desc")
            final_products.append(p)

    if not final_products:
        bot.delete_message(m.chat.id, status_msg.message_id)
        bot.send_message(m.chat.id, "לא נמצאו מוצרים תואמים.")
        return

    # 4. יצירת קולאז' (מספרים יפים)
    collage = create_collage_with_numbers([p.get("product_main_image_url") for p in final_products])

    # 5. טקסט ותוצאות
    text = f"🛍️ <b>תוצאות עבור: {query_he}</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(final_products):
        link = get_short_link(p.get("product_detail_url"))
        price = p.get("target_sale_price")
        rating = p.get("evaluate_rate", "4.5")
        orders = p.get("last_volume", "100+")
        
        title = p['display_title']
        desc = p['display_desc']

        # טקסט נקי עם לינק גולמי
        text += f"<b>{i+1}. {title}</b>\n"
        text += f"ℹ️ {desc}\n"
        text += f"💰 {price}₪  |  ⭐ {rating}  |  🛒 {orders}\n"
        text += f"{link}\n\n" # הקישור הגולמי

        kb.add(types.InlineKeyboardButton(f"🛒 קנה מוצר {i+1}", url=link))

    bot.delete_message(m.chat.id, status_msg.message_id)
    try:
        bot.send_photo(m.chat.id, collage, caption=text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        bot.send_message(m.chat.id, "שגיאה בשליחת התמונה.")
        print(e)

print("🚀 Bot Unlimited is Running...")
bot.infinity_polling(timeout=25, long_polling_timeout=10)
