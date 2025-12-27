# ==========================================
# DrDeals Premium – UNIVERSAL FIX
# ==========================================
import telebot
import requests
import time
import hashlib
import logging
import io
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
# 🧠 המוח המרכזי: הגדרות לכל מוצר
# ==========================================
# כאן אנחנו מגדירים לכל מוצר:
# 1. איך קוראים לו באנגלית (keyword)
# 2. מה הקטגוריה שלו (cat_id) - כדי למנוע מברגים
# 3. מה *אסור* שיהיה בו (ban_words)
# 4. מה המינימום מחיר (min_price) - למנוע זבל

PRODUCT_RULES = {
    "רחפן": {
        "en": "Professional Drone 4k",
        "cat_id": "200002649",
        "ban_words": ["propeller", "battery", "landing", "pad", "case", "cable", "motor", "arm"],
        "min_price": "100"
    },
    "מעיל": {
        "en": "Women Elegant Coat",
        "cat_id": "200001901",
        "ban_words": ["raincoat", "plastic", "hanger", "hook", "sport", "yoga", "hiking"],
        "min_price": "50"
    },
    "שעון": {
        "en": "Smart Watch",
        "cat_id": "200000095",
        "ban_words": ["strap", "band", "screen protector", "case", "film", "charger"],
        "min_price": "50"
    },
    "אוזניות": {
        "en": "Wireless Headphones Bluetooth",
        "cat_id": "63705",
        "ban_words": ["case", "silicone", "cable", "pad", "tips", "cleaner"],
        "min_price": "30"
    },
    "טלפון": {
        "en": "Smartphone Global Version",
        "cat_id": "2000023",
        "ban_words": ["case", "cover", "screen", "glass", "holder", "cable"],
        "min_price": "300"
    },
    "מצלמה": {
        "en": "Digital Camera",
        "cat_id": "200002412",
        "ban_words": ["tripod", "bag", "lens cap", "strap", "battery"],
        "min_price": "150"
    }
}

# מילות מפתח לצבעים (לזיהוי ושיפור חיפוש)
COLORS = {
    'שמנת': 'Beige', 'בז': 'Beige', 'קרם': 'Beige',
    'לבן': 'White', 'שחור': 'Black', 'אדום': 'Red',
    'כחול': 'Blue', 'ירוק': 'Green', 'ורוד': 'Pink'
}

# ==========================================
# 🔐 חתימה ורשת
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query, cat_id=None, min_price="10"):
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
        "min_sale_price": min_price
    }
    if cat_id:
        params["category_ids"] = cat_id
    
    params["sign"] = generate_sign(params)

    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        if "aliexpress_affiliate_product_query_response" not in data: return []
        products = data["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
        return products if isinstance(products, list) else [products]
    except: return []

# ==========================================
# 🧹 המסנן האוניברסלי
# ==========================================
def universal_filter(products, ban_list):
    clean = []
    # מילים שאסורות בכל המצבים
    global_ban = ["screw", "repair", "connector", "adapter", "toy", "part", "accessory"]
    
    for p in products:
        title = p.get("product_title", "").lower()
        
        # בדיקה 1: רשימה גלובלית
        if any(bad in title for bad in global_ban): continue
        
        # בדיקה 2: רשימה ספציפית למוצר (אם יש)
        if ban_list:
            if any(bad in title for bad in ban_list): continue
            
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

    user_input = m.text.replace("חפש לי","").strip()
    bot.send_chat_action(m.chat.id, "typing")

    # 1. זיהוי מוצר מתוך הטקסט
    detected_rule = None
    rule_name = None
    
    # בדיקה איזו מילת מפתח (רחפן, מעיל...) מופיעה בטקסט
    for key, rule in PRODUCT_RULES.items():
        if key in user_input:
            detected_rule = rule
            rule_name = key
            break
    
    # 2. בניית השאילתה
    query_en = ""
    cat_id = None
    ban_list = []
    min_price = "10"

    if detected_rule:
        # מקרה א': זיהינו מוצר מוכר (רחפן, מעיל...)
        # בודקים אם יש צבע בבקשה
        color_en = ""
        for heb_col, eng_col in COLORS.items():
            if heb_col in user_input:
                color_en = eng_col
                break
        
        # בונים שאילתה: "Women Elegant Coat Beige"
        query_en = f"{detected_rule['en']} {color_en}".strip()
        cat_id = detected_rule['cat_id']
        ban_list = detected_rule['ban_words']
        min_price = detected_rule['min_price']
        
        bot.reply_to(m, f"🔎 זיהיתי: {rule_name}. מחפש בקטגוריה המתאימה...")
        
    else:
        # מקרה ב': חיפוש כללי (לא מוכר)
        bot.reply_to(m, f"🔎 מחפש בכל אליאקספרס: {user_input}...")
        try: query_en = GoogleTranslator(source='auto', target='en').translate(user_input)
        except: query_en = user_input
    
    # 3. ביצוע החיפוש
    products = get_ali_products(query_en, cat_id, min_price)
    
    # 4. סינון
    clean_products = universal_filter(products, ban_list)
    
    # 5. הצגה
    if not clean_products:
        bot.send_message(m.chat.id, "🛑 לא נמצאו תוצאות איכותיות.")
        return

    top_3 = clean_products[:3]
    images = []
    text = f"🛍️ **תוצאות עבור: {user_input}**\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(top_3):
        try: title = GoogleTranslator(source='auto', target='iw').translate(p["product_title"])
        except: title = p["product_title"]
        
        price = p.get("target_sale_price", "?") + "₪"
        link = get_short_link(p.get("product_detail_url"))
        images.append(p.get("product_main_image_url"))

        text += f"{i+1}. {title[:55]}...\n💰 <b>{price}</b>\n🔗 {link}\n\n"
        kb.add(types.InlineKeyboardButton(f"🛒 לרכישה {i+1}", url=link))

    if images:
        try: bot.send_photo(m.chat.id, create_collage(images), caption=text, parse_mode="HTML", reply_markup=kb)
        except: bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)

print("Bot is running with UNIVERSAL Logic...")
bot.infinity_polling()
