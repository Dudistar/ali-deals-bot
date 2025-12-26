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

try:
    from deep_translator import GoogleTranslator
except ImportError:
    pass

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
    try:
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

# --- פונקציית תרגום חכמה ומשוריינת ---
def smart_query_optimizer(user_text):
    # נסיון 1: AI של גוגל
    if GEMINI_API_KEY:
        try:
            prompt = f"""
            Translate this Hebrew search term to simple English keywords for AliExpress.
            Input: "{user_text}"
            Rules:
            1. Remove polite words ("Find me", "I want").
            2. Keep brand names and model numbers exact.
            3. Output ONLY the English keywords.
            """
            response = model.generate_content(prompt)
            if response.text:
                return response.text.strip()
        except:
            pass # אם נכשל, עוברים הלאה

    # נסיון 2: תרגום רגיל
    try:
        translated = GoogleTranslator(source='auto', target='en').translate(user_text)
        return translated
    except:
        pass
    
    # נסיון 3: המקור
    return user_text

def get_ali_products(cleaned_query):
    # אם הקוורי ריק, לא שולחים בקשה כדי לא לקבל זבל
    if not cleaned_query or len(cleaned_query) < 2:
        return []

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

def filter_with_snob_ai(products, query_en):
    if not products: return []
    
    # 1. סינון בסיסי (גיליוטינה)
    blacklist = ["propeller", "part", "screw", "sticker"]
    clean_products = []
    for p in products:
        title = p.get('product_title', '').lower()
        if any(bad in title for bad in blacklist): continue
        clean_products.append(p)
    
    # אם אין מספיק מוצרים נקיים, מחזירים את המקוריים (אלא אם זה זבל מוחלט)
    if len(clean_products) < 2: clean_products = products

    # לוקחים את החצי היקר יותר (כדי לסנן פיצ'יפקעס)
    clean_products.sort(key=lambda x: float(x.get('target_sale_price', 0)), reverse=True)
    candidates = clean_products[:len(clean_products)//2]
    
    # גיבוי למקרה שנשארנו בלי כלום
    if not candidates: candidates = clean_products[:5]

    if not GEMINI_API_KEY: return candidates[:4]

    # 2. סינון AI חכם לבדיקת רלוונטיות
    list_text = "\n".join([f"ID {i}: {p['product_title']} (Price: {p.get('target_sale_price', '0')})" for i, p in enumerate(candidates[:15])])
    prompt = f"""
    User Query: "{query_en}"
    Task: Select items that MATCH the query.
    Rules: 
    1. REJECT items that are completely unrelated to "{query_en}".
    2. REJECT cheap parts/toys if the user asked for a main device.
    List:
    {list_text}
    Output: IDs like 0, 2. If nothing matches, output EMPTY.
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

    # מנקים את הבקשה מה"חפש לי"
    raw_query = m.text.replace("חפש לי", "").strip()
    notify_admin(m.from_user, raw_query)
    
    bot.send_chat_action(m.chat.id, 'typing')
    loading = bot.send_message(m.chat.id, f"💎 <b>מנתח בקשה: {raw_query}...</b>", parse_mode="HTML")
    
    # תרגום חכם לאנגלית (חובה כדי למנוע תוצאות זבל)
    optimized_query = smart_query_optimizer(raw_query)
    
    # משיכת מוצרים
    raw_products = get_ali_products(optimized_query)
    
    # אם לא מצאנו כלום בחיפוש הראשון, מנסים חיפוש נוסף עם המקור
    if not raw_products:
         raw_products = get_ali_products(raw_query)

    if not raw_products:
        bot.delete_message(m.chat.id, loading.message_id)
        bot.send_message(m.chat.id, "❌ לא מצאתי מוצרים רלוונטיים.")
        return

    # סינון איכות + רלוונטיות
    final_list = filter_with_snob_ai(raw_products, optimized_query)
    bot.delete_message(m.chat.id, loading.message_id)

    # אם הסינון החכם מחק את הכל כי זה היה זבל (מכונות תספורת כשביקשת צירים)
    if not final_list:
         msg = (
             f"🤔 <b>לא מצאתי תוצאות מדוייקות עבור: {raw_query}</b>\n\n"
             "המוצרים שמצאתי לא היו קשורים מספיק למה שביקשת.\n"
             "נסה לכתוב את שם המוצר באנגלית או בצורה אחרת."
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
            
            # בדיקה קריטית: אם אין לינק תקין, מדלגים (מונע קריסה)
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
