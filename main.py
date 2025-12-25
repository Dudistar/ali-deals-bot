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

# משיכת מפתח מהכספת
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
    # כאן נשתמש ב-Deep Translator כגיבוי לתרגום מהיר של כותרות
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

# --- הפונקציה החדשה: המוח שמתרגם כוונות למילות חיפוש ---
def smart_query_optimizer(user_text):
    if not GEMINI_API_KEY: return user_text
    
    prompt = f"""
    Act as an AliExpress Search Expert.
    Convert the following Hebrew user request into a specific, short English search query.
    1. Remove politeness words like "find me", "look for", "I want", "buy".
    2. Focus on the product name and model.
    3. If the user specifies a model (like 'A73'), assume the full name (e.g., 'Samsung Galaxy A73').
    
    User Input: "{user_text}"
    
    Output ONLY the English keywords (e.g., "Samsung A73 Phone Case"). No quotes.
    """
    try:
        response = model.generate_content(prompt)
        optimized_query = response.text.strip()
        print(f"Original: {user_text} -> Optimized: {optimized_query}") # לוג לשרת
        return optimized_query
    except Exception as e:
        print(f"AI Query Error: {e}")
        return user_text # במקרה חירום נחזיר את המקור

def get_ali_products(cleaned_query):
    # הפונקציה כבר מקבלת קוורי נקי באנגלית מה-AI
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
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
        data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(data, dict): data = [data]
        return data
    except: return []

def the_guillotine_filter(products):
    if not products or len(products) < 5: return products
    
    blacklist = ["strobe", "light", "lamp", "propeller", "battery", "part", "accessory", "cable", "case", "cover", "gift", "toy", "mini"]
    # הערה: הסרנו את case ו-cover מרשימת השחורים כי המשתמש מחפש כיסוי!
    # נשאיר רשימה מצומצמת יותר של זבל אמיתי
    blacklist = ["propeller", "part", "gift", "toy", "screw", "sticker"]
    
    clean_products = []
    
    for p in products:
        title = p.get('product_title', '').lower()
        if any(bad in title for bad in blacklist):
            continue
        clean_products.append(p)
    
    if len(clean_products) < 2: 
        clean_products = products
    
    clean_products.sort(key=lambda x: float(x.get('target_sale_price', 0)), reverse=True)
    half_index = len(clean_products) // 2
    premium_half = clean_products[:half_index]
    
    if not premium_half:
        return clean_products[:4]
        
    return premium_half

def filter_with_snob_ai(products, query_en):
    if not products: return []
    if not GEMINI_API_KEY: return products[:4]

    candidates = the_guillotine_filter(products)
    
    list_text = "\n".join([f"ID {i}: {p['product_title']} (Price: {p.get('target_sale_price', '0')})" for i, p in enumerate(candidates[:15])])
    
    prompt = f"""
    You are a Shopping Assistant.
    User Query: "{query_en}"
    Task: Pick the BEST matching items.
    
    STRICT RULES:
    1. RELEVANCE IS KING: If items are NOT "{query_en}", REJECT THEM. 
       (Example: If query is 'Phone Case' and item is 'Car Armrest', REJECT).
    2. REJECT cheap toys or parts.
    3. Look at the Price: If it looks too cheap, REJECT IT.
    
    List:
    {list_text}
    
    Output: Only the IDs of the best items (e.g., 0, 2). If nothing matches, return empty.
    """
    try:
        response = model.generate_content(prompt)
        ids = [int(s) for s in re.findall(r'\b\d+\b', response.text)]
        ai_filtered = [candidates[i] for i in ids if i < len(candidates)]
        return ai_filtered
    except: 
        return candidates[:4]

# ==========================================
# הנדלרים
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    notify_admin(m.from_user, "לחץ START")
    
    welcome_msg = (
        "✨ <b>ברוכים הבאים ל-DrDeals Premium</b> | חווית קניות חכמה 💎\n\n"
        "אני משתמש ב-AI כדי להבין בדיוק מה אתם צריכים, לא משנה איך תבקשו את זה.\n"
        "פשוט כתבו <b>'חפש לי'</b> ואת שם המוצר, ואני אמצא את הטוב ביותר.\n\n"
        "👇 <b>דוגמאות:</b>\n"
        "• חפש לי מגן לאייפון 14\n"
        "• חפש לי רחפן עם מצלמה\n"
        "• חפש לי אוזניות ספורט"
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
        "💎 <b>טיפים לחיפוש</b>\n\n"
        "כדי לקבל את התוצאות הטובות ביותר:\n"
        "✅ התחילו ב-**'חפש לי'**\n"
        "✅ היו ספציפיים (למשל: 'מטען מקורי לסמסונג' במקום 'מטען')\n"
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

    # מנקים את הבקשה מה"חפש לי" כדי שיהיה נקי לעין, אבל ה-AI יעשה את העבודה האמיתית
    raw_query = m.text.replace("חפש לי", "").strip()
    
    notify_admin(m.from_user, raw_query)
    bot.send_chat_action(m.chat.id, 'typing')
    
    # --- כאן המהפכה: ה-AI מבין מה המוצר לפני החיפוש ---
    loading = bot.send_message(m.chat.id, f"🧠 <b>מנתח את הבקשה: {raw_query}...</b>", parse_mode="HTML")
    optimized_query_en = smart_query_optimizer(raw_query)
    
    # מעדכנים את המשתמש שאנחנו מחפשים את מה שהוא באמת רצה (למשל Samsung A73 Case)
    bot.edit_message_text(f"💎 <b>מחפש את הטופ עבור: {optimized_query_en}...</b>", m.chat.id, loading.message_id, parse_mode="HTML")
    
    raw_products = get_ali_products(optimized_query_en)
    
    if not raw_products:
        bot.delete_message(m.chat.id, loading.message_id)
        bot.send_message(m.chat.id, "❌ לא מצאתי מוצרים. נסו חיפוש כללי יותר.")
        return

    final_list = filter_with_snob_ai(raw_products, optimized_query_en)
    bot.delete_message(m.chat.id, loading.message_id)

    if not final_list:
         msg = (
             f"🤔 <b>לא מצאתי תוצאות איכותיות לחיפוש: {optimized_query_en}</b>\n\n"
             "המוצרים שנמצאו היו לא רלוונטיים או באיכות נמוכה."
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
            
            if not link: continue

            full_text += f"{i+1}. 🏅 <b>{title_he[:55]}...</b>\n"
            full_text += f"💰 מחיר: <b>{price}₪</b>\n"
            full_text += f"🔗 {link}\n\n"
            
            btn = types.InlineKeyboardButton(text=f"🛍️ לרכישת המומלץ מס' {i+1}", url=link)
            markup.add(btn)
            
        full_text += "💎 <b>DrDeals Premium Selection</b>"
        bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        
    except Exception as e:
        bot.send_message(m.chat.id, f"שגיאה: {e}")

bot.infinity_polling()
