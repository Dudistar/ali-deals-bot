import telebot
import requests
import time
import re
import os
import io
import hashlib
import statistics
from telebot import types
from PIL import Image, ImageDraw

# ==========================================
# הגדרות מערכת
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
ADMIN_ID = 173837076

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# פונקציות בטוחות
# ==========================================

def safe_float(value):
    try:
        if not value: return 0.0
        clean = str(value).replace('US', '').replace('$', '').replace('₪', '').strip()
        return float(clean)
    except: return 0.0

def generate_sign(params):
    try:
        s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
        return hashlib.md5(s.encode('utf-8')).hexdigest().upper()
    except: return ""

def translate_to_hebrew(text):
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target='iw').translate(text)
    except: return text

def translate_to_english(text):
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target='en').translate(text)
    except: return text

# ==========================================
# שליפת מוצרים
# ==========================================
def get_ali_products(query):
    query_en = translate_to_english(query)
    
    params = {
        'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
        'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
        'keywords': query_en, 
        'target_currency': 'ILS', 'ship_to_country': 'IL',
        'sort': 'LAST_VOLUME_DESC', 
        'page_size': '50', 
    }
    params['sign'] = generate_sign(params)
    
    try:
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10).json()
        data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(data, dict): data = [data]
        return data
    except: return []

# ==========================================
# 🛡️ פונקציות הסינון (בלי הגבלת מחיר!)
# ==========================================
def filter_products(products):
    if not products: return []
    
    # רשימה שחורה רק לזבל אמיתי (ברגים, מדבקות, חלקים פנימיים)
    # הסרתי את כל חסימות המחיר!
    blacklist = [
        "sticker", "decal", "screw", "part", "glass film", "screen protector",
        "propeller", "landing gear", "motor arm", "battery", "replacement"
    ]
    
    clean = []
    
    for p in products:
        title = p.get('product_title', '').lower()
        
        # 1. בדיקת מילים אסורות (רק זבל טכני)
        if any(bad in title for bad in blacklist): continue
        
        # >> כאן היה הסינון מחיר - והוא נמחק! <<
        
        clean.append(p)
        
    # אם הסינון מחק את הכל, מחזירים את המקוריים
    if not clean:
        products.sort(key=lambda x: safe_float(x.get('target_sale_price', 0)), reverse=True)
        return products[:4]
        
    # מיון לפי מחיר (היקר למעלה) כדי שלפחות הטובים יהיו ראשונים, אבל גם הזולים שם
    clean.sort(key=lambda x: safe_float(x.get('target_sale_price', 0)), reverse=True)
    
    return clean[:4]

# ==========================================
# יצירת תמונות ולינקים
# ==========================================
def get_short_link(raw_url):
    if not raw_url: return None
    clean_url = raw_url.split('?')[0]
    try:
        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.link.generate',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'promotion_link_type': '0', 'source_values': clean_url, 'tracking_id': TRACKING_ID
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=5).json()
        result = resp.get('aliexpress_affiliate_link_generate_response', {}).get('resp_result', {}).get('result', {}).get('promotion_links', {}).get('promotion_link', [])
        if result: return result[0].get('promotion_short_link') or result[0].get('promotion_link')
    except: pass
    return clean_url

def create_collage(image_urls):
    try:
        images = []
        for url in image_urls[:4]:
            try:
                r = requests.get(url, timeout=3)
                img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
                images.append(img)
            except: 
                images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
        
        while len(images) < 4: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
        
        collage = Image.new('RGB', (1000, 1000), 'white')
        positions = [(0,0), (500,0), (0,500), (500,500)]
        draw = ImageDraw.Draw(collage)
        
        for i, img in enumerate(images):
            collage.paste(img, positions[i])
            if i < len(image_urls):
                x, y = positions[i]
                draw.ellipse((x+20, y+20, x+80, y+80), fill="#FFD700", outline="black", width=3)
                draw.text((x+42, y+35), str(i+1), fill="black", font_size=50)
        
        output = io.BytesIO()
        collage.save(output, format='JPEG', quality=85)
        output.seek(0)
        return output
    except: return None

# ==========================================
# הבוט עצמו
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    welcome_msg = (
        "✨ <b>ברוכים הבאים ל-DrDeals Premium</b> 💎\n\n"
        "הבוט שימצא לכם את הדילים השווים ביותר באליאקספרס.\n\n"
        "👇 <b>כדי להתחיל, כתבו:</b>\n"
        "'חפש לי' ואת שם המוצר (למשל: 'חפש לי רחפן')"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("חפש לי רחפן", "חפש לי אוזניות", "חפש לי שעון חכם", "❓ עזרה וטיפים")
    
    try:
        if os.path.exists('welcome.jpg'):
            with open('welcome.jpg', 'rb') as p:
                bot.send_photo(m.chat.id, p, caption=welcome_msg, parse_mode="HTML", reply_markup=markup)
        else:
            bot.send_message(m.chat.id, welcome_msg, parse_mode="HTML", reply_markup=markup)
    except:
        bot.send_message(m.chat.id, welcome_msg, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    if "חפש לי" not in m.text:
        if len(m.text) > 3: bot.reply_to(m, "💡 נא לכתוב **'חפש לי'** לפני שם המוצר.")
        return

    query = m.text.replace("חפש לי", "").strip()
    
    msg = bot.send_message(m.chat.id, f"🔍 <b>מחפש עבור: {query}...</b>", parse_mode="HTML")
    
    # 1. שליפה
    products = get_ali_products(query)
    
    if not products:
        bot.edit_message_text("❌ לא נמצאו מוצרים. נסה חיפוש אחר.", m.chat.id, msg.message_id)
        return

    # 2. סינון (בלי הגבלת מחיר!)
    final_list = filter_products(products)
    
    bot.delete_message(m.chat.id, msg.message_id)

    # 3. בניית התשובה
    image_urls = []
    full_text = ""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for i, p in enumerate(final_list):
        title = translate_to_hebrew(p.get('product_title', 'Product'))
        price = safe_float(p.get('target_sale_price', 0))
        orig_price = safe_float(p.get('target_original_price', 0))
        link = get_short_link(p.get('product_detail_url'))
        
        if not link: continue
        
        discount_txt = ""
        if orig_price > price:
            percent = int(((orig_price - price) / orig_price) * 100)
            discount_txt = f" | 📉 <b>{percent}% הנחה</b>"

        image_urls.append(p.get('product_main_image_url'))
        
        full_text += f"{i+1}. 🏅 <b>{title[:50]}...</b>\n"
        full_text += f"💰 מחיר: <b>{price}₪</b>{discount_txt}\n"
        full_text += f"🔗 {link}\n\n"
        
        markup.add(types.InlineKeyboardButton(f"🛍️ לרכישת מוצר {i+1}", url=link))
    
    if image_urls:
        collage = create_collage(image_urls)
        if collage:
            bot.send_photo(m.chat.id, collage, caption=f"🏆 <b>הבחירות המובילות: {query}</b>", parse_mode="HTML")
    
    full_text += "💎 <b>DrDeals Premium Selection</b>"
    bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

bot.infinity_polling()
