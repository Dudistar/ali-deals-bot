# ==========================================
# DrDeals Premium – Smart Fallback Edition
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
# 🛡️ לוגיקה כפולה: סינון + גיבוי
# ==========================================
# fallback_query: מה לחפש אם החיפוש המקורי נכשל
STRICT_LOGIC = {
    'מעיל': {
        'cat_id': '200001901', 
        'must_have': ['coat', 'jacket', 'parka', 'trench', 'outwear'],
        'fallback_query': 'Woman Coat Winter'
    },
    'רחפן': {
        'cat_id': '200002649', 
        'must_have': ['drone', 'quadcopter', 'uav'],
        'fallback_query': 'Professional Drone Camera'
    },
    'שעון': {
        'cat_id': '200000095', 
        'must_have': ['watch', 'smartwatch', 'band'],
        'fallback_query': 'Smart Watch'
    },
    'אוזניות': {
        'cat_id': '63705', 
        'must_have': ['headphone', 'earphone', 'earbud', 'headset'],
        'fallback_query': 'Wireless Headphones'
    },
    'טלפון': {
        'cat_id': '2000023', 
        'must_have': ['phone', 'smartphone', 'mobile', 'android'],
        'fallback_query': 'Smartphone Global Version'
    },
     'נעליים': {
        'cat_id': '322', 
        'must_have': ['shoe', 'sneaker', 'boot', 'heel'],
        'fallback_query': 'Women Shoes'
    }
}

# ==========================================
# 🔐 חתימה
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

# ==========================================
# 🎣 שליפת מוצרים
# ==========================================
def get_ali_products(query, cat_id=None):
    print(f"DEBUG: Searching '{query}' (Cat: {cat_id})")
    
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
    
    if cat_id:
        params["category_ids"] = cat_id

    params["sign"] = generate_sign(params)

    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        if "aliexpress_affiliate_product_query_response" not in data:
            return []
        products = data["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
        return products if isinstance(products, list) else [products]
    except Exception as e:
        print(f"Error: {e}")
        return []

# ==========================================
# 🕵️‍♂️ סינון (לא מוחק אם אין ברירה)
# ==========================================
def smart_filter(products, rule=None):
    clean = []
    
    # מילים שאסור שיהיו בשום מצב (חלקי חילוף)
    global_ban = ["screw", "repair tool", "connector", "adapter", "pipe", "aluminum alloy"]

    for p in products:
        title = p.get("product_title", "").lower()
        
        # 1. סינון גלובלי (הגנה ממברגים)
        if any(bad in title for bad in global_ban):
            continue

        # 2. סינון לפי קטגוריה (אם הוגדרה)
        if rule:
            # חייב להכיל אחת ממילות המפתח (למשל Coat)
            if not any(w in title for w in rule['must_have']):
                continue
        
        clean.append(p)
    
    return clean

# ==========================================
# 🔗 לינקים ותמונות
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
    bot.reply_to(m, f"🕵️‍♂️ מחפש: {query_he}...")

    # 1. זיהוי חוקים וקטגוריה
    rule = None
    for key, r in STRICT_LOGIC.items():
        if key in query_he:
            rule = r
            break
    
    cat_id = rule['cat_id'] if rule else None

    # 2. תרגום (ניסיון ראשון - ספציפי)
    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except:
        query_en = query_he

    # 3. חיפוש ראשון (ספציפי)
    products = get_ali_products(query_en, cat_id)
    final_products = smart_filter(products, rule)

    # 4. מנגנון הגיבוי (הצלה!)
    # אם החיפוש הספציפי נכשל (לא מצא כלום או שהכל סונן)
    if not final_products and rule:
        bot.send_message(m.chat.id, "⚠️ חיפוש מדויק לא הניב תוצאות, מפעיל חיפוש חכם בקטגוריה...")
        # משתמשים בביטוי כללי שמוגדר מראש (למשל 'Woman Coat')
        fallback_query = rule['fallback_query']
        products = get_ali_products(fallback_query, cat_id)
        final_products = smart_filter(products, rule)

    # 5. בדיקה סופית
    if not final_products:
        bot.send_message(m.chat.id, "🛑 לא נמצאו תוצאות. נסה ניסוח פשוט יותר.")
        return

    # 6. הצגה
    top_3 = final_products[:3]
    images = []
    text = f"🧥 <b>תוצאות עבור: {query_he}</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(top_3):
        try:
            title = GoogleTranslator(source='auto', target='iw').translate(p["product_title"])
        except:
            title = p["product_title"]
            
        price = p.get("target_sale_price", "?") + "₪"
        link = get_short_link(p.get("product_detail_url"))
        images.append(p.get("product_main_image_url"))

        text += f"{i+1}. {title[:55]}...\n💰 <b>{price}</b>\n🔗 {link}\n\n"
        kb.add(types.InlineKeyboardButton(f"🛍️ לרכישה {i+1}", url=link))

    if images:
        try:
            bot.send_photo(m.chat.id, create_collage(images), caption=text, parse_mode="HTML", reply_markup=kb)
        except:
            bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)

print("Bot is running with Smart Fallback...")
bot.infinity_polling()
