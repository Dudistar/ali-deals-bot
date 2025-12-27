# ==========================================
# DrDeals Premium – Color & Style Master
# ==========================================

import telebot
import requests
import time
import hashlib
import logging
import io
import random
from telebot import types
from PIL import Image, ImageDraw
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
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
retry = Retry(connect=3, backoff_factor=1, status_forcelist=[500,502,503,504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('https://', adapter)

# ==========================================
# 🎨 מילון צבעים וסגנונות (הסוד לדיוק)
# ==========================================
# אליאקספרס עובד עם מילות מפתח ספציפיות. תרגום רגיל לא מספיק.
COLOR_MAP = {
    'שמנת': 'Beige', 'בז': 'Beige', 'קרם': 'Beige',
    'לבן': 'White',
    'שחור': 'Black',
    'אדום': 'Red',
    'כחול': 'Blue', 'תכלת': 'Sky Blue',
    'ירוק': 'Green', 'זית': 'Army Green',
    'ורוד': 'Pink',
    'זהב': 'Gold',
    'כסף': 'Silver'
}

STYLE_MAP = {
    'אלגנטי': 'Elegant Office',
    'ערב': 'Evening Party',
    'יומיומי': 'Casual',
    'ספורט': 'Sport',
    'וינטג': 'Vintage',
    'רטרו': 'Retro',
    'צנוע': 'Modest Long'
}

# ==========================================
# 🛡️ הגדרות קטגוריות (למניעת כלי עבודה)
# ==========================================
STRICT_LOGIC = {
    'מעיל': {'cat_id': '200001901', 'base_en': 'Women Coat'},
    'רחפן': {'cat_id': '200002649', 'base_en': 'Professional Drone'},
    'שעון': {'cat_id': '200000095', 'base_en': 'Smart Watch'},
    'אוזניות': {'cat_id': '63705', 'base_en': 'Wireless Headphones'},
    'טלפון': {'cat_id': '2000023', 'base_en': 'Smartphone'},
    'שמלה': {'cat_id': '200003482', 'base_en': 'Women Dress'},
    'נעליים': {'cat_id': '322', 'base_en': 'Women Shoes'}
}

# ==========================================
# 🧠 בונה השאילתות החכם
# ==========================================
def build_smart_queries(user_query_he, rule):
    """
    בונה 2-3 רמות של חיפוש.
    רמה 1: הכל כולל הכל (צבע, סגנון, מוצר).
    רמה 2: רק צבע ומוצר (מוותר על הסגנון).
    רמה 3: רק מוצר (ברירת מחדל).
    """
    base_product = rule['base_en']
    detected_colors = []
    detected_styles = []

    # 1. חילוץ צבעים
    for heb, eng in COLOR_MAP.items():
        if heb in user_query_he:
            detected_colors.append(eng)
    
    # 2. חילוץ סגנונות
    for heb, eng in STYLE_MAP.items():
        if heb in user_query_he:
            detected_styles.append(eng)

    queries = []
    
    # שאילתה 1: הכי ספציפית (מוצר + צבע + סגנון)
    # דוגמה: "Women Coat Beige Elegant Office"
    full_query = f"{base_product} {' '.join(detected_colors)} {' '.join(detected_styles)}".strip()
    queries.append(full_query)

    # שאילתה 2: התפשרות על סגנון (מוצר + צבע) - אם המשתמש ביקש צבע
    # דוגמה: "Women Coat Beige"
    if detected_colors:
        color_query = f"{base_product} {' '.join(detected_colors)}".strip()
        if color_query != full_query:
            queries.append(color_query)

    # שאילתה 3: בסיס (רק אם הכל נכשל)
    # דוגמה: "Women Coat"
    queries.append(base_product)
    
    return queries

# ==========================================
# 🔐 חתימה ורשת
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query, cat_id=None):
    # print(f"DEBUG: Trying query: '{query}'") # לדיבאג
    params = {
        "app_key": APP_KEY,
        "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "format": "json",
        "sign_method": "md5",
        "v": "2.0",
        "partner_id": "top-autopilot",
        "keywords": query,
        "target_currency": "ILS",
        "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC",
        "page_size": "50"
    }
    if cat_id: params["category_ids"] = cat_id
    params["sign"] = generate_sign(params)

    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        if "aliexpress_affiliate_product_query_response" not in data: return []
        products = data["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
        return products if isinstance(products, list) else [products]
    except: return []

# ==========================================
# 🧹 סינון חכם (Smart Filter)
# ==========================================
def filter_products(products, query_string):
    """
    מסנן מוצרים שלא מכילים את מילות המפתח הקריטיות שחיפשנו כרגע.
    אם חיפשנו 'Beige', חייב להיות 'Beige' (או Cream/Khaki/Apricot) בכותרת.
    """
    clean = []
    # מילים נרדפות לצבעים נפוצים באליאקספרס
    color_expansions = {
        'beige': ['beige', 'cream', 'khaki', 'apricot', 'white', 'camel'],
        'white': ['white', 'ivory'],
        'red': ['red', 'burgundy', 'wine']
    }

    query_parts = query_string.lower().split()
    
    for p in products:
        title = p.get("product_title", "").lower()
        
        # הגנה בסיסית ממברגים
        if "screw" in title or "repair" in title or "tool" in title: continue

        # בדיקת התאמה למילות החיפוש הנוכחיות
        match_score = 0
        for word in query_parts:
            # אם זו מילת צבע, נבדוק גם את המילים הנרדפות שלה
            word_found = False
            if word in title:
                word_found = True
            elif word in color_expansions: # הרחבת צבעים
                if any(c in title for c in color_expansions[word]):
                    word_found = True
            
            if word_found: match_score += 1
        
        # אם מצאנו את רוב המילים (לפחות חצי), זה מוצר טוב
        if match_score >= len(query_parts) / 2:
            clean.append(p)
            
    return clean

# ==========================================
# 🔗 לינקים וקולאז'
# ==========================================
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
    for u in urls[:3]:
        try:
            img = Image.open(io.BytesIO(session.get(u, timeout=5).content)).resize((500,500))
        except: img = Image.new("RGB",(500,500),"white")
        imgs.append(img)
    while len(imgs)<3: imgs.append(Image.new("RGB",(500,500),"white"))
    canvas = Image.new("RGB",(1000,1000),"white")
    canvas.paste(imgs[0].resize((1000,500)),(0,0))
    canvas.paste(imgs[1],(0,500))
    canvas.paste(imgs[2],(500,500))
    out = io.BytesIO()
    canvas.save(out,"JPEG",quality=85)
    out.seek(0)
    return out

# ==========================================
# 🚀 בוט ראשי
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    if not m.text.startswith("חפש לי"): return

    query_he = m.text.replace("חפש לי","").strip()
    bot.send_chat_action(m.chat.id, "typing")
    
    # 1. זיהוי קטגוריה בסיסית
    rule = None
    for key, r in STRICT_LOGIC.items():
        if key in query_he:
            rule = r
            break
            
    # אם לא זוהתה קטגוריה, הולכים לתרגום רגיל (פחות מומלץ, אבל עובד)
    if not rule:
        bot.reply_to(m, "💡 נסה לכלול שם מוצר ברור (מעיל, שעון, רחפן...). מחפש בכל זאת...")
        try: q_en = GoogleTranslator(source='auto', target='en').translate(query_he)
        except: q_en = query_he
        queries_to_try = [q_en]
        cat_id = None
    else:
        # 2. בניית שאילתות מדורגות (החלק החכם!)
        queries_to_try = build_smart_queries(query_he, rule)
        cat_id = rule['cat_id']
        bot.reply_to(m, f"🕵️‍♂️ מחפש: {query_he}\n(ממיר לצבעים ומונחים של אליאקספרס...)")

    # 3. לולאת חיפוש (מהספציפי לכללי)
    final_products = []
    
    for q in queries_to_try:
        # print(f"DEBUG: Trying -> {q}") 
        products = get_ali_products(q, cat_id)
        filtered = filter_products(products, q)
        
        if filtered:
            final_products = filtered
            break # מצאנו! לא צריך להמשיך לחיפושים כלליים יותר
    
    # 4. תוצאות
    if not final_products:
        bot.send_message(m.chat.id, "🛑 לא מצאתי תוצאות שמתאימות לתיאור המדויק.")
        return

    top_3 = final_products[:3]
    images = []
    text = f"🧥 <b>הבחירות שלי עבורך:</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(top_3):
        try: title = GoogleTranslator(source='auto', target='iw').translate(p["product_title"])
        except: title = p["product_title"]
        
        price = p.get("target_sale_price", "?") + "₪"
        link = get_short_link(p.get("product_detail_url"))
        images.append(p.get("product_main_image_url"))

        text += f"{i+1}. {title[:55]}...\n💰 <b>{price}</b>\n🔗 {link}\n\n"
        kb.add(types.InlineKeyboardButton(f"🛍️ לרכישה {i+1}", url=link))

    if images:
        try: bot.send_photo(m.chat.id, create_collage(images), caption=text, parse_mode="HTML", reply_markup=kb)
        except: bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)

print("Bot is running with Smart Color & Style Logic...")
bot.infinity_polling()
