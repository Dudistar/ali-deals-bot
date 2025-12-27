import telebot
import requests
import time
import re
import os
import io
import hashlib
import statistics
import logging
import json
import random
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
# 🔒 מיפוי קטגוריות
# ==========================================
CATEGORY_MAP = {
    'coat': '200001901', 'jacket': '200001901', 'מעיל': '200001901',
    'drone': '200002649', 'רחפן': '200002649',
    'watch': '200000095', 'שעון': '200000095',
    'headphones': '63705', 'earphones': '63705', 'אוזניות': '63705',
    'phone': '2000023', 'smartphone': '2000023', 'טלפון': '2000023',
    'dress': '200003482', 'שמלה': '200003482',
    'shoes': '322', 'נעליים': '322'
}

def get_category_id(user_query):
    for key, cat_id in CATEGORY_MAP.items():
        if key in user_query.lower():
            return cat_id
    return None

# ==========================================
# 🛠️ פונקציות עזר
# ==========================================
def safe_float(value):
    try:
        clean = str(value).replace('US', '').replace('$', '').replace('₪', '').strip()
        return float(clean)
    except: return 0.0

def translate_to_hebrew(text):
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target='iw').translate(text)
    except: return text

def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

# ==========================================
# 🛑 פילטר ברזל (Keyword Guard)
# ==========================================
def keyword_guard(product_title, query_english):
    """
    זה השומר בכניסה. אם המילה 'Coat' לא מופיעה בכותרת המוצר,
    המוצר נזרק לפח. נקודה.
    """
    title_lower = product_title.lower()
    query_parts = query_english.lower().split()
    
    # מסננים מילים קצרות מידי (כמו "for", "in")
    significant_keywords = [w for w in query_parts if len(w) > 2]
    
    if not significant_keywords: return True # אם אין מילים לבדוק, מעבירים (מסוכן, אבל נדיר)
    
    # האם לפחות מילה אחת משמעותית מופיעה בכותרת?
    # אם חיפשת "Elegant Coat", והמוצר הוא "Aluminum Tool", אין התאמה.
    for word in significant_keywords:
        if word in title_lower:
            return True
            
    return False

# ==========================================
# 🧠 שלב 1: הבלש (Smart Query)
# ==========================================
def smart_query_optimizer(user_text):
    time.sleep(random.uniform(0.5, 1.5))
    if HAS_GEMINI:
        try:
            prompt = f"""
            Task: Translate Hebrew search to English Keywords.
            Input: "{user_text}"
            Rules:
            1. Output ONLY English.
            2. "Coat" -> "Woman Coat".
            Output: Keywords only.
            """
            response = model.generate_content(prompt)
            if response.text:
                res = response.text.strip().replace('"', '')
                if not any("\u0590" <= char <= "\u05EA" for char in res):
                    return res
        except: pass

    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source='auto', target='en').translate(user_text)
        if translated and not any("\u0590" <= char <= "\u05EA" for char in translated):
            return translated
    except: pass
    return None

# ==========================================
# 🎣 שלב 2: הרשת (API Fetcher)
# ==========================================
def get_ali_products(cleaned_query, category_id=None):
    if not cleaned_query: return []
    
    time.sleep(random.uniform(0.5, 1.5))
    
    params = {
        'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
        'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
        'keywords': cleaned_query, 
        'target_currency': 'ILS', 'ship_to_country': 'IL',
        'sort': 'LAST_VOLUME_DESC', 
        'page_size': '40', 
    }
    if category_id:
        params['category_ids'] = category_id
    
    params['sign'] = generate_sign(params)
    
    try:
        response = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = response.json().get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(data, dict): data = [data]
        return data
    except: return []

# ==========================================
# ✍️ שלב 3: העורך (AI Rewrite + Strict Guard)
# ==========================================
def ai_filter_and_rewrite(products, user_query_hebrew, query_english):
    if not products: return []
    
    # === 1. הפעלת פילטר הברזל ===
    # זורקים כל מוצר שלא מכיל את מילת החיפוש בכותרת שלו
    sane_products = []
    for p in products:
        if keyword_guard(p.get('product_title', ''), query_english):
            sane_products.append(p)
    
    # אם הכל היה זבל (כלי עבודה), הרשימה תהיה ריקה עכשיו.
    # אנחנו מחזירים ריק. לא מחזירים את הזבל!
    if not sane_products:
        return []

    # 2. מיון לפי מחיר
    pre_filtered = []
    for p in sane_products:
        price = safe_float(p.get('target_sale_price', 0))
        if price > 0: pre_filtered.append(p)
            
    pre_filtered.sort(key=lambda x: safe_float(x.get('target_sale_price', 0)), reverse=True)
    candidates = pre_filtered[:10]

    time.sleep(random.uniform(2, 3))

    if not HAS_GEMINI:
        for p in candidates:
            p['ai_title'] = translate_to_hebrew(p.get('product_title'))
        return candidates[:3]

    items_str = ""
    for i, p in enumerate(candidates):
        items_str += f"Item {i}: {p.get('product_title')} | Price: {p.get('target_sale_price')}\n"

    prompt = f"""
    Role: Product Curator.
    User Query: "{user_query_hebrew}"
    
    Task:
    1. FILTER: Is it the correct product? (Coat=Coat).
       - Be FLEXIBLE on colors/styles.
    2. REWRITE: Write a short Hebrew title (max 10 words) with emoji.
    
    Items:
    {items_str}
    
    Output JSON ONLY:
    [
        {{"index": 0, "valid": true, "hebrew_title": "מעיל אלגנטי בצבע קרם 🧥"}},
        {{"index": 1, "valid": false}}
    ]
    """
    try:
        response = model.generate_content(prompt)
        text_resp = response.text.strip().replace("```json", "").replace("```", "")
        ai_decisions = json.loads(text_resp)
        
        final_list = []
        for decision in ai_decisions:
            if decision.get("valid") == True:
                idx = decision.get("index")
                if idx < len(candidates):
                    product = candidates[idx]
                    product['ai_title'] = decision.get("hebrew_title")
                    final_list.append(product)
        
        # אם ה-AI סינן הכל בטעות, אבל המוצרים עברו את "פילטר הברזל" (הם באמת מעילים),
        # אז נחזיר אותם כגיבוי. הפעם זה בטוח כי הם עברו את בדיקת הכותרת!
        if not final_list:
            for p in candidates[:3]:
                 p['ai_title'] = translate_to_hebrew(p.get('product_title'))
            return candidates[:3]

        return final_list[:3]
        
    except Exception as e:
        logging.error(f"AI Error: {e}")
        for p in candidates[:3]:
             p['ai_title'] = translate_to_hebrew(p.get('product_title'))
        return candidates[:3]

# ==========================================
# 🛠️ לינקים וקולאז'
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
        for url in image_urls[:3]:
            try:
                r = session.get(url, timeout=3)
                img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
                images.append(img)
            except: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
        while len(images) < 3: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
        
        collage = Image.new('RGB', (1000, 1000), 'white')
        collage.paste(images[0].resize((1000, 500)), (0, 0))
        collage.paste(images[1].resize((500, 500)), (0, 500))
        collage.paste(images[2].resize((500, 500)), (500, 500))
        
        draw = ImageDraw.Draw(collage)
        positions = [(50,50), (50,550), (550,550)]
        for i, pos in enumerate(positions):
             x, y = pos
             draw.ellipse((x, y, x+60, y+60), fill="#FFD700", outline="black", width=3)
             draw.text((x+20, y+10), str(i+1), fill="black", font_size=40)
        
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
        "הבוט הזה לא מתפשר. או מוצר מדויק או כלום.\n"
        "👇 <b>נסו אותו: 'חפש לי...'</b>"
    )
    bot.send_message(m.chat.id, welcome_msg, parse_mode="HTML")

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    if "חפש לי" not in m.text:
        if len(m.text) > 3: bot.reply_to(m, "💡 נא לכתוב **'חפש לי'** לפני שם המוצר.")
        return

    raw_query = m.text.replace("חפש לי", "").strip()
    notify_admin(m.from_user, raw_query)
    
    bot.send_chat_action(m.chat.id, 'typing')
    msg = bot.send_message(m.chat.id, f"🔍 <b>מנתח בקשה: {raw_query}...</b>", parse_mode="HTML")
    
    cat_id = get_category_id(raw_query)
    query_en = smart_query_optimizer(raw_query)
    
    if not query_en:
        bot.edit_message_text("⚠️ תקלה בתרגום. נסה שוב.", m.chat.id, msg.message_id)
        return

    bot.edit_message_text(f"🌏 <b>סורק מאגרים בינלאומיים...</b>", m.chat.id, msg.message_id, parse_mode="HTML")
    bot.send_chat_action(m.chat.id, 'typing')
    
    products = get_ali_products(query_en, category_id=cat_id)

    if not products:
        bot.edit_message_text("❌ לא נמצאו מוצרים תואמים.", m.chat.id, msg.message_id)
        return

    bot.edit_message_text(f"🧠 <b>ה-AI כותב תיאורים ומסנן זיופים...</b>", m.chat.id, msg.message_id, parse_mode="HTML")
    bot.send_chat_action(m.chat.id, 'typing')
    
    final_list = ai_filter_and_rewrite(products, raw_query, query_en)
    bot.delete_message(m.chat.id, msg.message_id)

    # כאן השינוי הגדול: אם הרשימה ריקה, זה אומר שפילטר הברזל עבד.
    # אנחנו לא מציגים זבל!
    if not final_list:
        bot.send_message(m.chat.id, f"🛑 <b>לא נמצאו תוצאות מדויקות.</b>\nהמוצרים שנמצאו לא הכילו את המילה '{query_en}' בכותרת ולכן סוננו כדי למנוע הצגת מוצרים שגויים.")
        return

    image_urls = []
    full_text = f"🛍️ <b>הבחירות המובילות עבורך:</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for i, p in enumerate(final_list):
        title = p.get('ai_title', translate_to_hebrew(p.get('product_title')))
        price = safe_float(p.get('target_sale_price', 0))
        orig_price = safe_float(p.get('target_original_price', 0))
        sales = p.get('last_volume', 0)
        link = get_short_link(p.get('product_detail_url'))
        
        if not link: continue
        
        discount_txt = ""
        if orig_price > price:
            percent = int(((orig_price - price) / orig_price) * 100)
            if percent > 5: discount_txt = f" | 📉 <b>{percent}% הנחה</b>"

        sales_txt = ""
        if sales and int(sales) > 10: sales_txt = f" | 📦 <b>{sales}+ נרכשו</b>"

        image_urls.append(p.get('product_main_image_url'))
        
        full_text += f"{i+1}. {title}\n"
        full_text += f"💰 <b>{price}₪</b>{discount_txt}{sales_txt}\n"
        full_text += f"🔗 {link}\n\n"
        
        markup.add(types.InlineKeyboardButton(f"🛍️ עבור למוצר {i+1}", url=link))
    
    if image_urls:
        collage = create_collage(image_urls)
        if collage:
            bot.send_photo(m.chat.id, collage, caption=f"🏆 <b>תוצאות: {raw_query}</b>", parse_mode="HTML")
    
    full_text += "💎 <b>DrDeals Premium</b>"
    bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

bot.infinity_polling()
