# ==========================================
# DrDeals Premium – ANTI-SPAM EDITION 🛡️
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
import google.generativeai as genai
from telebot import types
from PIL import Image, ImageDraw
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# ==========================================
# ⚙️ בדיקה שהמפתח קיים בשרת
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
# ⚙️ הגדרות הבוט
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
# 🧠 המוח: בדיקת רלוונטיות קשוחה
# ==========================================
def is_relevant(user_query_en, product_title):
    """
    הפונקציה שמונעת זבל.
    אם חיפשתי 'Drone' והכותרת לא מכילה את המילה - זה עף.
    """
    q_words = user_query_en.lower().split()
    title_lower = product_title.lower()
    
    # בדיקה 1: מילים אסורות גלובליות (כבלים, ניירות, שקיות כביסה)
    spam_words = ["organizer", "cable winder", "disposable", "paper", "towel", "washing bag", "hook", "loop"]
    if any(s in title_lower for s in spam_words):
        return False

    # בדיקה 2: האם מילת המפתח קיימת?
    # לפחות מילה אחת משמעותית (מעל 3 אותיות) מהחיפוש חייבת להופיע בכותרת
    found_match = False
    for word in q_words:
        if len(word) > 2 and word in title_lower:
            found_match = True
            break
    
    return found_match

def analyze_with_ai(user_query, product_title, price):
    # אם יש AI, הוא יעשה עבודה טובה יותר בניסוח הכותרת
    if not HAS_AI:
        return {"valid": True, "title": product_title[:50]}

    prompt = f"""
    User searched: "{user_query}"
    Found Product: "{product_title}"
    
    Task:
    1. Check if product matches user intent. (If User wants 'Drone' and product is 'Cable' -> INVALID).
    2. Write a SHORT Hebrew title (max 7 words).
    
    Output JSON: {{"valid": true, "title": "..."}}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except:
        return {"valid": True, "title": product_title[:50]}

# ==========================================
# 🔧 תשתית אליאקספרס
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query):
    # שינוי קריטי: min_sale_price מוגדר ל-50 כדי לסנן את הכבלים ב-2 שקל
    params = {
        "app_key": APP_KEY, "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "format": "json",
        "sign_method": "md5", "v": "2.0", "partner_id": "top-autopilot",
        "keywords": query, "target_currency": "ILS", "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC", "page_size": "20", 
        "min_sale_price": "20" # חוסם את הזבל הזול
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
        final = link.get("promotion_short_link") or link.get("promotion_link")
        return final if final else clean
    except: return clean

def create_collage(urls):
    imgs = []
    for u in urls[:4]:
        try:
            img = Image.open(io.BytesIO(session.get(u, timeout=5).content)).resize((500,500))
            imgs.append(img)
        except: imgs.append(Image.new("RGB",(500,500),"white"))
    while len(imgs)<4: imgs.append(Image.new("RGB",(500,500),"white"))
    canvas = Image.new("RGB",(1000,1000),"white")
    canvas.paste(imgs[0],(0,0)); canvas.paste(imgs[1],(500,0))
    canvas.paste(imgs[2],(0,500)); canvas.paste(imgs[3],(500,500))
    out = io.BytesIO()
    canvas.save(out,"JPEG",quality=85); out.seek(0)
    return out

# ==========================================
# 🚀 בוט ראשי
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    if not m.text.startswith("חפש לי"): return
    query_he = m.text.replace("חפש לי","").strip()
    
    msg = bot.reply_to(m, f"🕵️‍♂️ בודק: '{query_he}'...\n🛡️ מפעיל מסנן ספאם (כדי לא להביא כבלים ומגבות)...")
    bot.send_chat_action(m.chat.id, "typing")

    # 1. תרגום (נסיון חכם)
    try:
        # אם יש AI, נשתמש בו לתרגום מדויק
        if HAS_AI:
            trans_prompt = f"Translate '{query_he}' to English for Shopping Search. Return ONLY the English words."
            query_en = model.generate_content(trans_prompt).text.strip()
        else:
            from deep_translator import GoogleTranslator
            query_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except: query_en = query_he

    print(f"DEBUG: Searching Query -> '{query_en}'")

    # 2. משיכת מוצרים
    raw_products = get_ali_products(query_en)
    
    # 3. סינון קשוח
    final_products = []
    
    for p in raw_products:
        if len(final_products) >= 4: break
        
        title = p["product_title"]
        
        # שלב א': שומר הסף (הבדיקה המכנית)
        # אם ביקשנו Drone ואין Drone בכותרת - זה עף מיד!
        if not is_relevant(query_en, title):
            print(f"🗑️ Junk Removed: {title[:20]}...")
            continue

        # שלב ב': AI (אם קיים)
        if HAS_AI:
            ai_result = analyze_with_ai(query_he, title, p["target_sale_price"])
            if not ai_result.get("valid"):
                continue
            p["display_title"] = ai_result.get("title")
        else:
            p["display_title"] = title[:50] # כותרת רגילה אם אין AI

        final_products.append(p)

    if not final_products:
        bot.edit_message_text(f"🛑 לא מצאתי תוצאות מדויקות ל-'{query_he}'.\n(העדפתי לא להציג כלום מאשר להציג מוצרים לא קשורים).", m.chat.id, msg.message_id)
        return

    # 4. הצגה
    bot.delete_message(m.chat.id, msg.message_id)
    
    images = []
    text = f"🤖 **הבחירות החכמות עבורך:**\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(final_products):
        price = p.get("target_sale_price")
        link = get_short_link(p.get("product_detail_url"))
        if not link: continue

        images.append(p.get("product_main_image_url"))
        
        text += f"{i+1}. 🥇 {p['display_title']}\n"
        text += f"💰 מחיר: {price}₪\n"
        text += f"{link}\n\n"
        
        kb.add(types.InlineKeyboardButton(f"🛍️ מוצר {i+1}", url=link))

    if images:
        try: bot.send_photo(m.chat.id, create_collage(images), caption=text, parse_mode="Markdown", reply_markup=kb)
        except: bot.send_message(m.chat.id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="Markdown", reply_markup=kb)

print("🚀 Anti-Spam Bot Running...")
bot.infinity_polling(timeout=10, long_polling_timeout=5)
