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
# הגדרות מערכת
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
# פונקציות ליבה
# ==========================================

def notify_admin(user, query):
    if not ADMIN_ID: return
    try:
        username = f"@{user.username}" if user.username else "ללא שם משתמש"
        msg = (
            f"🕵️‍♂️ **התראה למנהל:**\n"
            f"👤 **משתמש:** {user.first_name} ({username})\n"
            f"🔍 **חיפש:** {query}"
        )
        bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
    except Exception as e:
        print(f"Error notifying admin: {e}")

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
    except:
        return text

def create_collage(image_urls):
    images = []
    for url in image_urls[:4]:
        try:
            r = requests.get(url, timeout=5)
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
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

def smart_query_optimizer(user_text):
    if GEMINI_API_KEY:
        try:
            prompt = f"""
            Role: eCommerce Search Expert.
            Input: "{user_text}" (Hebrew).
            Action: 
            1. Identify the CORE PRODUCT (Device/Item).
            2. Translate to precise English.
            3. IGNORE polite words ("find", "buy", "please").
            4. IF specific model (e.g. "A73") -> Expand to "Samsung Galaxy A73 Phone".
            Output: English keywords ONLY.
            """
            response = model.generate_content(prompt)
            if response.text:
                return response.text.strip()
        except:
            pass
            
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target='en').translate(user_text)
    except:
        return user_text

def get_ali_products(cleaned_query):
    if not cleaned_query or len(cleaned_query) < 2: return []

    # הגדלנו את כמות המוצרים ל-100 כדי לתת לסינון יותר "בשר" לעבוד עליו
    params = {
        'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
        'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
        'keywords': cleaned_query, 
        'target_currency': 'ILS', 'ship_to_country': 'IL',
        'sort': 'LAST_VOLUME_DESC', 
        'page_size': '100',  # שאיבה של יותר מוצרים
    }
    params['sign'] = generate_sign(params)
    try:
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
        data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(data, dict): data = [data]
        return data
    except: return []

def filter_with_snob_ai(products, query_en):
    if not products: return []
    
    # שלב 1: ניקוי ידני גס
    blacklist = ["sticker", "decal", "skin", "screw", "part"]
    clean_products = []
    
    # חישוב חציון מחיר כדי לזהות זבל זול מידי
    prices = [float(p.get('target_sale_price', 0)) for p in products if float(p.get('target_sale_price', 0)) > 0]
    if not prices: return []
    median_price = statistics.median(prices)
    min_price_threshold = median_price * 0.3 # מוצרים שעולים פחות מ-30% מהממוצע חשודים כזבל
    
    for p in products:
        title = p.get('product_title', '').lower()
        price = float(p.get('target_sale_price', 0))
        
        if any(bad in title for bad in blacklist): continue
        if price < min_price_threshold: continue # זול מידי
        
        clean_products.append(p)
    
    # אם הסינון הידני היה אגרסיבי מידי, נשחרר קצת
    if len(clean_products) < 5: 
        clean_products = products[:20]
    else:
        # מיון לפי מחיר (מהיקר לזול - הנחה שהמוצר האמיתי יקר מהאביזר)
        clean_products.sort(key=lambda x: float(x.get('target_sale_price', 0)), reverse=True)
        clean_products = clean_products[:30] # שולחים ל-AI את ה-30 היקרים והטובים

    if not GEMINI_API_KEY: return clean_products[:4]

    # שלב 2: סינון AI עמוק
    list_text = "\n".join([f"ID {i}: {p['product_title']} (Price: {p.get('target_sale_price', '0')})" for i, p in enumerate(clean_products)])
    
    prompt = f"""
    Search Query: "{query_en}"
    
    Task: Filter AliExpress results.
    GOAL: Find the MAIN ITEM the user wants.
    
    STRICT FILTERING RULES:
    1. REJECT ACCESSORIES: If user wants "Phone", reject "Case". If "Drone", reject "Propeller".
    2. REJECT UNRELATED: If item is completely different category -> REJECT.
    3. PRICE LOGIC: The main item is usually the most expensive in the list. Low price = Accessory.
    
    List:
    {list_text}
    
    Output: JSON array of valid IDs only. Example: [0, 3, 5]
    """
    try:
        response = model.generate_content(prompt)
        # שימוש בביטוי רגולרי למציאת מספרים בלבד, ליתר ביטחון
        ids = [int(s) for s in re.findall(r'\b\d+\b', response.text)]
        
        ai_filtered = [clean_products[i] for i in ids if i < len(clean_products)]
        
        # אם ה-AI לא מצא כלום (מחמיר מידי), נחזיר את היקרים ביותר מהסינון הידני
        if not ai_filtered:
            return clean_products[:4]
            
        return ai_filtered 
    except: 
        return clean_products[:4]

# ==========================================
# הנדלרים
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    notify_admin(m.from_user, "לחץ START")
    welcome_msg = (
        "✨ <b>ברוכים הבאים ל-DrDeals Premium</b> 💎\n\n"
        "אני העוזר האישי שלכם לקניות חכמות.\n"
        "כדי להתחיל, פשוט כתבו <b>'חפש לי'</b> ואת שם המוצר.\n\n"
        "👇 <b>דוגמאות:</b>\n"
        "• חפש לי מגן לאייפון 14\n"
        "• חפש לי רחפן עם מצלמה\n"
        "• חפש לי שעון חכם"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("חפש לי רחפן", "חפש לי אוזניות", "חפש לי שעון חכם", "❓ עזרה וטיפים")
    
    if os.path.exists('welcome.jpg'):
        try:
            with open('welcome.jpg', 'rb') as photo:
                bot.send_photo(m.chat.id, photo, caption=welcome_msg, parse_mode="HTML", reply_markup=markup)
        except:
            bot.send_message(m.chat.id, welcome_msg, parse_mode="HTML", reply_markup=markup)
    else:
        bot.send_message(m.chat.id, welcome_msg, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=['help'])
def help_command(m):
    help_text = (
        "💎 <b>טיפים לחיפוש</b>\n"
        "✅ התחילו ב-**'חפש לי'**\n"
        "✅ היו ספציפיים (למשל: 'חפש לי מטען מקורי לסמסונג')"
    )
    bot.send_message(m.chat.id, help_text, parse_mode="HTML")

@bot.message_handler(func=lambda m: "עזרה" in m.text)
def handle_help_text(m):
    help_command(m)

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    if "חפש לי" not in m.text: 
        if len(m.text) > 3: bot.reply_to(m, "💡 כדי להתחיל חיפוש, אנא התחילו את המשפט במילים **'חפש לי'**.")
        return

    raw_query = m.text.replace("חפש לי", "").strip()
    notify_admin(m.from_user, raw_query)
    bot.send_chat_action(m.chat.id, 'typing')
    
    # שלב 1: הצגת הודעת פתיחה דינמית
    status_msg = bot.send_message(m.chat.id, f"🔍 <b>מתחיל בסריקה עבור: {raw_query}...</b>", parse_mode="HTML")
    
    # שלב 2: תרגום ומיקוד
    optimized_query = smart_query_optimizer(raw_query)
    bot.edit_message_text(f"🇺🇸 <b>ממקד חיפוש: {optimized_query}...</b>", m.chat.id, status_msg.message_id, parse_mode="HTML")
    
    # שלב 3: שליפה (הגדלנו ל-100 מוצרים אז זה לוקח שניה)
    raw_products = get_ali_products(optimized_query)
    
    if not raw_products:
        # נסיון שני אם הראשון נכשל
        raw_products = get_ali_products(raw_query)

    if not raw_products:
        bot.delete_message(m.chat.id, status_msg.message_id)
        bot.send_message(m.chat.id, "❌ לא מצאתי מוצרים. נסו חיפוש באנגלית.")
        return

    # שלב 4: סינון עמוק
    bot.edit_message_text(f"🧠 <b>מפעיל סינון איכות (מסיר זיופים ואביזרים)...</b>", m.chat.id, status_msg.message_id, parse_mode="HTML")
    final_list = filter_with_snob_ai(raw_products, optimized_query)
    
    # מחיקת הודעת הסטטוס לפני הצגת התוצאות
    bot.delete_message(m.chat.id, status_msg.message_id)

    if not final_list:
         msg = (
             f"🤔 <b>לא מצאתי בדיוק את מה שחיפשת ({raw_query})</b>\n\n"
             "המוצרים שמצאתי היו בעיקר אביזרים נלווים ולא המכשיר עצמו.\n"
         )
         bot.send_message(m.chat.id, msg, parse_mode="HTML")
         return

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
            
            if not link or len(str(link)) < 10:
                continue

            full_text += f"{i+1}. 🏅 <b>{title_he[:55]}...</b>\n"
            full_text += f"💰 מחיר: <b>{price}₪</b>\n"
            full_text += f"🔗 {link}\n\n"
            
            btn = types.InlineKeyboardButton(text=f"🛍️ לקנייה (מוצר {i+1})", url=link)
            markup.add(btn)
            
        full_text += "💎 <b>DrDeals Premium Selection</b>"
        bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        
    except Exception as e:
        bot.send_message(m.chat.id, f"שגיאה בהצגת התוצאות: {e}")

bot.infinity_polling()
