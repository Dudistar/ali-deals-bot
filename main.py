# ==========================================
# DrDeals Premium – "THE CLONE" (Option A)
# ==========================================
# 🏆 גירסת הפנתאון: קולאז' תמונות, מספרים צהובים, AI חכם, ומלשינון.

import telebot
import requests
import time
import hashlib
import logging
import io
import sys
import os
import json
import random
from telebot import types
from PIL import Image, ImageDraw, ImageFont # המנוע הגרפי
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from deep_translator import GoogleTranslator
import google.generativeai as genai

# ==========================================
# 👮 הגדרות הבלש (מי מקבל דיווחים?)
# ==========================================
ADMIN_ID = 173837076

# ==========================================
# 🔑 טעינת מפתח AI (מאובטח)
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

HAS_AI = False
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        HAS_AI = True
        print("✅ AI Connected via Server Variables!")
    except Exception as e:
        print(f"⚠️ AI Connection Error: {e}")
else:
    print("❌ CRITICAL: GEMINI_API_KEY missing in Railway!")

# ==========================================
# ⚙️ הגדרות אליאקספרס ובוט
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
bot = telebot.TeleBot(BOT_TOKEN)

# חיבור אינטרנט יציב
session = requests.Session()
adapter = HTTPAdapter(max_retries=Retry(connect=3, read=3, redirect=3, backoff_factor=1))
session.mount('https://', adapter)

# ==========================================
# 🎨 המנוע הגרפי (יצירת הקולאז' עם המספרים)
# ==========================================
def get_font():
    """מנסה לטעון פונט נורמלי מהשרת כדי שהמספרים יהיו יפים"""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf"
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, 60) # גודל פונט 60
        except:
            continue
    return ImageFont.load_default() # ברירת מחדל אם לא מצא כלום

def create_collage_with_numbers(urls):
    """יוצר תמונה אחת מ-4 תמונות ומוסיף עיגולים צהובים עם מספרים"""
    images = []
    # הורדת התמונות
    for u in urls[:4]:
        try:
            resp = session.get(u, timeout=4)
            img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((500, 500))
            images.append(img)
        except:
            # במקרה של תקלה - ריבוע לבן
            images.append(Image.new("RGB", (500, 500), "white"))
    
    # השלמה ל-4 אם חסר
    while len(images) < 4:
        images.append(Image.new("RGB", (500, 500), "white"))

    # יצירת הקנבס (1000x1000)
    canvas = Image.new("RGB", (1000, 1000), "white")
    canvas.paste(images[0], (0, 0))
    canvas.paste(images[1], (500, 0))
    canvas.paste(images[2], (0, 500))
    canvas.paste(images[3], (500, 500))

    # ציור המספרים
    draw = ImageDraw.Draw(canvas)
    font = get_font()
    
    # מיקומים של העיגולים (צד שמאל למעלה של כל תמונה)
    # פורמט: (x, y) של הפינה השמאלית העליונה של הריבוע
    positions = [(20, 20), (520, 20), (20, 520), (520, 520)]
    
    for i, (x, y) in enumerate(positions):
        # ציור עיגול צהוב
        box = [x, y, x+80, y+80] # גודל העיגול
        draw.ellipse(box, fill="#FFD700", outline="black", width=3)
        
        # כתיבת המספר (ממורכז)
        num_str = str(i + 1)
        
        # חישוב מרכז בערך (תלוי בפונט, כאן זה קירוב טוב)
        text_x = x + 25
        text_y = y + 10
        if "DejaVu" in str(font): # כיוונון עדין לפונט של לינוקס
             text_x = x + 22
             text_y = y + 5

        draw.text((text_x, text_y), num_str, fill="black", font=font)

    # שמירה לזיכרון
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=90)
    out.seek(0)
    return out

# ==========================================
# 🧠 המוח (AI + HTML Cleaner)
# ==========================================
def escape_html(text):
    if not text: return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def analyze_with_ai(user_query, product_title, price, rating):
    """בודק אם המוצר איכותי וכותב כותרת מחדש"""
    if not HAS_AI:
        return {"valid": True, "title": product_title[:40], "desc": "מוצר פופולרי"}

    prompt = f"""
    Role: Senior eCommerce Buyer.
    Task: Filter & Rename AliExpress Product.
    
    User Query (Hebrew): "{user_query}"
    Product Title (English/Gibberish): "{product_title}"
    Price: {price} ILS, Rating: {rating}
    
    Rules:
    1. STRICT FILTER: If product is irrelevant (e.g. user wants "Drone" and this is "Propeller"), set valid=false.
    2. REWRITE: Write a CLEAN, ATTRACTIVE Hebrew title (max 5-6 words). Do not translate - Rewrite!
    3. PITCH: Write a 4-5 word marketing hook in Hebrew.
    
    Output JSON: {{"valid": true, "title": "רחפן מקצועי 4K", "desc": "צילום יציב ואיכותי"}}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except:
        return {"valid": True, "title": product_title[:40], "desc": "מוצר מומלץ"}

# ==========================================
# 🔧 תשתית אליאקספרס
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query):
    # מחיר מינימום 10 ש"ח כדי לסנן זבל מוחלט
    params = {
        "app_key": APP_KEY, "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "format": "json",
        "sign_method": "md5", "v": "2.0", "partner_id": "top-autopilot",
        "keywords": query, "target_currency": "ILS", "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC", "page_size": "20", "min_sale_price": "10"
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
# 🚀 הבוט הראשי
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    if not m.text.startswith("חפש לי"): return
    query_he = m.text.replace("חפש לי","").strip()
    
    # === 1. מלשינון (Spy) ===
    try:
        user = m.from_user
        info = f"👤 <b>משתמש:</b> {user.first_name}\n🔍 <b>חיפש:</b> {query_he}"
        bot.send_message(ADMIN_ID, f"🕵️‍♂️ <b>התראה חדשה!</b>\n{info}", parse_mode="HTML")
    except: pass

    # === 2. חיווי התחלתי ===
    status_msg = bot.reply_to(m, f"🔎 מחפש את הטובים ביותר עבור: <b>{escape_html(query_he)}</b>...", parse_mode="HTML")
    bot.send_chat_action(m.chat.id, "upload_photo") # משדר "מעלה תמונה" כדי לקנות זמן

    # תרגום
    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except: query_en = query_he

    # === 3. משיכה וסינון ===
    raw_products = get_ali_products(query_en)
    final_products = []
    
    # לולאת סינון חכמה
    for p in raw_products:
        if len(final_products) >= 4: break
        
        # בדיקת איכות מהירה לפני AI
        try:
            rating = float(p.get("evaluate_rate", "0"))
            if rating < 4.0: continue # סינון מוצרים גרועים
        except: pass

        # שליחה ל-AI
        price = p.get("target_sale_price")
        ai_result = analyze_with_ai(query_he, p["product_title"], price, p.get("evaluate_rate", "4.5"))
        
        if ai_result.get("valid"):
            p["display_title"] = ai_result.get("title")
            p["display_desc"] = ai_result.get("desc")
            final_products.append(p)
            print(f"✅ AI Approved: {p['display_title']}")
        else:
            print(f"🗑️ AI Rejected: {p['product_title'][:20]}")

    # אם לא מצאנו כלום
    if not final_products:
        bot.delete_message(m.chat.id, status_msg.message_id)
        bot.send_message(m.chat.id, "🤔 לא מצאתי מוצרים שעומדים בסטנדרט האיכות.\nנסה לשנות את מילות החיפוש.")
        return

    # === 4. יצירת הקולאז' (The Magic) ===
    image_urls = [p.get("product_main_image_url") for p in final_products]
    collage_bytes = create_collage_with_numbers(image_urls)

    # === 5. בניית הטקסט והכפתורים ===
    text = f"🛍️ <b>תוצאות עבור: {escape_html(query_he)}</b>\n\n"
    kb = types.InlineKeyboardMarkup()
    
    for i, p in enumerate(final_products):
        price = p.get("target_sale_price")
        rating = p.get("evaluate_rate", "4.8")
        orders = p.get("last_volume", "100+")
        link = get_short_link(p.get("product_detail_url"))
        
        if not link: continue # לא אמור לקרות
        
        # בניית שורה בטקסט
        # פורמט: 1. כותרת (מודגש) -> תיאור (נטוי) -> נתונים
        title = escape_html(str(p['display_title']))
        desc = escape_html(str(p['display_desc']))
        
        text += f"<b>{i+1}. {title}</b>\n"
        text += f"ℹ️ <i>{desc}</i>\n"
        text += f"💰 {price}₪  |  ⭐ {rating}  |  🛒 {orders}\n"
        text += f"🔗 <a href='{link}'>לרכישה לחץ כאן</a>\n\n"
        
        # כפתור
        btn_text = f"🛒 מוצר {i+1} - {price}₪"
        kb.add(types.InlineKeyboardButton(btn_text, url=link))

    # === 6. שליחה ===
    bot.delete_message(m.chat.id, status_msg.message_id)
    try:
        bot.send_photo(
            m.chat.id, 
            collage_bytes, 
            caption=text, 
            parse_mode="HTML", 
            reply_markup=kb
        )
    except Exception as e:
        print(f"Send Error: {e}")
        bot.send_message(m.chat.id, "שגיאה בשליחת התמונה, נסה שוב.")

print("🚀 DrDeals 'The Clone' is Live on Railway...")
bot.infinity_polling(timeout=25, long_polling_timeout=10)
