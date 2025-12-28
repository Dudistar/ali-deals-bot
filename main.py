# ==========================================
# DrDeals Premium – TRUE AI LOGIC (Gemini Powered)
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

if not GEMINI_API_KEY:
    # הגנה למקרה ששכחת לשים את המשתנה ב-Railway
    print("❌ שגיאה: לא נמצא מפתח GEMINI_API_KEY בהגדרות ה-Variables ב-Railway!")
    HAS_AI = False
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        HAS_AI = True
        print("✅ מנוע בינה מלאכותית (Gemini) מחובר בהצלחה!")
    except Exception as e:
        print(f"⚠️ שגיאה בחיבור ל-AI: {e}")
        HAS_AI = False

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
# 🧠 המוח: פונקציית ה-AI
# ==========================================
def analyze_with_ai(user_query, product_title, price):
    """
    שולח את המוצר למוח של גוגל לקבלת אישור וכותרת.
    """
    if not HAS_AI:
        # גיבוי למקרה חירום (אם ה-AI נופל)
        return {"valid": True, "title": product_title[:50]}

    prompt = f"""
    Role: Professional Shopping Assistant.
    User Search (Hebrew): "{user_query}"
    Found Product (AliExpress): "{product_title}"
    Price: {price} ILS.

    Task:
    1. FILTER: Is this product EXACTLY what the user wants?
       - If user wants "Drone" and this is "Propeller" -> INVALID.
       - If user wants "Coat" and this is "Hanger" -> INVALID.
    2. TITLE: If Valid, write a SHORT, ATTRACTIVE Hebrew title (max 7-8 words).
       - No "New 2024", No "Free Shipping". Just the product name.

    Output JSON Only:
    {{"valid": true, "title": "רחפן מקצועי 4K עם מצלמה כפולה 🚁"}}
    OR
    {{"valid": false, "title": ""}}
    """
    
    try:
        response = model.generate_content(prompt)
        # ניקוי פורמט התשובה
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        print(f"AI Processing Error: {e}")
        # במקרה של שגיאה ב-AI, נעביר את המוצר בכל זאת כדי לא לתקוע
        return {"valid": True, "title": product_title[:50]}

# ==========================================
# 🔧 פונקציות תשתית (אליאקספרס)
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query):
    # כאן אנחנו בכוונה לא מסננים חזק, משאירים עבודה ל-AI
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
    
    draw = ImageDraw.Draw(canvas)
    for i, (x,y) in enumerate([(30,30), (530,30), (30,530), (530,530)]):
        draw.ellipse((x,y,x+70,y+70),fill="#FFD700",outline="black",width=3)
        draw.text((x+25,y+15),str(i+1),fill="black", font_size=40)
    
    out = io.BytesIO()
    canvas.save(out,"JPEG",quality=85); out.seek(0)
    return out

# ==========================================
# 🚀 הבוט (עם לוגיקה חכמה)
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    if not m.text.startswith("חפש לי"): return
    query_he = m.text.replace("חפש לי","").strip()
    
    # שלב 1: חיווי למשתמש
    msg = bot.reply_to(m, f"🧠 ה-AI מנתח את הבקשה: '{query_he}'...\n⏳ _סורק ומסנן מוצרים בזמן אמת (זה ייקח כ-10 שניות)..._")
    bot.send_chat_action(m.chat.id, "typing")

    # 2. תרגום לאנגלית עבור אליאקספרס
    try:
        # נשתמש ב-AI גם לתרגום כדי להבין הקשר (למשל: עכבר למחשב vs עכבר חיה)
        if HAS_AI:
            trans_prompt = f"Translate '{query_he}' to English for Shopping Search. Return ONLY the English words."
            query_en = model.generate_content(trans_prompt).text.strip()
        else:
            # גיבוי אם ה-AI לא עובד
            from deep_translator import GoogleTranslator
            query_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except: 
        query_en = query_he

    print(f"DEBUG: Searching for '{query_en}'")

    # 3. משיכת מוצרים גולמיים
    raw_products = get_ali_products(query_en)
    
    # 4. סינון AI - הלב של המערכת
    final_products = []
    
    for p in raw_products:
        if len(final_products) >= 4: break
        
        # שולחים ל-AI לבדיקה
        bot.send_chat_action(m.chat.id, "typing")
        ai_result = analyze_with_ai(query_he, p["product_title"], p["target_sale_price"])
        
        if ai_result.get("valid"):
            p["display_title"] = ai_result.get("title") # הכותרת היפה מה-AI
            final_products.append(p)
            print(f"✅ AI Approved: {p['display_title']}")
        else:
            print(f"❌ AI Rejected: {p['product_title'][:30]}...")

    if not final_products:
        bot.edit_message_text("🛑 ה-AI סינן את כל התוצאות כי הן לא עמדו בסטנדרט האיכות.", m.chat.id, msg.message_id)
        return

    # 5. בניית התשובה
    bot.delete_message(m.chat.id, msg.message_id)
    
    images = []
    text = f"🤖 **הבחירות החכמות עבורך:**\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(final_products):
        price = p.get("target_sale_price")
        # בדיקה שהלינק תקין
        raw_link = p.get("product_detail_url")
        link = get_short_link(raw_link)
        if not link: continue

        images.append(p.get("product_main_image_url"))
        
        text += f"{i+1}. 🥇 {p['display_title']}\n"
        text += f"💰 מחיר: {price}₪\n"
        text += f"{link}\n\n" # הקישור הגלוי שרצית
        
        kb.add(types.InlineKeyboardButton(f"🛍️ מוצר {i+1}", url=link))

    if images:
        try: bot.send_photo(m.chat.id, create_collage(images), caption=text, parse_mode="Markdown", reply_markup=kb)
        except: bot.send_message(m.chat.id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="Markdown", reply_markup=kb)

print("🚀 Bot Started with Real AI Engine...")
bot.infinity_polling(timeout=10, long_polling_timeout=5)
