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
    """מתרגם לאנגלית. אם נכשל ומחזיר עברית - מחזיר None."""
    if HAS_GEMINI:
        try:
            prompt = f"""
            Task: Convert Hebrew user request to AliExpress English Search Keywords.
            Input: "{user_text}"
            Rules:
            1. Output ONLY English.
            2. Be specific (e.g. "Coat" -> "Elegant Woman Wool Coat").
            3. Remove polite words.
            Output: Keywords only.
            """
            response = model.generate_content(prompt)
            if response.text:
                res = response.text.strip().replace('"', '')
                # בדיקה שהתוצאה לא מכילה עברית
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
def get_ali_products(cleaned_query):
    if not cleaned_query: return []
    
    # חזרנו ל-30 מוצרים - אנחנו מעדיפים איכות על כמות
    params = {
        'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
        'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
        'keywords': cleaned_query, 
        'target_currency': 'ILS', 'ship_to_country': 'IL',
        'sort': 'LAST_VOLUME_DESC', 
        'page_size': '30', 
    }
    params['sign'] = generate_sign(params)
    
    try:
        response = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = response.json().get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(data, dict): data = [data]
        return data
    except: return []

# ==========================================
# ✍️ שלב 3: העורך והמסנן (The Slow & Smart Logic)
# ==========================================
def ai_filter_and_rewrite(products, user_query_hebrew):
    """
    זו הפונקציה שיוצרת את ה"השהייה" אבל מביאה תוצאות זהב.
    היא שולחת את המוצרים ל-AI, מבקשת ממנו לסנן זבל, ולכתוב תיאור שיווקי.
    """
    if not products: return []
    
    # הכנה ראשונית: סינון מחיר ורלוונטיות בסיסית
    pre_filtered = []
    for p in products:
        price = safe_float(p.get('target_sale_price', 0))
        if price > 0:
            pre_filtered.append(p)
            
    # מיון לפי מחיר ולקיחת ה-8 היקרים ביותר (הנחה: האיכותיים יקרים יותר)
    pre_filtered.sort(key=lambda x: safe_float(x.get('target_sale_price', 0)), reverse=True)
    candidates = pre_filtered[:8]

    if not HAS_GEMINI:
        # גיבוי למקרה שאין AI - עובד רגיל
        return candidates[:3]

    # --- הקסם מתחיל כאן: שליחה ל-AI לעיבוד ---
    # אנו בונים רשימה ל-AI ומבקשים ממנו פלט בפורמט JSON בלבד
    items_str = ""
    for i, p in enumerate(candidates):
        items_str += f"Item {i}: {p.get('product_title')} | Price: {p.get('target_sale_price')}\n"

    prompt = f"""
    You are a professional Hebrew Copywriter and Quality Filter.
    User Request (Hebrew): "{user_query_hebrew}"
    
    Here is a list of items from AliExpress.
    Your Job:
    1. FILTER: Decide if the item matches the user request strictly.
       - If user wants "Coat" and item is "Tool" -> REJECT.
       - If user wants "Phone" and item is "Case" -> REJECT.
    2. REWRITE: If item is GOOD, write a short, attractive Hebrew title (max 15 words) with an emoji.
       - Style: Marketing, Fun, Clean. NO "Aliexpress translation" style.
    
    Items:
    {items_str}
    
    Output Format: return a JSON list of objects.
    Example:
    [
        {{"index": 0, "valid": true, "hebrew_title": "מעיל צמר יוקרתי בצבע שמנת - מושלם לחורף! 🧥"}},
        {{"index": 1, "valid": false}}
    ]
    RETURN ONLY THE JSON ARRAY.
    """
    
    try:
        response = model.generate_content(prompt)
        text_resp = response.text.strip()
        # ניקוי פורמט אם ה-AI הוסיף ```json
        if "```" in text_resp:
            text_resp = text_resp.replace("```json", "").replace("```", "")
        
        ai_decisions = json.loads(text_resp)
        
        final_list = []
        for decision in ai_decisions:
            if decision.get("valid") == True:
                idx = decision.get("index")
                if idx < len(candidates):
                    # אנחנו מלבישים את הכותרת החדשה של ה-AI על המוצר!
                    product = candidates[idx]
                    product['ai_title'] = decision.get("hebrew_title")
                    final_list.append(product)
        
        return final_list[:3] # מחזירים את ה-3 הכי טובים
        
    except Exception as e:
        logging.error(f"AI Rewrite Error: {e}")
        # במקרה של תקלה ב-AI, מחזירים את המועמדים המקוריים (Fallback)
        return candidates[:3]

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
        for url in image_urls[:3]: # קולאז של 3
            try:
                r = session.get(url, timeout=3)
                img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
                images.append(img)
            except: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
        
        while len(images) < 3: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
        
        # קולאז' של 3 תמונות (1 גדולה, 2 קטנות)
        collage = Image.new('RGB', (1000, 1000), 'white')
        collage.paste(images[0].resize((1000, 500)), (0, 0))
        collage.paste(images[1].resize((500, 500)), (0, 500))
        collage.paste(images[2].resize((500, 500)), (500, 500))
        
        # מספור
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
        "הבוט שלי עובד אחרת: הוא לא סתם מחפש, הוא חושב. 🧠\n"
        "לכן זה לוקח לו כמה שניות – אבל התוצאות שוות את זה.\n\n"
        "👇 <b>נסו אותי: כתבו 'חפש לי' ואת שם המוצר.</b>"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("חפש לי רחפן", "חפש לי מעיל", "חפש לי שעון", "❓ עזרה")
    
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
    
    # 1. חיווי למשתמש שאנחנו עובדים
    bot.send_chat_action(m.chat.id, 'typing')
    msg = bot.send_message(m.chat.id, f"🔍 <b>בודק במאגרים הבינלאומיים עבור: {raw_query}...</b>", parse_mode="HTML")
    
    # 2. תרגום (אנגלית בלבד)
    query_en = smart_query_optimizer(raw_query)
    if not query_en:
        bot.edit_message_text("⚠️ לא הצלחתי לתרגם את הבקשה. נסה ניסוח פשוט יותר.", m.chat.id, msg.message_id)
        return

    # 3. חיפוש
    # משהים קצת כדי לתת תחושה של עבודה מעמיקה (וגם לא לחסום את ה-API)
    time.sleep(1) 
    bot.edit_message_text(f"📥 <b>מושך מוצרים וסורק איכות...</b>", m.chat.id, msg.message_id, parse_mode="HTML")
    products = get_ali_products(query_en)

    if not products:
        bot.edit_message_text("❌ לא נמצאו מוצרים תואמים.", m.chat.id, msg.message_id)
        return

    # 4. המהפכה: שליחה ל-AI לניתוח וכתיבה מחדש
    bot.edit_message_text(f"✍️ <b>ה-AI מנתח וכותב תיאורים בעברית... (זה ייקח רגע)</b>", m.chat.id, msg.message_id, parse_mode="HTML")
    bot.send_chat_action(m.chat.id, 'typing') # מראה שהבוט מקליד
    
    # הפונקציה הזו היא שתיצור את ההשהייה הטבעית ואת האיכות
    final_list = ai_filter_and_rewrite(products, raw_query)
    
    bot.delete_message(m.chat.id, msg.message_id)

    if not final_list:
        bot.send_message(m.chat.id, f"🤔 ה-AI סינן את כל התוצאות כי הן לא היו מדויקות מספיק ל-'{raw_query}'.")
        return

    # 5. הצגה (הפעם עם הטקסט של ה-AI!)
    image_urls = []
    full_text = f"🧥 <b>נמצאו {len(final_list)} תוצאות מעולות עבורך!</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for i, p in enumerate(final_list):
        # שימוש בכותרת שה-AI כתב לנו!
        title = p.get('ai_title', p.get('product_title'))
        price = safe_float(p.get('target_sale_price', 0))
        orig_price = safe_float(p.get('target_original_price', 0))
        link = get_short_link(p.get('product_detail_url'))
        
        if not link: continue
        
        discount_txt = ""
        if orig_price > price:
            percent = int(((orig_price - price) / orig_price) * 100)
            discount_txt = f" | 📉 <b>{percent}% הנחה</b>"

        image_urls.append(p.get('product_main_image_url'))
        
        full_text += f"{i+1}. {title}\n" # הכותרת כבר מכילה אימוג'ים מה-AI
        full_text += f"💰 מחיר: <b>{price}₪</b>{discount_txt}\n"
        full_text += f"🔗 {link}\n\n"
        
        markup.add(types.InlineKeyboardButton(f"🛍️ עבור למוצר {i+1}", url=link))
    
    if image_urls:
        collage = create_collage(image_urls)
        if collage:
            bot.send_photo(m.chat.id, collage, caption=f"🏆 <b>הבחירות של ה-AI</b>", parse_mode="HTML")
    
    full_text += "💎 <b>DrDeals Premium Selection</b>"
    bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

bot.infinity_polling()
