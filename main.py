# ==========================================
# DrDeals Premium – The "Elma" Competitor
# ==========================================
import telebot
import requests
import time
import hashlib
import logging
import io
import re
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
# 🧠 מילון צבעים וסגנונות (לדיוק מקסימלי)
# ==========================================
COLORS = {
    'שמנת': 'Beige', 'בז': 'Beige', 'קרם': 'Beige', 'חול': 'Khaki',
    'לבן': 'White', 'שחור': 'Black', 'אדום': 'Red', 'כחול': 'Blue',
    'ירוק': 'Green', 'ורוד': 'Pink', 'חום': 'Brown', 'אפור': 'Grey'
}

# רשימת מילים שחובה שיהיו במוצר (Whitelist)
# אם המשתמש מחפש "מעיל", המוצר חייב להכיל אחת מהמילים באנגלית
PRODUCT_VALIDATORS = {
    'מעיל': ['coat', 'jacket', 'parka', 'trench', 'blazer', 'outerwear'],
    'רחפן': ['drone', 'quadcopter', 'uav'],
    'שעון': ['watch', 'smartwatch'],
    'אוזניות': ['headphone', 'earphone', 'headset', 'earbuds'],
    'תיק': ['bag', 'handbag', 'purse', 'wallet', 'backpack'],
    'נעליים': ['shoe', 'sneaker', 'boot', 'sandal', 'heel']
}

# ==========================================
# 🔐 חתימה ורשת
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products(query, min_price="20"):
    # חיפוש רחב ומקיף
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
        "sort": "LAST_VOLUME_DESC", # מיון לפי פופולריות
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
# 🧹 המנקה והמסנן (The Processor)
# ==========================================
def clean_title_hebrew(title_en):
    """
    פונקציה שמנסה לחקות את ה-AI של המתחרה.
    היא לוקחת כותרת ארוכה ומבולגנת ומשאירה רק את ה"בשר".
    """
    # 1. תרגום
    try:
        title_he = GoogleTranslator(source='auto', target='iw').translate(title_en)
    except:
        return title_en

    # 2. ניקוי מילים שיווקיות מיותרות
    garbage = ["חדש", "2024", "2025", "משלוח חינם", "הגעה", "אופנה", "נשים", "גברים", "יוקרה", "באיכות גבוהה", "טרנד", "סגנון"]
    for word in garbage:
        title_he = title_he.replace(word, "")
    
    # 3. קיצור
    words = title_he.split()
    if len(words) > 8:
        return " ".join(words[:8]) + "..."
    return " ".join(words)

def validate_product(product, original_query_he):
    title_lower = product.get("product_title", "").lower()
    
    # 1. הגנה גלובלית (כלי עבודה)
    global_ban = ["screw", "repair", "tool", "connector", "adapter", "pipe", "accessory", "part", "kit"]
    if any(bad in title_lower for bad in global_ban): return False

    # 2. אימות ספציפי (Whitelist)
    # אם המשתמש חיפש "מעיל", אנחנו מוודאים שכתוב Coat/Jacket
    for key, valid_words in PRODUCT_VALIDATORS.items():
        if key in original_query_he:
            if not any(good in title_lower for good in valid_words):
                return False # זה לא המוצר שהמשתמש ביקש!
    
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
    for u in urls[:4]: # ננסה 4 תמונות כמו המתחרה
        try:
            img = Image.open(io.BytesIO(session.get(u, timeout=5).content)).resize((500,500))
        except: img = Image.new("RGB",(500,500),"white")
        imgs.append(img)
    
    # השלמה ל-4
    while len(imgs)<4: imgs.append(Image.new("RGB",(500,500),"white"))
    
    # יצירת קולאז' 2x2
    canvas = Image.new("RGB",(1000,1000),"white")
    canvas.paste(imgs[0],(0,0))
    canvas.paste(imgs[1],(500,0))
    canvas.paste(imgs[2],(0,500))
    canvas.paste(imgs[3],(500,500))
    
    # מספור
    draw = ImageDraw.Draw(canvas)
    # מיקומים: שמאל-למעלה, ימין-למעלה, שמאל-למטה, ימין-למטה
    positions = [(30,30), (530,30), (30,530), (530,530)]
    for i, (x,y) in enumerate(positions):
        draw.ellipse((x,y,x+70,y+70),fill="#FFD700",outline="black",width=3)
        draw.text((x+25,y+15),str(i+1),fill="black", font_size=40) # פונט גדול יותר

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
    
    # שלב 1: חיווי מיידי (כמו המתחרה)
    msg = bot.reply_to(m, f"🔎 מחפש את הטובים ביותר עבור: {query_he}...")
    bot.send_chat_action(m.chat.id, "typing")

    # שלב 2: עיבוד חכם של השאילתה
    color_en = ""
    for heb_col, eng_col in COLORS.items():
        if heb_col in query_he:
            color_en = eng_col
            break
            
    # תרגום בסיסי + הוספת צבע
    try:
        base_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except:
        base_en = query_he
        
    final_query = f"{base_en} {color_en}".strip()
    
    # שלב 3: משיכה (לוקח זמן...)
    time.sleep(1.5) # השהייה מלאכותית כדי לתת תחושת "חשיבה"
    products = get_ali_products(final_query)
    
    # שלב 4: סינון קפדני (The Enforcer)
    valid_products = []
    for p in products:
        if validate_product(p, query_he):
            valid_products.append(p)
    
    if not valid_products:
        bot.edit_message_text("🛑 לא מצאתי תוצאות שעומדות בסטנדרט האיכות (סיננתי מוצרים לא רלוונטיים).", m.chat.id, msg.message_id)
        return

    # שלב 5: הכנת התוצאה הסופית (עיצוב כמו המתחרה)
    top_4 = valid_products[:4]
    images = []
    
    # כותרת מעוצבת
    final_text = f"🧥 <b>נמצאו {len(top_4)} מוצרים מובילים עבורך!</b>\n\n"
    
    kb = types.InlineKeyboardMarkup()
    
    for i, p in enumerate(top_4):
        # כותרת נקייה
        title_clean = clean_title_hebrew(p["product_title"])
        price = p.get("target_sale_price", "?")
        rating = p.get("evaluate_rate", "4.8") # אם אין, נשים ברירת מחדל גבוהה
        orders = p.get("last_volume", "100+")
        link = get_short_link(p.get("product_detail_url"))
        
        images.append(p.get("product_main_image_url"))
        
        # עיצוב מודעה כמו המתחרה
        final_text += f"{i+1}. 🥇 {title_clean}\n"
        final_text += f"*💰 מחיר:* {price}₪\n"
        final_text += f"*⭐ דירוג:* {rating}\n"
        final_text += f"*🛒 רכישות:* {orders}\n"
        final_text += f"🔗 [לחץ לרכישה]({link})\n\n"
        
        kb.add(types.InlineKeyboardButton(f"🛍️ מוצר {i+1} - {price}₪", url=link))

    # מחיקת הודעת "מחפש..."
    bot.delete_message(m.chat.id, msg.message_id)

    # שליחת קולאז' + טקסט
    if images:
        try:
            collage = create_collage(images)
            bot.send_photo(m.chat.id, collage, caption=final_text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            bot.send_message(m.chat.id, final_text, parse_mode="Markdown", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, final_text, parse_mode="Markdown", reply_markup=kb)

print("Bot is running in 'Competitor Mode'...")
bot.infinity_polling()
