# ==========================================
# DrDeals Premium – FINAL STABLE FIX 🛠️
# ==========================================
import telebot
import requests
import time
import hashlib
import logging
import io
import sys
from telebot import types
from PIL import Image, ImageDraw
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# נסיון לייבא תרגום
try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False

# ==========================================
# ⚙️ הגדרות
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
bot = telebot.TeleBot(BOT_TOKEN)

session = requests.Session()
retry = Retry(connect=3, backoff_factor=1, status_forcelist=[500,502,503,504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('https://', adapter)

# ==========================================
# 🧠 רשימות אימות (WhiteList)
# ==========================================
VALIDATORS = {
    'מעיל': ['coat', 'jacket', 'parka', 'outerwear', 'blazer'],
    'רחפן': ['drone', 'quadcopter', 'uav'],
    'שעון': ['watch', 'smartwatch', 'band'],
    'אוזניות': ['headphone', 'earphone', 'earbuds', 'headset'],
    'תיק': ['bag', 'handbag', 'wallet', 'backpack', 'purse'],
    'נעליים': ['shoe', 'sneaker', 'boot', 'sandal', 'heels']
}

COLORS = {
    'שמנת': 'Beige', 'בז': 'Beige', 'קרם': 'Beige', 'חול': 'Khaki',
    'לבן': 'White', 'שחור': 'Black', 'אדום': 'Red', 
    'כחול': 'Blue', 'ירוק': 'Green', 'ורוד': 'Pink', 
    'צהוב': 'Yellow', 'חום': 'Brown', 'אפור': 'Grey'
}

# ==========================================
# 🔧 פונקציות ליבה
# ==========================================
def safe_translate(text, target='en'):
    if not HAS_TRANSLATOR: return text
    try:
        return GoogleTranslator(source='auto', target=target).translate(text)
    except:
        return text

def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query):
    params = {
        "app_key": APP_KEY, "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "format": "json",
        "sign_method": "md5", "v": "2.0", "partner_id": "top-autopilot",
        "keywords": query, "target_currency": "ILS", "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC", "page_size": "50", "min_sale_price": "15"
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
        # בדיקה קריטית: האם הקישור קיים?
        final_link = link.get("promotion_short_link") or link.get("promotion_link")
        return final_link if final_link else clean # מחזיר את המקור אם הקיצור נכשל
    except: 
        return clean # מחזיר את המקור במקרה של שגיאה

def create_collage(urls):
    imgs = []
    for u in urls[:4]:
        try:
            resp = session.get(u, timeout=5)
            img = Image.open(io.BytesIO(resp.content)).resize((500,500))
            imgs.append(img)
        except: 
            imgs.append(Image.new("RGB",(500,500),"white"))
    
    while len(imgs)<4: imgs.append(Image.new("RGB",(500,500),"white"))
    
    canvas = Image.new("RGB",(1000,1000),"white")
    canvas.paste(imgs[0],(0,0)); canvas.paste(imgs[1],(500,0))
    canvas.paste(imgs[2],(0,500)); canvas.paste(imgs[3],(500,500))
    
    draw = ImageDraw.Draw(canvas)
    for i, (x,y) in enumerate([(30,30), (530,30), (30,530), (530,530)]):
        draw.ellipse((x,y,x+70,y+70),fill="#FFD700",outline="black",width=3)
        draw.text((x+25,y+15),str(i+1),fill="black", font_size=40)
        
    out = io.BytesIO()
    canvas.save(out,"JPEG",quality=85)
    out.seek(0)
    return out

def clean_title(title):
    try: title_he = safe_translate(title, 'iw')
    except: title_he = title
    garbage = ["2024", "2025", "New", "Fashion", "Women", "Men", "Arrival", "Shipping", "Free", "חדש", "אופנה", "משלוח חינם"]
    for g in garbage: title_he = title_he.replace(g, "")
    return " ".join(title_he.split()[:10])

def is_valid_product(product, query_he):
    title_lower = product.get("product_title", "").lower()
    bad_words = ["screw", "repair", "tool", "adapter", "connector", "pipe", "hair clipper", "trimmer", "parts"]
    if any(b in title_lower for b in bad_words): return False

    for key, valid_list in VALIDATORS.items():
        if key in query_he:
            if not any(v in title_lower for v in valid_list):
                return False
    return True

# ==========================================
# 🚀 בוט ראשי
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    try:
        if not m.text.startswith("חפש לי"): return
        query_he = m.text.replace("חפש לי","").strip()
        msg = bot.reply_to(m, f"🔎 מעבד: {query_he}...")
        bot.send_chat_action(m.chat.id, "typing")

        color_en = ""
        for h, e in COLORS.items():
            if h in query_he: color_en = e
        
        base_en = safe_translate(query_he, 'en')
        extra = "Fashion" if "מעיל" in query_he or "שמלה" in query_he else ""
        final_query = f"{base_en} {color_en} {extra}".strip()
        
        products = get_ali_products(final_query)
        valid_products = [p for p in products if is_valid_product(p, query_he)]

        if not valid_products:
            bot.edit_message_text("🛑 לא נמצאו תוצאות תקינות.", m.chat.id, msg.message_id)
            return

        top_4 = valid_products[:4]
        images = []
        text = f"🛍️ **תוצאות עבור: {query_he}**\n\n"
        kb = types.InlineKeyboardMarkup()

        for i, p in enumerate(top_4):
            title = clean_title(p["product_title"])
            price = p.get("target_sale_price", "?")
            rating = p.get("evaluate_rate", "4.8")
            orders = p.get("last_volume", "100+")
            
            # --- התיקון הקריטי כאן ---
            raw_link = p.get("product_detail_url")
            link = get_short_link(raw_link)
            
            # אם אין לינק תקין - מדלגים על המוצר ולא יוצרים כפתור
            if not link:
                continue

            images.append(p.get("product_main_image_url"))
            
            text += f"{i+1}. 🥇 {title}\n"
            text += f"💰 מחיר: {price}₪ | ⭐ {rating} | 🛒 {orders}\n"
            text += f"{link}\n\n"
            
            # יצירת הכפתור רק אם יש לינק בטוח
            kb.add(types.InlineKeyboardButton(text=f"🛍️ מוצר {i+1}", url=link))

        bot.delete_message(m.chat.id, msg.message_id)
        
        if images:
            try:
                collage = create_collage(images)
                bot.send_photo(m.chat.id, collage, caption=text, parse_mode="HTML", reply_markup=kb)
            except:
                bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)
        else:
            bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)

    except Exception as e:
        error_msg = f"❌ שגיאה: {str(e)}"
        print(error_msg)
        bot.send_message(m.chat.id, "אירעה שגיאה זמנית בחיפוש. נסה שוב.")

print("Bot is running - STABLE VERSION...")
bot.infinity_polling(timeout=10, long_polling_timeout=5)
