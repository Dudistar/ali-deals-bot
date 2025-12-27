# ===============================
# DrDeals Premium – The Enforcer
# ===============================

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

# חיבור יציב
session = requests.Session()
retry = Retry(connect=3, backoff_factor=1, status_forcelist=[500,502,503,504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('https://', adapter)

# ==========================================
# 🛡️ המוח: מיפוי קטגוריות + אימות מילים (החלק הקריטי)
# ==========================================
# זהו המילון שמונע את כלי העבודה.
# המפתח: המילה בעברית שהמשתמש כתב.
# הערך: רשימה של מילים שחייבות להופיע בכותרת באנגלית + קטגוריה.

STRICT_LOGIC = {
    'מעיל': {
        'cat_id': '200001901', 
        'must_have': ['coat', 'jacket', 'parka', 'trench', 'overcoat', 'windbreaker']
    },
    'רחפן': {
        'cat_id': '200002649', 
        'must_have': ['drone', 'quadcopter', 'uav', 'aircraft']
    },
    'שעון': {
        'cat_id': '200000095', 
        'must_have': ['watch', 'smartwatch', 'band', 'wrist']
    },
    'אוזניות': {
        'cat_id': '63705', 
        'must_have': ['headphone', 'earphone', 'earbud', 'headset', 'bud']
    },
    'טלפון': {
        'cat_id': '2000023', 
        'must_have': ['phone', 'smartphone', 'mobile', 'cellphone']
    },
    'נעליים': {
        'cat_id': '322', 
        'must_have': ['shoe', 'sneaker', 'boot', 'sandal', 'heel']
    },
    'שמלה': {
        'cat_id': '200003482', 
        'must_have': ['dress', 'gown', 'skirt']
    }
}

# ==========================================
# 🔐 חתימה
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

# ==========================================
# 🎣 שליפת מוצרים מאליאקספרס
# ==========================================
def get_ali_products(query, cat_id=None):
    print(f"DEBUG: Searching API for '{query}' with CatID: {cat_id}") # דיבאג למסוף
    
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
        # בדיקה שהתגובה תקינה
        if "aliexpress_affiliate_product_query_response" not in data:
            print("DEBUG: API Error or Empty Response", data)
            return []
            
        resp_result = data["aliexpress_affiliate_product_query_response"]["resp_result"]
        if resp_result["resp_code"] != 200:
            return []
            
        products = resp_result["result"]["products"]["product"]
        return products if isinstance(products, list) else [products]
    except Exception as e:
        print(f"DEBUG: Exception in fetch: {e}")
        return []

# ==========================================
# 🕵️‍♂️ סינון ברזל (Strict Verify)
# ==========================================
def strict_filter(products, user_query_hebrew):
    clean_products = []
    user_query_hebrew = user_query_hebrew.lower()
    
    # 1. זיהוי אם יש חוקים קשוחים למילה הזו
    active_rule = None
    for key, rule in STRICT_LOGIC.items():
        if key in user_query_hebrew:
            active_rule = rule
            print(f"DEBUG: Active Rule Found for '{key}': Must match {rule['must_have']}")
            break
    
    # 2. סינון
    for p in products:
        title_lower = p.get("product_title", "").lower()
        
        # סינון מילים אסורות גלובלי (כמו חלקים ואביזרים)
        bad_words = ["part", "screw", "aluminum alloy", "vise", "tool", "repair"]
        if any(bad in title_lower for bad in bad_words):
            print(f"DEBUG: REJECTED (Bad Word): {title_lower[:30]}...")
            continue

        # אם יש חוק קשוח - בודקים אותו
        if active_rule:
            # בדיקה: האם לפחות אחת ממילות החובה מופיעה בכותרת?
            has_match = any(word in title_lower for word in active_rule['must_have'])
            if not has_match:
                print(f"DEBUG: REJECTED (Rule Mismatch): {title_lower[:30]}...")
                continue # זרוק לפח!
        
        # אם עברנו את כל השומרים - המוצר נכנס
        clean_products.append(p)
        
    return clean_products

# ==========================================
# 🔗 קיצור לינק
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

# ==========================================
# 🖼️ קולאז'
# ==========================================
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
# 🚀 הבוט
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    if not m.text.startswith("חפש לי"): return

    # ניקוי השאילתה
    query_he = m.text.replace("חפש לי","").strip()
    
    bot.send_chat_action(m.chat.id, "typing")
    bot.reply_to(m, f"🕵️‍♂️ מחפש ביסודיות: {query_he}...")

    # 1. תרגום לאנגלית
    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except:
        query_en = query_he # Fallback

    # 2. בדיקה האם יש לנו חוק קשוח למילה הזו (לקבלת Category ID)
    cat_id = None
    for key, rule in STRICT_LOGIC.items():
        if key in query_he.lower():
            cat_id = rule['cat_id']
            break

    # 3. משיכה מאליאקספרס
    products = get_ali_products(query_en, cat_id)
    
    # 4. הפעלת הסלקטור הקשוח
    final_products = strict_filter(products, query_he)

    if not final_products:
        bot.send_message(m.chat.id, "🛑 לא נמצאו תוצאות מדויקות.\nהמסנן הסיר תוצאות לא רלוונטיות (כמו חלקי חילוף או אביזרים).")
        return

    # 5. הצגה
    top_3 = final_products[:3]
    images = []
    text = f"🧥 <b>תוצאות מאומתות עבור: {query_he}</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(top_3):
        # תרגום כותרת לעברית
        try:
            title = GoogleTranslator(source='auto', target='iw').translate(p["product_title"])
        except:
            title = p["product_title"]
            
        price = p.get("target_sale_price", "?") + "₪"
        link = get_short_link(p.get("product_detail_url"))
        images.append(p.get("product_main_image_url"))

        text += f"{i+1}. {title[:50]}...\n💰 {price}\n🔗 {link}\n\n"
        kb.add(types.InlineKeyboardButton(f"🛒 לרכישה {i+1}", url=link))

    if images:
        try:
            bot.send_photo(m.chat.id, create_collage(images), caption=text, parse_mode="HTML", reply_markup=kb)
        except:
            bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)

print("Bot is running with Strict Enforcer...")
bot.infinity_polling()
