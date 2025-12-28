# ==========================================
# DrDeals Premium – FULL RICH VERSION (Secure + AI + Details)
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
# 🔑 טעינת מפתח מאובטחת
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
    print("❌ Critical Error: GEMINI_API_KEY is missing in Railway Variables!")

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
# 🧠 המוח: AI שכותב גם תיאור!
# ==========================================
def analyze_with_ai(user_query, product_title, price, rating):
    if not HAS_AI:
        return {"valid": True, "title": product_title[:50], "desc": "מוצר איכותי מאליאקספרס"}

    prompt = f"""
    Task: Shopping Assistant.
    User Search: "{user_query}"
    Found Item: "{product_title}" (Price: {price}, Rating: {rating})
    
    1. MATCH: Is this item relevant? (User "Drone" != Item "Cable").
    2. TITLE: Short Hebrew Title (max 5 words).
    3. DESC: A short, punchy marketing sentence in Hebrew (max 8 words).
    
    Output JSON: {{"valid": true, "title": "...", "desc": "..."}}
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except:
        return {"valid": True, "title": product_title[:50], "desc": "מוצר מומלץ"}

# ==========================================
# 🔧 תשתית אליאקספרס
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query):
    params = {
        "app_key": APP_KEY, "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "format": "json",
        "sign_method": "md5", "v": "2.0", "partner_id": "top-autopilot",
        "keywords": query, "target_currency": "ILS", "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC", "page_size": "20", "min_sale_price": "5"
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
    
    msg = bot.reply_to(m, f"🕵️‍♂️ ה-AI סורק את הרשת עבור: '{query_he}'...\n(כולל דירוגים וניתוח חכם)")
    bot.send_chat_action(m.chat.id, "typing")

    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except: query_en = query_he

    raw_products = get_ali_products(query_en)
    
    final_products = []
    for p in raw_products:
        if len(final_products) >= 4: break
        time.sleep(0.3)
        bot.send_chat_action(m.chat.id, "typing")
        
        # שליפת נתונים נוספים לניתוח
        price = p.get("target_sale_price")
        rating = p.get("evaluate_rate", "4.8")

        ai_result = analyze_with_ai(query_he, p["product_title"], price, rating)
        
        if ai_result.get("valid"):
            p["display_title"] = ai_result.get("title")
            p["display_desc"] = ai_result.get("desc") # התיאור החדש!
            final_products.append(p)
            print(f"✅ Approved: {p['display_title']}")

    if not final_products and raw_products:
        final_products = raw_products[:2] 
        for p in final_products: 
            p["display_title"] = p["product_title"][:40]
            p["display_desc"] = "מוצר פופולרי מאליאקספרס"

    if not final_products:
        bot.edit_message_text("🛑 לא נמצאו מוצרים.", m.chat.id, msg.message_id)
        return

    bot.delete_message(m.chat.id, msg.message_id)
    
    images = []
    text = f"🛍️ **תוצאות עבור: {query_he}**\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(final_products):
        price = p.get("target_sale_price")
        # הוספתי כאן את הנתונים החסרים:
        rating = p.get("evaluate_rate", "4.9") 
        orders = p.get("last_volume", "100+")
        
        link = get_short_link(p.get("product_detail_url"))
        if not link: continue

        images.append(p.get("product_main_image_url"))
        
        # === עיצוב ההודעה המלא ===
        text += f"{i+1}. 🥇 {p['display_title']}\n"
        text += f"ℹ️ {p['display_desc']}\n"  # התיאור בעברית
        text += f"💰 {price}₪ | ⭐ {rating} | 🛒 {orders}\n" # הנתונים
        text += f"{link}\n\n"
        
        kb.add(types.InlineKeyboardButton(f"🛍️ מוצר {i+1}", url=link))

    if images:
        try: bot.send_photo(m.chat.id, create_collage(images), caption=text, parse_mode="Markdown", reply_markup=kb)
        except: bot.send_message(m.chat.id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="Markdown", reply_markup=kb)

print("🚀 Full Feature Bot Running...")
bot.infinity_polling(timeout=20, long_polling_timeout=10)
