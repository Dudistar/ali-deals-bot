# ==========================================
# DrDeals Premium – Text Verification Edition
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
# 📚 מילון אימות טקסטואלי (במקום קטגוריות שנכשלו)
# ==========================================
# לכל סוג מוצר יש "מילות מפתח חובה".
# אם הכותרת באנגלית לא מכילה אחת מהן - המוצר נפסל.

VALIDATION_RULES = {
    'מעיל': ['coat', 'jacket', 'parka', 'trench', 'outerwear', 'blazer', 'cardigan'],
    'רחפן': ['drone', 'quadcopter', 'uav', 'aircraft'],
    'שעון': ['watch', 'smartwatch', 'wristband'],
    'אוזניות': ['headphone', 'earphone', 'earbud', 'headset'],
    'טלפון': ['phone', 'smartphone', 'mobile', 'cellphone'],
    'נעליים': ['shoe', 'sneaker', 'boot', 'sandal', 'heel'],
    'שמלה': ['dress', 'gown', 'skirt']
}

# תרגום צבעים ידני לדיוק מקסימלי
COLOR_MAP = {
    'שמנת': 'Cream', 'בז': 'Beige', 'קרם': 'Cream',
    'לבן': 'White', 'שחור': 'Black', 'אדום': 'Red',
    'כחול': 'Blue', 'תכלת': 'Sky Blue', 'ירוק': 'Green',
    'ורוד': 'Pink', 'זהב': 'Gold', 'כסף': 'Silver'
}

# ==========================================
# 🔐 חתימה ורשת
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query):
    # print(f"DEBUG: Searching API for: {query}")
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
    params["sign"] = generate_sign(params)

    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        if "aliexpress_affiliate_product_query_response" not in data: return []
        products = data["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
        return products if isinstance(products, list) else [products]
    except: return []

# ==========================================
# 🧹 המסנן הטקסטואלי (Text Validator)
# ==========================================
def text_validator(products, must_have_words):
    clean = []
    
    # רשימה שחורה גלובלית (ברגים, צינורות, חלקים)
    blacklist = ["screw", "pipe", "adapter", "connector", "repair tool", "part only", "accessory"]

    for p in products:
        title = p.get("product_title", "").lower()
        
        # 1. בדיקת רשימה שחורה
        if any(bad in title for bad in blacklist):
            continue

        # 2. בדיקת חובה (האם זה באמת מעיל?)
        # אם המערכת הגדירה מילות חובה (למשל coat, jacket) - חייב להופיע!
        if must_have_words:
            if not any(good in title for good in must_have_words):
                continue
        
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
    bot.reply_to(m, f"🕵️‍♂️ מחפש: {query_he}...")

    # 1. הכנת השאילתה (תרגום + התאמת צבעים)
    # המרת צבע מעברית לאנגלית אם קיים
    color_en = ""
    for heb_color, eng_color in COLOR_MAP.items():
        if heb_color in query_he:
            color_en = eng_color
            break
    
    # תרגום בסיסי של שאר המשפט
    try:
        base_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except:
        base_en = query_he

    # אם זיהינו צבע ידנית, נדחוף אותו לחיפוש כדי לחזק את התוצאה
    if color_en and color_en.lower() not in base_en.lower():
        final_query = f"{base_en} {color_en}"
    else:
        final_query = base_en

    # 2. קביעת מילות אימות (Validation Words)
    must_have = []
    for key, words in VALIDATION_RULES.items():
        if key in query_he:
            must_have = words
            break

    # 3. ביצוע החיפוש
    products = get_ali_products(final_query)
    
    # 4. סינון לפי טקסט (ולא לפי ID דפוק)
    valid_products = text_validator(products, must_have)

    # 5. מנגנון גיבוי (אם לא מצאנו עם הצבע הספציפי)
    if not valid_products and must_have:
        # מנסים לחפש רק את שם המוצר בלי הצבע והתיאורים
        # למשל: במקום "Cream Elegant Coat" -> נחפש רק "Women Coat" ונסנן ידנית
        bot.send_message(m.chat.id, "⚠️ החיפוש המדויק לא הניב תוצאות, מרחיב חיפוש...")
        fallback_query = must_have[0] + " women" # דוגמה: coat women
        products = get_ali_products(fallback_query)
        valid_products = text_validator(products, must_have)

    if not valid_products:
        bot.send_message(m.chat.id, "🛑 לא נמצאו תוצאות תקינות (סיננתי תוצאות לא רלוונטיות).")
        return

    # 6. הצגה
    top_3 = valid_products[:3]
    images = []
    text = f"🧥 <b>תוצאות עבור: {query_he}</b>\n\n"
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

print("Bot is running with Text Verification Logic...")
bot.infinity_polling()
