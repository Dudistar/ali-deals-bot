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

def contains_hebrew(text):
    return any("\u0590" <= char <= "\u05EA" for char in text)

# ==========================================
# 🧠 שלב 1: הבלש (Smart Query)
# ==========================================
def smart_query_optimizer(user_text):
    """חייב להחזיר אנגלית. אם נכשל, מחזיר None כדי לא לשלוח זבל."""
    
    # ניסיון 1: AI
    if HAS_GEMINI:
        try:
            prompt = f"""
            Task: Translate to AliExpress English Search Terms.
            Input: "{user_text}"
            Rules:
            1. Output ONLY English.
            2. Remove polite words.
            3. "Cream color" -> "Beige" or "Cream".
            Output: Keywords only.
            """
            response = model.generate_content(prompt)
            if response.text:
                res = response.text.strip().replace('"', '')
                if not contains_hebrew(res): return res
        except: pass

    # ניסיון 2: תרגום רגיל
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source='auto', target='en').translate(user_text)
        if not contains_hebrew(translated): return translated
    except: pass

    # אם נשארנו עם עברית - זה כישלון. עדיף להחזיר כלום מאשר לשלוח עברית לאליאקספרס
    if contains_hebrew(user_text):
        return None
        
    return user_text

# ==========================================
# 🎣 שלב 2: הרשת (API Fetcher)
# ==========================================
def get_ali_products(cleaned_query):
    if not cleaned_query: return []

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
        data = response.json().get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(data, dict): data = [data]
        return data
    except: return []

# ==========================================
# 📊 בדיקת רלוונטיות (Relevance Score)
# ==========================================
def calculate_relevance_score(title, query_words):
    score = 0
    title_lower = title.lower()
    
    # בדיקה האם מילות המפתח מופיעות בכותרת
    matches = 0
    for w in query_words:
        if len(w) > 2 and w in title_lower: # מתעלמים ממילות קישור קצרות
            score += 2
            matches += 1
            
    # אם אין שום התאמה למילים, הציון הוא אפס עגול
    if matches == 0:
        return 0
        
    if len(title_lower.split()) < 15: # בונוס לכותרות נקיות
        score += 1
        
    return score

# ==========================================
# 💎 שלב 3: הסלקטור הקשוח (No Fallback)
# ==========================================
def filter_candidates(products, query_en):
    if not products: return []
    
    query_words = query_en.lower().split()
    scored_products = []
    prices = []
    
    for p in products:
        title = p.get('product_title', '')
        price = safe_float(p.get('target_sale_price', 0))
        if price <= 0: continue
        
        # חישוב ציון
        score = calculate_relevance_score(title, query_words)
        
        # --- השינוי הקריטי: סינון אגרסיבי ---
        # אם הציון הוא 0 (אף מילה לא תואמת), המוצר נזרק לפח.
        # לא שומרים אותו "למקרה חירום". זבל הוא זבל.
        if score > 0:
            scored_products.append({'p': p, 'score': score, 'price': price})
            prices.append(price)

    # אם אחרי הסינון לא נשאר כלום - עדיף להחזיר רשימה ריקה
    # מאשר להחזיר את המוצרים המקוריים (שהם כנראה כלי עבודה)
    if not scored_products:
        return []

    # סינון מחיר (רק אם יש מספיק מוצרים רלוונטיים)
    final_candidates = [item['p'] for item in scored_products]
    if len(prices) > 5:
        median_price = statistics.median(prices)
        threshold = median_price * 0.3
        final_candidates = [item['p'] for item in scored_products if item['price'] >= threshold]

    # מיון לפי מחיר
    final_candidates.sort(key=lambda x: safe_float(x.get('target_sale_price', 0)), reverse=True)
    top_20 = final_candidates[:20]

    if not HAS_GEMINI: return top_20[:4]

    # סינון AI סופי
    list_text = "\n".join([f"ID {i}: {p['product_title']}" for i, p in enumerate(top_20)])
    prompt = f"""
    User Query: "{query_en}"
    Task: Select BEST matches.
    Rules:
    1. REJECT items that don't match the query content (e.g. Tools for a Coat query).
    2. REJECT Accessories/Parts.
    List:
    {list_text}
    Output JSON IDs: [0, 2]
    """
    try:
        response = model.generate_content(prompt)
        ids = [int(s) for s in re.findall(r'\b\d+\b', response.text)]
        final = [top_20[i] for i in ids if i < len(top_20)]
        return final[:4] if final else top_20[:4]
    except:
        return top_20[:4]

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
# 🚀 בוט ראשי
# ==========================================
@bot.message_handler(commands=['start'])
def start(m):
    welcome_msg = (
        "✨ <b>ברוכים הבאים ל-DrDeals Premium</b> 💎\n\n"
        "נעים להכיר, אני עוזר הקניות האישי שלכם.\n"
        "אני משתמש באלגוריתם דירוג חכם 📊 כדי למצוא לכם את המוצר המדויק.\n\n"
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
    bot.send_message(m.chat.id, "💎 <b>טיפ:</b> כתבו **'חפש לי'** ואת שם המוצר המדויק.", parse_mode="HTML")

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
    
    msg = bot.send_message(m.chat.id, f"🔍 <b>מנתח בקשה: {raw_query}...</b>", parse_mode="HTML")
    
    # שלב 1: תרגום חובה (אם נכשל - עוצרים)
    query_en = smart_query_optimizer(raw_query)
    
    if not query_en:
        bot.edit_message_text("⚠️ שגיאת תרגום. אנא נסה לכתוב את המוצר באנגלית.", m.chat.id, msg.message_id)
        return

    # שלב 2: חיפוש
    bot.edit_message_text(f"📊 <b>סורק עבור: {query_en}...</b>", m.chat.id, msg.message_id, parse_mode="HTML")
    products = get_ali_products(query_en)

    if not products:
        bot.edit_message_text("❌ לא נמצאו מוצרים.", m.chat.id, msg.message_id)
        return

    # שלב 3: סינון קשוח
    bot.edit_message_text(f"💎 <b>בוחר את הטובים ביותר...</b>", m.chat.id, msg.message_id, parse_mode="HTML")
    final_list = filter_candidates(products, query_en)
    
    bot.delete_message(m.chat.id, msg.message_id)

    if not final_list:
        # כאן השינוי הגדול: אם הכל סונן (כי הכל היה כלי עבודה), אומרים למשתמש שלא נמצאה התאמה
        bot.send_message(m.chat.id, f"🤔 לא מצאתי מוצרים שתואמים בדיוק ל-'{raw_query}'.\nנסה להיות ספציפי יותר (למשל: 'מעיל צמר נשים').")
        return

    image_urls = []
    full_text = ""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for i, p in enumerate(final_list):
        title_full = translate_to_hebrew(p.get('product_title', 'Product'))
        if len(title_full) > 60:
            title_display = title_full[:60].rsplit(' ', 1)[0] + "..."
        else:
            title_display = title_full

        price = safe_float(p.get('target_sale_price', 0))
        orig_price = safe_float(p.get('target_original_price', 0))
        link = get_short_link(p.get('product_detail_url'))
        
        if not link or not link.startswith('http'): continue
        
        discount_txt = ""
        if orig_price > price:
            percent = int(((orig_price - price) / orig_price) * 100)
            discount_txt = f" | 📉 <b>{percent}%</b>"

        image_urls.append(p.get('product_main_image_url'))
        
        full_text += f"{i+1}. 🏅 <b>{title_display}</b>\n💰 <b>{price}₪</b>{discount_txt}\n🔗 {link}\n\n"
        markup.add(types.InlineKeyboardButton(f"🛍️ מוצר {i+1}", url=link))
    
    if image_urls:
        collage = create_collage(image_urls)
        if collage:
            bot.send_photo(m.chat.id, collage, caption=f"🏆 <b>הבחירות המובילות: {raw_query}</b>", parse_mode="HTML")
    
    full_text += "💎 <b>DrDeals Premium Selection</b>"
    bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

bot.infinity_polling()
