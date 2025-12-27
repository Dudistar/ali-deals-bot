# ==========================================
# DrDeals Premium – Fashion Logic Edition
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
# 🎨 מפות חכמות: צבעים וסגנונות
# ==========================================
COLOR_MAP = {
    'שמנת': 'Beige', 'בז': 'Beige', 'קרם': 'Beige', 'חול': 'Khaki',
    'לבן': 'White', 'שחור': 'Black', 'אדום': 'Red',
    'כחול': 'Blue', 'ירוק': 'Green', 'ורוד': 'Pink'
}

# אם המשתמש מחפש "אלגנטי", נחסום את המילים האלו:
STYLE_BAN_LIST = {
    'elegant': ['yoga', 'sport', 'hiking', 'camping', 'rain', 'waterproof', 'running', 'gym', 'fitness', 'cycling', 'fishing', 'sun protection'],
    'formal': ['casual', 'beach', 'home', 'sleep', 'sport'],
}

# מילות מפתח לחיזוק החיפוש
STYLE_BOOST = {
    'אלגנטי': 'Elegant Office Lady Formal',
    'ערב': 'Evening Party Luxury',
    'חורף': 'Winter Warm Thick',
    'צמר': 'Wool Blend',
    'פוך': 'Down Parka'
}

# ==========================================
# 🔐 חתימה ורשת
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query):
    # print(f"DEBUG: API Request -> {query}")
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
        "page_size": "50",
        "min_sale_price": "50" # סינון זבל: לא מציגים מעילים מתחת ל-50 שקל!
    }
    params["sign"] = generate_sign(params)

    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        if "aliexpress_affiliate_product_query_response" not in data: return []
        products = data["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
        return products if isinstance(products, list) else [products]
    except: return []

# ==========================================
# 🧠 בונה השאילתות + המסנן
# ==========================================
def construct_query(user_input):
    """
    בונה שאילתה חכמה:
    במקום "מעיל שמנת" -> "Women Coat Beige Elegant Office"
    """
    # 1. זיהוי מוצר בסיס (חובה)
    base_product = "Women Coat" # ברירת מחדל חזקה
    if "שמלה" in user_input: base_product = "Women Dress"
    elif "נעליים" in user_input: base_product = "Women Shoes"
    
    # 2. המרת צבע
    color_en = ""
    for heb, eng in COLOR_MAP.items():
        if heb in user_input:
            color_en = eng
            break
            
    # 3. זיהוי סגנון ובוסט
    style_boost = ""
    is_elegant = False
    for heb, boost in STYLE_BOOST.items():
        if heb in user_input:
            style_boost += " " + boost
            if "אלגנטי" in heb or "ערב" in heb:
                is_elegant = True
    
    # הרכבת השאילתה הסופית
    final_query = f"{base_product} {color_en} {style_boost}".strip()
    return final_query, is_elegant

def advanced_filter(products, is_elegant):
    clean = []
    
    # רשימה שחורה תמידית (כלי עבודה, אביזרים)
    global_ban = ["screw", "repair", "tool", "connector", "pipe", "adapter", "toy", "accessory"]
    
    # רשימה שחורה לסגנון אלגנטי (ספורט וטיולים)
    sport_ban = STYLE_BAN_LIST['elegant']

    for p in products:
        title = p.get("product_title", "").lower()
        
        # 1. העפה של כלי עבודה
        if any(bad in title for bad in global_ban): continue

        # 2. אם המשתמש רצה אלגנטי - העפה של ספורט/יוגה/טיולים
        if is_elegant:
            if any(bad in title for bad in sport_ban):
                continue
            
            # וידוא נוסף: אם זה מעיל גשם זול (Plastic/Raincoat)
            if "raincoat" in title or "poncho" in title:
                continue

        clean.append(p)
    
    return clean

# ==========================================
# 🔗 קיצור לינק + תמונות
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

    user_input = m.text.replace("חפש לי","").strip()
    bot.send_chat_action(m.chat.id, "typing")
    
    # 1. בניית שאילתה חכמה
    # התוצאה תהיה משהו כמו: "Women Coat Beige Elegant Office Lady"
    smart_query, is_elegant = construct_query(user_input)
    
    bot.reply_to(m, f"👠 מחפש בקטגוריית אופנה: {smart_query}...")

    # 2. משיכה מאליאקספרס (עם סינון מחיר מינימלי ב-API)
    products = get_ali_products(smart_query)

    # 3. סינון אגרסיבי של ספורט/טיולים
    final_products = advanced_filter(products, is_elegant)

    # 4. אם הסינון מחק הכל (כי הכל היה ספורט), נסה חיפוש רחב יותר
    if not final_products and is_elegant:
        # מוותרים על ה"אלגנטי" בטקסט אבל משאירים את הצבע
        bot.send_message(m.chat.id, "⚠️ לא נמצאו מעילים אלגנטיים מדויקים, מציג מעילים בצבע המבוקש...")
        fallback_query = smart_query.replace("Elegant Office Lady Formal", "").strip()
        products = get_ali_products(fallback_query)
        final_products = advanced_filter(products, False) # בלי סינון ספורט הדוק

    if not final_products:
        bot.send_message(m.chat.id, "🛑 לא נמצאו פריטים תואמים.")
        return

    # 5. הצגה
    top_3 = final_products[:3]
    images = []
    text = f"🧥 <b>הבחירות האופנתיות שלי:</b>\n\n"
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

print("Bot is running with Fashion Intelligence...")
bot.infinity_polling()
