# ==========================================
# DrDeals Premium – PRODUCTION VERSION (AI Powered)
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
from deep_translator import GoogleTranslator

# ==========================================
# 🔑 ניהול מפתח חכם (גיבוי כפול)
# ==========================================
# 1. מנסה לקחת מהשרת
KEY = os.environ.get("GEMINI_API_KEY")

# 2. אם אין בשרת, משתמש במפתח שסיפקת כגיבוי קשיח
if not KEY:
    KEY = "AIzaSyBzR-46-B13sdh1UIPVM2hOJDjIR_8ZQ-4"

try:
    genai.configure(api_key=KEY)
    model = genai.GenerativeModel('gemini-pro')
    HAS_AI = True
    print("✅ AI Connected Successfully!")
except Exception as e:
    print(f"⚠️ AI Error: {e}")
    HAS_AI = False

# ==========================================
# ⚙️ הגדרות
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
# 🧠 המוח: ניתוח מוצר (בלי רשימות חסימה!)
# ==========================================
def analyze_product(user_query, product_title, price):
    """
    שולח ל-AI כדי להחליט אם המוצר מתאים ולכתוב כותרת.
    """
    if not HAS_AI:
        return {"valid": True, "title": product_title[:50]}

    prompt = f"""
    Acting as a shopping assistant.
    User Search: "{user_query}"
    Found Product: "{product_title}"
    Price: {price} ILS.
    
    Task:
    1. RELEVANCE CHECK: Is the product logicallly related?
       - Search: "T-Shirt for men". Product: "Cotton Summer Tee" -> VALID.
       - Search: "T-Shirt". Product: "Plastic Hanger" -> INVALID.
    2. WRITING: If valid, write a clean Hebrew title (max 6 words).
    
    Output JSON: {{"valid": true, "title": "..."}}
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except:
        # במקרה של שגיאה ב-AI, ברירת המחדל היא לאשר (כדי לא להחזיר ריק)
        return {"valid": True, "title": product_title[:50]}

# ==========================================
# 🔧 תשתית אליאקספרס
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query):
    # מחיר מינימום נמוך (5 ש"ח) כדי לא לפספס חולצות זולות
    params = {
        "app_key": APP_KEY, "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "format": "json",
        "sign_method": "md5", "v": "2.0", "partner_id": "top-autopilot",
        "keywords": query, "target_currency": "ILS", "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC", "page_size": "15", "min_sale_price": "5"
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
    
    # שלב 1: חיווי
    msg = bot.reply_to(m, f"🤖 ה-AI מנתח בקשה: '{query_he}'...\n🛡️ סורק את המאגר (נא להמתין)...")
    bot.send_chat_action(m.chat.id, "typing")

    # תרגום לחיפוש (לא חובה AI לזה, גוגל מספיק טוב ומהיר יותר לשלב הזה)
    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except: query_en = query_he

    print(f"Searching: {query_en}")

    # שלב 2: משיכה גולמית
    raw_products = get_ali_products(query_en)
    
    # שלב 3: סינון AI חכם
    final_products = []
    
    for p in raw_products:
        if len(final_products) >= 4: break
        
        # השהייה קטנטנה למניעת עומס
        time.sleep(0.3)
        bot.send_chat_action(m.chat.id, "typing")
        
        # בדיקת AI
        ai_result = analyze_product(query_he, p["product_title"], p["target_sale_price"])
        
        if ai_result.get("valid"):
            p["display_title"] = ai_result.get("title")
            final_products.append(p)
            print(f"✅ Approved: {p['display_title']}")

    # מנגנון חירום: אם ה-AI סינן הכל (נדיר), נחזיר את ה-2 הכי רלוונטיים כדי לא להחזיר ריק
    if not final_products and raw_products:
        final_products = raw_products[:2]
        for p in final_products: p["display_title"] = p["product_title"][:50]

    if not final_products:
        bot.edit_message_text("🛑 לא נמצאו מוצרים תואמים במאגר.", m.chat.id, msg.message_id)
        return

    # שלב 4: הצגה
    bot.delete_message(m.chat.id, msg.message_id)
    
    images = []
    text = f"🤖 **תוצאות AI עבור: {query_he}**\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(final_products):
        price = p.get("target_sale_price")
        # השגת לינק מקוצר
        link = get_short_link(p.get("product_detail_url"))
        if not link: continue

        images.append(p.get("product_main_image_url"))
        
        text += f"{i+1}. 🥇 {p['display_title']}\n"
        text += f"💰 מחיר: {price}₪\n"
        text += f"{link}\n\n" # הקישור פתוח וברור
        
        kb.add(types.InlineKeyboardButton(f"🛍️ מוצר {i+1}", url=link))

    if images:
        try: bot.send_photo(m.chat.id, create_collage(images), caption=text, parse_mode="Markdown", reply_markup=kb)
        except: bot.send_message(m.chat.id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="Markdown", reply_markup=kb)

print("🚀 Bot Running (Final Production Version)...")
bot.infinity_polling(timeout=20, long_polling_timeout=10)
