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
# ⚙️ הגדרות מערכת ולוגים
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
ADMIN_ID = 173837076
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# הגדרת סשן יציב למניעת ניתוקים
session = requests.Session()
retry = Retry(connect=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

# בדיקת זמינות AI
HAS_GEMINI = False
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        HAS_GEMINI = True
    except ImportError:
        logging.warning("Google GenAI library missing.")

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🛡️ פונקציות עזר מוגנות
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
# 🧠 שלב 1: הבלש (Query Optimizer)
# ==========================================
def smart_query_optimizer(user_text):
    """מתרגם ומזקק את הבקשה לאנגלית טכנית"""
    if HAS_GEMINI:
        try:
            prompt = f"""
            Task: Extract specific AliExpress search keywords from Hebrew text.
            Input: "{user_text}"
            Rules:
            1. Output ONLY the English product name.
            2. Remove polite words ("I want", "find").
            3. If user specifies a model (e.g. "Buds 3 Pro"), ADD the brand ("Samsung").
            Output format: Keywords only.
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
# 🎣 שלב 2: הרשת (API Fetcher)
# ==========================================
def get_ali_products(cleaned_query):
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
# 💎 שלב 3: הסלקטור (Strict AI Filter)
# ==========================================
def filter_candidates(products, query_en):
    if not products: return []
    
    blacklist = ["sticker", "decal", "skin", "screw", "protector film"]
    clean_products = []
    prices = []
    
    for p in products:
        title = p.get('product_title', '').lower()
        price = safe_float(p.get('target_sale_price', 0))
        
        if any(bad in title for bad in blacklist): continue
        if price > 0:
            clean_products.append(p)
            prices.append(price)

    if not clean_products: return []

    if len(prices) > 5:
        median_price = statistics.median(prices)
        threshold = median_price * 0.3
        clean_products = [p for p in clean_products if safe_float(p.get('target_sale_price', 0)) >= threshold]

    clean_products.sort(key=lambda x: safe_float(x.get('target_sale_price', 0)), reverse=True)
    candidates = clean_products[:20]

    if not HAS_GEMINI: return candidates[:4]

    list_text = "\n".join([f"ID {i}: {p['product_title']} (Price: {p.get('target_sale_price', '0')})" for i, p in enumerate(candidates)])
    
    prompt = f"""
    User Query: "{query_en}"
    Task: Identify the MAIN DEVICE only.
    STRICT RULES:
    1. REJECT "Case", "Strap", "Silicone", "Cover" unless explicitly asked.
    2. REJECT unrelated items.
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
# 🛠️ כלי עזר (Link, Collage)
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
# 🚀 בוט ראשי (העיצוב המקורי חזר!)
# ==========================================
@bot.message_handler(commands=['start'])
def start(m):
    # החזרת העיצוב היוקרתי המקורי
    welcome_msg = (
        "✨ <b>ברוכים הבאים ל-DrDeals Premium</b> | הדור הבא של הקניות 💎\n\n"
        "נעים להכיר, אני עוזר הקניות האישי שלכם.\n"
        "נמאס לכם לקבל מוצרים זולים וחיקויים? גם לי.\n\n"
        "🧠 <b>איך אני שומר עליכם?</b>\n"
        "פיתחתי מנוע AI חכם שסורק אלפי מוצרים, מזהה את **האיכותיים ביותר**,\n"
        "ומסנן עבורכם את כל השאר. אתם תקבלו רק את הטופ של הטופ.\n\n"
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
    help_text = (
        "💎 <b>מדריך לחיפוש איכותי</b>\n\n"
        "✅ <b>כתבו 'חפש לי' ואז את שם המוצר:</b>\n"
        "• 'חפש לי מצלמה לרכב שיאומי'\n"
        "• 'חפש לי שעון חכם עמיד למים'\n\n"
    )
    bot.send_message(m.chat.id, help_text, parse_mode="HTML")

@bot.message_handler(func=lambda m: "עזרה" in m.text)
def handle_help_text(m):
    help_command(m)

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
        bot.edit_message_text("❌ לא נמצאו מוצרים. נסה חיפוש אחר.", m.chat.id, msg.message_id)
        return

    bot.edit_message_text(f"💎 <b>ה-AI מסנן זיופים ואביזרים...</b>", m.chat.id, msg.message_id, parse_mode="HTML")
    final_list = filter_candidates(products, query_en)
    
    bot.delete_message(m.chat.id, msg.message_id)

    if not final_list:
        bot.send_message(m.chat.id, "🤔 מצאתי רק אביזרים נלווים, לא את המוצר הראשי.")
        return

    image_urls = []
    full_text = ""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # בניית התשובה המעוצבת (עם הנחות ומחירים מקוריים)
    for i, p in enumerate(final_list):
        title = translate_to_hebrew(p.get('product_title', 'Product'))
        price = safe_float(p.get('target_sale_price', 0))
        orig_price = safe_float(p.get('target_original_price', 0))
        link = get_short_link(p.get('product_detail_url'))
        
        if not link or not link.startswith('http'): continue
        
        # חישוב הנחה
        discount_txt = ""
        if orig_price > price:
            percent = int(((orig_price - price) / orig_price) * 100)
            discount_txt = f" | 📉 <b>{percent}% הנחה</b>"

        image_urls.append(p.get('product_main_image_url'))
        
        full_text += f"{i+1}. 🏅 <b>{title[:55]}...</b>\n"
        full_text += f"💰 מחיר: <b>{price}₪</b>{discount_txt}\n"
        full_text += f"🔗 {link}\n\n"
        
        markup.add(types.InlineKeyboardButton(f"🛍️ לרכישת מוצר {i+1}", url=link))
    
    if image_urls:
        collage = create_collage(image_urls)
        if collage:
            bot.send_photo(m.chat.id, collage, caption=f"🏆 <b>הבחירות המובילות: {raw_query}</b>", parse_mode="HTML")
    
    full_text += "💎 <b>DrDeals Premium Selection</b>"
    bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

bot.infinity_polling()
