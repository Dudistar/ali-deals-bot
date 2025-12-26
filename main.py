import telebot
import requests
import time
import re
import os
import io
import hashlib
import statistics
import google.generativeai as genai
from telebot import types
from PIL import Image, ImageDraw

# ==========================================
# ⚙️ הגדרות מערכת
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
ADMIN_ID = 173837076

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
else:
    print("⚠️ Warning: No GEMINI_API_KEY found.")

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🧠 שלב 1: הבלש (Smart Query Optimizer)
# ==========================================
def smart_query_optimizer(user_text):
    """
    מנתח את כוונת המשתמש ומתרגם לאנגלית טכנית נקייה.
    מסיר מילות נימוס ומתמקד במוצר.
    """
    if not GEMINI_API_KEY:
        try:
            from deep_translator import GoogleTranslator
            return GoogleTranslator(source='auto', target='en').translate(user_text)
        except:
            return user_text

    prompt = f"""
    ROLE: Expert eCommerce Keyword Extractor.
    INPUT: "{user_text}" (Hebrew).
    
    GOAL: Translate to precise English keywords for AliExpress search.
    
    RULES:
    1. IGNORE polite words ("find me", "I want", "please", "buy").
    2. DETECT the core object.
    3. BRANDING: If user says model number (e.g. "S24"), ADD the brand ("Samsung").
    4. OUTPUT: 2-5 English keywords ONLY. No sentences.
    
    Example:
    In: "חפש לי מגן לאייפון 13" -> Out: iPhone 13 Case
    In: "רחפן עם מצלמה" -> Out: Professional Camera Drone
    """
    try:
        response = model.generate_content(prompt)
        cleaned = response.text.strip().replace('"', '').replace("'", "")
        return cleaned
    except:
        return user_text

# ==========================================
# 🎣 שלב 2: הרשת הרחבה (API Fetcher)
# ==========================================
def get_ali_products(cleaned_query):
    """
    מושך 100 מוצרים מאליאקספרס כדי שיהיה לנו מבחר גדול לסינון.
    """
    if not cleaned_query or len(cleaned_query) < 2: return []

    params = {
        'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
        'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
        'keywords': cleaned_query, 
        'target_currency': 'ILS', 'ship_to_country': 'IL',
        'sort': 'LAST_VOLUME_DESC', 
        'page_size': '100',  # משיכה רחבה!
    }
    params['sign'] = generate_sign(params)
    try:
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
        data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(data, dict): data = [data]
        return data
    except: return []

# ==========================================
# 💎 שלב 3: הסלקטור (Math + AI Filter)
# ==========================================
def filter_candidates(products, query_en):
    """
    משלב סינון מתמטי (להסרת זבל זול) וסינון AI (להסרת אביזרים לא רלוונטיים).
    """
    if not products: return []
    
    # --- תת-שלב א': סינון מתמטי ---
    # הסרת מילים אסורות ברורות
    hard_blacklist = ["sticker", "decal", "skin", "screw", "part", "cable protector"]
    
    valid_prices = []
    first_pass = []
    
    for p in products:
        title = p.get('product_title', '').lower()
        try: price = float(p.get('target_sale_price', 0))
        except: price = 0
        
        if any(bad in title for bad in hard_blacklist): continue
        if price > 0:
            valid_prices.append(price)
            first_pass.append(p)
            
    if not first_pass: return []

    # חישוב חציון וניפוי ה-20% התחתונים (הזולים ביותר)
    if len(valid_prices) > 5:
        median_price = statistics.median(valid_prices)
        threshold = median_price * 0.2 # כל מה שמתחת ל-20% מהחציון עף
        candidates = [p for p in first_pass if float(p.get('target_sale_price', 0)) >= threshold]
    else:
        candidates = first_pass

    # מיון לפי מחיר (הנחה: הדבר האמיתי יקר יותר)
    candidates.sort(key=lambda x: float(x.get('target_sale_price', 0)), reverse=True)
    
    # שולחים ל-AI רק את ה-25 היקרים והטובים ביותר
    ai_candidates = candidates[:25]

    if not GEMINI_API_KEY: return ai_candidates[:4]

    # --- תת-שלב ב': סינון AI קפדני ---
    list_text = "\n".join([f"ID {i}: {p['product_title']} (Price: {p.get('target_sale_price', '0')})" for i, p in enumerate(ai_candidates)])
    
    prompt = f"""
    User Query: "{query_en}"
    
    ROLE: Quality Control & Relevance Expert.
    TASK: Select only the MAIN PRODUCT requested.
    
    STRICT RULES:
    1. ACCESSORY TRAP: If user wants a device (Phone, Drone, Watch), REJECT all "Case", "Strap", "Charger", "Glass".
       - ONLY accept accessories if the user EXPLICITLY asked for "Case" or "Strap".
    2. PRICE LOGIC: Use the provided price. If it's too cheap to be the main device -> REJECT.
    3. RELEVANCE: If the item is totally unrelated -> REJECT.
    
    List to filter:
    {list_text}
    
    OUTPUT: JSON array of IDs for the BEST matches. Example: [0, 2, 5]
    """
    try:
        response = model.generate_content(prompt)
        ids = [int(s) for s in re.findall(r'\b\d+\b', response.text)]
        final_list = [ai_candidates[i] for i in ids if i < len(ai_candidates)]
        
        # אם ה-AI היה קשוח מידי ולא החזיר כלום, נחזיר את הטופ מהסינון המתמטי
        if not final_list:
            return ai_candidates[:4]
            
        return final_list[:4]
    except:
        return ai_candidates[:4]

# ==========================================
# 🛠️ כלי עזר (Link, Translate, Image, Sign)
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

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
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10).json()
        res = resp.get('aliexpress_affiliate_link_generate_response', {}).get('resp_result', {}).get('result', {}).get('promotion_links', {}).get('promotion_link', [])
        if res: return res[0].get('promotion_short_link') or res[0].get('promotion_link')
    except: pass
    return clean_url

def translate_to_hebrew(text):
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target='iw').translate(text)
    except: return text

def create_collage(image_urls):
    images = []
    for url in image_urls[:4]:
        try:
            r = requests.get(url, timeout=5)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
            images.append(img)
        except: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
    while len(images) < 4: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
    
    collage = Image.new('RGB', (1000, 1000), 'white')
    positions = [(0,0), (500,0), (0,500), (500,500)]
    for i, img in enumerate(images):
        collage.paste(img, positions[i])
    
    # הוספת מספרים לתמונה
    draw = ImageDraw.Draw(collage)
    for i, pos in enumerate(positions):
        if i < len(image_urls):
            x, y = pos
            draw.ellipse((x+20, y+20, x+80, y+80), fill="#FFD700", outline="black", width=3)
            draw.text((x+42, y+35), str(i+1), fill="black", font_size=50)
            
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

def notify_admin(user, query):
    if not ADMIN_ID: return
    try:
        username = f"@{user.username}" if user.username else ""
        msg = f"🕵️‍♂️ **חיפוש חדש:**\n👤 {user.first_name} {username}\n🔍 {query}"
        bot.send_message(ADMIN_ID, msg)
    except: pass

# ==========================================
# 📱 הנדלרים (Handlers)
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    welcome_msg = (
        "✨ <b>ברוכים הבאים ל-DrDeals Premium</b> 💎\n\n"
        "אני הבוט החכם לקניות באליאקספרס.\n"
        "במקום להציף אתכם בתוצאות זבל, אני חושב, מסנן ובוחר רק את הטובים ביותר.\n\n"
        "👇 <b>איך משתמשים?</b>\n"
        "פשוט כתבו <b>'חפש לי'</b> ואת שם המוצר.\n"
        "למשל: 'חפש לי רחפן DJI', 'חפש לי אוזניות ספורט'."
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("חפש לי רחפן", "חפש לי אוזניות", "חפש לי שעון חכם", "❓ עזרה וטיפים")
    bot.send_message(m.chat.id, welcome_msg, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=['help'])
def help_command(m):
    bot.send_message(m.chat.id, "💡 <b>טיפ:</b> התחילו כל חיפוש ב-**'חפש לי'** כדי שאדע שאתם רציניים.", parse_mode="HTML")

@bot.message_handler(func=lambda m: "עזרה" in m.text)
def handle_help_text(m):
    help_command(m)

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    if "חפש לי" not in m.text: 
        if len(m.text) > 3: bot.reply_to(m, "💡 כדי להתחיל, כתבו **'חפש לי'** ואת שם המוצר.")
        return

    raw_query = m.text.replace("חפש לי", "").strip()
    notify_admin(m.from_user, raw_query)
    
    # הודעת "חושב" ראשונה
    status_msg = bot.send_message(m.chat.id, f"🔍 <b>מתחיל בסריקה עבור: {raw_query}...</b>", parse_mode="HTML")
    
    # שלב 1: תרגום וניתוח
    optimized_query = smart_query_optimizer(raw_query)
    bot.edit_message_text(f"🧠 <b>הבנתי, מחפש: {optimized_query}...</b>", m.chat.id, status_msg.message_id, parse_mode="HTML")
    
    # שלב 2: משיכה רחבה
    raw_products = get_ali_products(optimized_query)
    if not raw_products: # נסיון גיבוי
        raw_products = get_ali_products(raw_query)

    if not raw_products:
        bot.delete_message(m.chat.id, status_msg.message_id)
        bot.send_message(m.chat.id, "❌ לא מצאתי מוצרים מתאימים.")
        return

    # שלב 3: סינון חכם
    bot.edit_message_text(f"💎 <b>מסנן איכות וזיופים...</b>", m.chat.id, status_msg.message_id, parse_mode="HTML")
    final_list = filter_candidates(raw_products, optimized_query)
    
    bot.delete_message(m.chat.id, status_msg.message_id)

    if not final_list:
         bot.send_message(m.chat.id, f"🤔 לא מצאתי מוצר ראשי התואם לחיפוש '{raw_query}'. (מצאתי בעיקר אביזרים)")
         return

    # בניית התשובה
    try:
        image_urls = [p.get('product_main_image_url') for p in final_list]
        collage = create_collage(image_urls)
        bot.send_photo(m.chat.id, collage, caption=f"🏆 <b>הבחירות המובילות: {raw_query}</b>", parse_mode="HTML")
        
        full_text = ""
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for i, p in enumerate(final_list):
            title_he = translate_to_hebrew(p.get('product_title'))
            price = float(p.get('target_sale_price', 0))
            link = get_short_link(p.get('product_detail_url'))
            
            if not link or len(str(link)) < 10: continue

            full_text += f"{i+1}. 🏅 <b>{title_he[:55]}...</b>\n"
            full_text += f"💰 מחיר: <b>{price}₪</b>\n"
            full_text += f"🔗 {link}\n\n"
            
            markup.add(types.InlineKeyboardButton(text=f"🛍️ לקנייה (מוצר {i+1})", url=link))
            
        full_text += "💎 <b>DrDeals Premium Selection</b>"
        bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        
    except Exception as e:
        bot.send_message(m.chat.id, "שגיאה טכנית בהצגת התוצאות.")

bot.infinity_polling()
