import telebot
import requests
import time
import re
import os
import io
import hashlib
import statistics
import logging
from telebot import types
from PIL import Image, ImageDraw
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# ==========================================
# ⚙️ הגדרות מערכת
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
ADMIN_ID = 173837076
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

session = requests.Session()
retry = Retry(connect=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

HAS_GEMINI = False
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        HAS_GEMINI = True
    except: pass

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🛡️ פונקציות עזר
# ==========================================
def safe_float(value):
    try:
        if not value: return 0.0
        clean = str(value).replace('US', '').replace('$', '').replace('₪', '').strip()
        return float(clean)
    except: return 0.0

def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

def translate_to_hebrew(text):
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target='iw').translate(text)
    except: return text

# ==========================================
# 🧠 שלב 1: הבלש (Smart Query)
# ==========================================
def smart_query_optimizer(user_text):
    if HAS_GEMINI:
        try:
            prompt = f"""
            Task: Translate Hebrew search to AliExpress English keywords.
            Input: "{user_text}"
            Rules:
            1. Output ONLY the English product name.
            2. IF user asks for "Drone" -> Output "Professional Camera Drone" (to avoid parts).
            3. IF user asks for "Phone" -> Output "Smartphone Global Version".
            4. Remove polite words.
            Output: Keywords only.
            """
            response = model.generate_content(prompt)
            if response.text:
                return response.text.strip().replace('"', '')
        except: pass

    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target='en').translate(user_text)
    except:
        return user_text

# ==========================================
# 🎣 שלב 2: הרשת (API)
# ==========================================
def get_ali_products(cleaned_query):
    # חוזרים ל-50 מוצרים ליציבות
    params = {
        'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
        'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
        'keywords': cleaned_query, 
        'target_currency': 'ILS', 'ship_to_country': 'IL',
        'sort': 'LAST_VOLUME_DESC', 
        'page_size': '50', 
    }
    params['sign'] = generate_sign(params)
    
    try:
        response = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        response.raise_for_status()
        data = response.json().get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(data, dict): data = [data]
        return data
    except: return []

# ==========================================
# 💎 שלב 3: הסלקטור (Strict Filter)
# ==========================================
def filter_candidates(products, query_en):
    if not products: return []
    
    # --- רשימה שחורה טכנית (נגד חלקי חילוף) ---
    # אלו המילים שהפילו אותנו (VTX, מנוע, בקר טיסה)
    tech_blacklist = [
        "vtx", "flight controller", "esc ", "motor", "propeller", 
        "frame kit", "receiver", "antenna", "module", "spare part",
        "sticker", "screw", "case", "film", "strap"
    ]
    
    clean_products = []
    prices = []
    
    for p in products:
        title = p.get('product_title', '').lower()
        price = safe_float(p.get('target_sale_price', 0))
        
        # זריקה מיידית אם זה חלק טכני
        if any(bad in title for bad in tech_blacklist): continue
        
        if price > 0:
            clean_products.append(p)
            prices.append(price)

    if not clean_products: return []

    # סינון מתמטי (רק אם יש מספיק נתונים)
    if len(prices) > 5:
        median_price = statistics.median(prices)
        threshold = median_price * 0.3
        clean_products = [p for p in clean_products if safe_float(p.get('target_sale_price', 0)) >= threshold]

    clean_products.sort(key=lambda x: safe_float(x.get('target_sale_price', 0)), reverse=True)
    candidates = clean_products[:20]

    if not HAS_GEMINI: return candidates[:4]

    # --- סינון AI נגד קומפוננטים ---
    list_text = "\n".join([f"ID {i}: {p['product_title']} (Price: {p.get('target_sale_price', '0')})" for i, p in enumerate(candidates)])
    
    prompt = f"""
    User Query: "{query_en}"
    Task: Find the COMPLETE UNIT, reject PARTS.
    
    RULES:
    1. REJECT COMPONENTS: If user wants "Drone", REJECT "VTX", "Motor", "Frame", "Transmitter", "ESC".
       - Example: "Rush Tank VTX" is a PART. REJECT IT.
    2. REJECT ACCESSORIES: Reject cases, straps, cables.
    3. PRICE LOGIC: A Drone costs $50+. A VTX costs $30. Know the difference.
    
    List:
    {list_text}
    
    Output JSON IDs: [0, 2]
    """
    try:
        response = model.generate_content(prompt)
        ids = [int(s) for s in re.findall(r'\b\d+\b', response.text)]
        final = [candidates[i] for i in ids if i < len(candidates)]
        return final[:4] if final else candidates[:4]
    except:
        return candidates[:4]

# ==========================================
# 🛠️ כלי עזר
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
        resp = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=5).json()
        result = resp.get('aliexpress_affiliate_link_generate_response', {}).get('resp_result', {}).get('result', {}).get('promotion_links', {}).get('promotion_link', [])
        if result: return result[0].get('promotion_short_link') or result[0].get('promotion_link')
    except: pass
    return clean_url

def create_collage(image_urls):
    try:
        images = []
        for url in image_urls[:4]:
            try:
                r = session.get(url, timeout=3)
                img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
                images.append(img)
            except: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
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

def notify_admin(user, query):
    if not ADMIN_ID: return
    try:
        username = f"@{user.username}" if user.username else ""
        msg = f"🕵️‍♂️ **חיפוש:** {query}\n👤 {user.first_name} {username}"
        bot.send_message(ADMIN_ID, msg)
    except: pass

# ==========================================
# 🚀 בוט ראשי
# ==========================================
@bot.message_handler(commands=['start'])
def start(m):
    welcome_msg = (
        "✨ <b>ברוכים הבאים ל-DrDeals Premium</b> 💎\n\n"
        "נעים להכיר, אני עוזר הקניות האישי שלכם.\n"
        "המערכת שלי יודעת לסנן אביזרים וחלקי חילוף ולמצוא את המוצר האמיתי.\n\n"
        "👇 <b>מה תרצו לחפש היום? (כתבו 'חפש לי...')</b>"
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

@bot.message_handler(commands=['help'])
def help_command(m):
    bot.send_message(m.chat.id, "💡 התחילו ב-**'חפש לי'**.", parse_mode="HTML")

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    if "חפש לי" not in m.text:
        if len(m.text) > 3: bot.reply_to(m, "💡 נא לכתוב **'חפש לי'** לפני שם המוצר.")
        return

    raw_query = m.text.replace("חפש לי", "").strip()
    notify_admin(m.from_user, raw_query)
    
    msg = bot.send_message(m.chat.id, f"🔍 <b>בודק: {raw_query}...</b>", parse_mode="HTML")
    
    query_en = smart_query_optimizer(raw_query)
    products = get_ali_products(query_en)
    if not products: products = get_ali_products(raw_query)

    if not products:
        bot.edit_message_text("❌ לא נמצאו מוצרים.", m.chat.id, msg.message_id)
        return

    bot.edit_message_text(f"💎 <b>מסנן חלקי חילוף ואביזרים...</b>", m.chat.id, msg.message_id, parse_mode="HTML")
    final_list = filter_candidates(products, query_en)
    
    bot.delete_message(m.chat.id, msg.message_id)

    if not final_list:
        bot.send_message(m.chat.id, "🤔 מצאתי רק אביזרים/חלקי חילוף ולא את המוצר השלם.")
        return

    image_urls = []
    full_text = ""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for i, p in enumerate(final_list):
        title = translate_to_hebrew(p.get('product_title', 'Product'))
        price = safe_float(p.get('target_sale_price', 0))
        orig_price = safe_float(p.get('target_original_price', 0))
        link = get_short_link(p.get('product_detail_url'))
        
        if not link or not link.startswith('http'): continue
        
        discount_txt = ""
        if orig_price > price:
            percent = int(((orig_price - price) / orig_price) * 100)
            discount_txt = f" | 📉 <b>{percent}% הנחה</b>"

        image_urls.append(p.get('product_main_image_url'))
        full_text += f"{i+1}. 🏅 <b>{title[:55]}...</b>\n💰 מחיר: <b>{price}₪</b>{discount_txt}\n🔗 {link}\n\n"
        markup.add(types.InlineKeyboardButton(f"🛍️ מוצר {i+1}", url=link))
    
    if image_urls:
        collage = create_collage(image_urls)
        if collage:
            bot.send_photo(m.chat.id, collage, caption=f"🏆 <b>הבחירות המובילות: {raw_query}</b>", parse_mode="HTML")
    
    full_text += "💎 <b>DrDeals Premium Selection</b>"
    bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

bot.infinity_polling()
