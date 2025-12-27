# ==========================================
# DrDeals Premium – Final "Open Link" Version
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
# 🧠 מילון שיפור תוצאות (Power Words)
# ==========================================
# זה נועד לשפר את ה"סטייל" של התוצאות.
# אם מחפשים מעיל -> מוסיפים "Fashion Elegant"
POWER_WORDS = {
    'מעיל': 'Fashion Elegant',
    'שמלה': 'Trendy Style',
    'שעון': 'Luxury Brand',
    'נעליים': 'Comfortable Stylish',
    'תיק': 'Luxury Designer'
}

COLORS = {
    'שמנת': 'Beige', 'בז': 'Beige', 'קרם': 'Beige', 'חול': 'Khaki',
    'לבן': 'White', 'שחור': 'Black', 'אדום': 'Red', 'כחול': 'Blue',
    'ירוק': 'Green', 'ורוד': 'Pink', 'חום': 'Brown', 'אפור': 'Grey'
}

# רשימת אימות (Whitelist) - הגנה בסיסית ממברגים
PRODUCT_VALIDATORS = {
    'מעיל': ['coat', 'jacket', 'parka', 'trench', 'blazer', 'outerwear'],
    'רחפן': ['drone', 'quadcopter', 'uav'],
    'שעון': ['watch', 'smartwatch'],
    'אוזניות': ['headphone', 'earphone', 'headset', 'earbuds'],
    'טלפון': ['phone', 'smartphone', 'mobile'],
}

# ==========================================
# 🔐 חתימה ורשת
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query, min_price="15"):
    # שיניתי ל-Sort by LAST_VOLUME_DESC (הכי נמכרים) כדי לקבל תוצאות פופולריות
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
    params["sign"] = generate_sign(params)

    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        if "aliexpress_affiliate_product_query_response" not in data: return []
        products = data["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
        return products if isinstance(products, list) else [products]
    except: return []

# ==========================================
# 🧹 המנקה והמסנן
# ==========================================
def clean_title_hebrew(title_en):
    try:
        title_he = GoogleTranslator(source='auto', target='iw').translate(title_en)
    except:
        return title_en

    # ניקוי מילים מיותרות כדי שהכותרת תהיה נקייה
    garbage = ["חדש", "2024", "2025", "משלוח חינם", "הגעה", "אופנה", "נשים", "גברים", "יוקרה", "באיכות גבוהה", "טרנד", "סגנון", "חורף", "סתיו"]
    for word in garbage:
        title_he = title_he.replace(word, "")
    
    # ניקוי רווחים כפולים
    title_he = " ".join(title_he.split())
    
    # קיצור אם ארוך מדי
    words = title_he.split()
    if len(words) > 10:
        return " ".join(words[:10]) + "..."
    return title_he

def validate_product(product, original_query_he):
    title_lower = product.get("product_title", "").lower()
    
    # הגנה גלובלית
    global_ban = ["screw", "repair", "tool", "connector", "adapter", "pipe", "accessory", "part", "kit"]
    if any(bad in title_lower for bad in global_ban): return False

    # אימות לפי מוצר (אם זוהה)
    for key, valid_words in PRODUCT_VALIDATORS.items():
        if key in original_query_he:
            # אם אף מילת מפתח לא נמצאת בכותרת - המוצר נפסל
            if not any(good in title_lower for good in valid_words):
                return False
    return True

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
    # מנסים להביא 4 תמונות לקולאז' יפה
    for u in urls[:4]:
        try:
            img = Image.open(io.BytesIO(session.get(u, timeout=5).content)).resize((500,500))
        except: img = Image.new("RGB",(500,500),"white")
        imgs.append(img)
    
    while len(imgs)<4: imgs.append(Image.new("RGB",(500,500),"white"))
    
    # 2x2 Grid
    canvas = Image.new("RGB",(1000,1000),"white")
    canvas.paste(imgs[0],(0,0))
    canvas.paste(imgs[1],(500,0))
    canvas.paste(imgs[2],(0,500))
    canvas.paste(imgs[3],(500,500))
    
    # מספור
    draw = ImageDraw.Draw(canvas)
    positions = [(30,30), (530,30), (30,530), (530,530)]
    for i, (x,y) in enumerate(positions):
        draw.ellipse((x,y,x+70,y+70),fill="#FFD700",outline="black",width=3)
        draw.text((x+25,y+15),str(i+1),fill="black", font_size=40)

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
    
    # חיווי התחלתי
    msg = bot.reply_to(m, f"🔎 מעבד נתונים עבור: {query_he}...")
    bot.send_chat_action(m.chat.id, "typing")

    # 1. עיבוד שאילתה חכם
    color_en = ""
    for heb_col, eng_col in COLORS.items():
        if heb_col in query_he:
            color_en = eng_col
            break
            
    try:
        base_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except:
        base_en = query_he
        
    # הוספת מילות כוח אם צריך
    extra_boost = ""
    for key, boost in POWER_WORDS.items():
        if key in query_he:
            extra_boost = boost
            break

    # השאילתה הסופית לאליאקספרס
    final_query = f"{base_en} {color_en} {extra_boost}".strip()
    
    # 2. השהייה קלה (לטובת ה-UX)
    time.sleep(1.5)
    
    # 3. חיפוש
    products = get_ali_products(final_query)
    
    # 4. סינון
    valid_products = []
    for p in products:
        if validate_product(p, query_he):
            valid_products.append(p)
    
    if not valid_products:
        bot.edit_message_text("🛑 לא נמצאו תוצאות שעומדות בסטנדרט האיכות.", m.chat.id, msg.message_id)
        return

    # 5. בניית התוצאה
    top_4 = valid_products[:4]
    images = []
    
    final_text = f"🧥 <b>הבחירות המובילות עבורך:</b>\n\n"
    
    kb = types.InlineKeyboardMarkup()
    
    for i, p in enumerate(top_4):
        title_clean = clean_title_hebrew(p["product_title"])
        price = p.get("target_sale_price", "?")
        rating = p.get("evaluate_rate", "4.8") 
        orders = p.get("last_volume", "50+")
        link = get_short_link(p.get("product_detail_url"))
        
        images.append(p.get("product_main_image_url"))
        
        # === כאן התיקון הגדול: קישור פתוח וברור ===
        final_text += f"{i+1}. 🥇 {title_clean}\n"
        final_text += f"💰 מחיר: {price}₪ | ⭐ {rating} | 🛒 {orders}\n"
        final_text += f"{link}\n\n"  # <--- הקישור הגלוי
        
        kb.add(types.InlineKeyboardButton(f"🛍️ מוצר {i+1}", url=link))

    bot.delete_message(m.chat.id, msg.message_id)

    if images:
        try:
            collage = create_collage(images)
            bot.send_photo(m.chat.id, collage, caption=final_text, parse_mode="HTML", reply_markup=kb)
        except:
            bot.send_message(m.chat.id, final_text, parse_mode="HTML", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, final_text, parse_mode="HTML", reply_markup=kb)

print("Bot is running with OPEN LINKS & SMART SEARCH...")
bot.infinity_polling()
