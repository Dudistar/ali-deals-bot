import telebot
import requests
import time
import re
import os
import io
import hashlib
import html
import google.generativeai as genai
from telebot import types
from PIL import Image, ImageDraw

# ניסיון לייבא תרגום
try:
    from deep_translator import GoogleTranslator
except ImportError:
    pass

# ==========================================
# הגדרות ופרטים אישיים
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
GEMINI_API_KEY = "AIzaSyDNkixE64pO0muWxcqD2qtwZbTiH9UHT7w"
ADMIN_ID = 173837076

# חיבור ל-AI (מודל יציב שעובד בטוח)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# פונקציות ליבה (מנוע)
# ==========================================

def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

def get_short_link(raw_url):
    # פונקציה ליצירת לינק מקוצר ונקי
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

def create_collage(image_urls):
    # יצירת קולאז' תמונות יפה
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
    draw = ImageDraw.Draw(collage)
    
    for i, img in enumerate(images):
        collage.paste(img, positions[i])
        if i < len(image_urls):
            x, y = positions[i]
            # עיגול צהוב עם מספר
            draw.ellipse((x+20, y+20, x+70, y+70), fill="#FFD700", outline="black", width=2)
            draw.text((x+38, y+30), str(i+1), fill="black", font_size=40)
            
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

def get_products_from_ali(query):
    # תרגום לאנגלית לחיפוש (המנוע של אליאקספרס עובד טוב יותר באנגלית)
    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query).lower()
    except:
        query_en = query

    params = {
        'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
        'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
        'keywords': query_en, 'target_currency': 'ILS', 'ship_to_country': 'IL',
        'sort': 'LAST_VOLUME_DESC', 'page_size': '20', 
    }
    params['sign'] = generate_sign(params)
    
    try:
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
        data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {})
        products = data.get('products', {}).get('product', [])
        if isinstance(products, dict): products = [products]
        return products, query_en
    except Exception as e:
        return [], str(e)

def filter_with_ai(products, user_query):
    if not products: return []
    
    # בניית רשימה ל-AI
    text_list = "\n".join([f"ID {i}: {p['product_title']} (Price: {p['target_sale_price']})" for i, p in enumerate(products)])
    
    # ההוראה ל-AI: תהיה קשוח ותעיף זבל
    prompt = f"""
    User search: "{user_query}"
    Task: Select ONLY the main product requested.
    
    CRITICAL RULES:
    1. If user wants a "Drone", EXCLUDE: propellers, motors, batteries, cables, connectors, lights. Return ONLY the flying drone.
    2. If user wants "Pants", EXCLUDE: shorts, underwear, pajamas.
    3. If user wants "Phone", EXCLUDE: cases, glass, cables.
    
    Product List:
    {text_list}
    
    Return ONLY the ID numbers of the correct items, separated by commas (e.g., 0, 2, 5).
    """
    
    try:
        response = model.generate_content(prompt)
        # חילוץ מספרים נקי
        ids = [int(s) for s in re.findall(r'\b\d+\b', response.text)]
        clean_list = [products[i] for i in ids if i < len(products)]
        return clean_list
    except Exception as e:
        print(f"AI Error: {e}")
        return []

# ==========================================
# הנדלרים (התנהגות הבוט)
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    welcome_text = (
        "👋 <b>ברוכים הבאים ל-DrDeals!</b>\n"
        "הבוט החכם שמשלב AI כדי למצוא לכם את הדילים הכי טובים.\n\n"
        "👇 <b>מה תרצו לחפש היום?</b>"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("חפש לי רחפן", "חפש לי אוזניות", "חפש לי שעון חכם", "חפש לי מצלמה")
    bot.send_message(m.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle(m):
    if "חפש לי" not in m.text: return
    query = m.text.replace("חפש לי", "").strip()
    
    bot.send_chat_action(m.chat.id, 'typing')
    loading = bot.send_message(m.chat.id, f"🤖 <b>ה-AI מנתח מוצרים עבור: {query}...</b>", parse_mode="HTML")
    
    # 1. משיכה מאליאקספרס
    raw_products, query_en = get_products_from_ali(query)
    
    if not raw_products:
        bot.delete_message(m.chat.id, loading.message_id)
        bot.send_message(m.chat.id, "❌ לא נמצאו מוצרים כלל.")
        return

    # 2. סינון AI
    final_products = filter_with_ai(raw_products, query_en)
    
    # גיבוי: אם ה-AI נכשל או החמיר מדי, קח את ה-4 הנמכרים ביותר
    if not final_products:
         final_products = raw_products[:4]
    
    # לוקחים רק את ה-4 הכי טובים
    final_products = final_products[:4]
    bot.delete_message(m.chat.id, loading.message_id)

    # 3. בניית ההודעה המושקעת (עם HTML, עברית וכפתורים)
    try:
        # קולאז'
        image_urls = [p.get('product_main_image_url') for p in final_products]
        collage = create_collage(image_urls)
        
        bot.send_photo(m.chat.id, collage, caption=f"💎 <b>נבחרת הדילים: {query}</b>", parse_mode="HTML")
        
        # טקסט מפורט
        msg_text = ""
        buttons = []
        markup = types.InlineKeyboardMarkup(row_width=1)

        for i, p in enumerate(final_products):
            # תרגום כותרת לעברית
            title_orig = p.get('product_title')
            try: title_he = GoogleTranslator(source='auto', target='iw').translate(title_orig)
            except: title_he = title_orig
            
            price = p.get('target_sale_price')
            orig_price = p.get('target_original_price')
            
            # חישוב הנחה
            discount_str = ""
            try:
                p_float = float(price)
                o_float = float(orig_price)
                if o_float > p_float:
                    d = int(((o_float - p_float) / o_float) * 100)
                    discount_str = f" | 📉 <b>{d}% הנחה!</b>"
            except: pass
            
            short_link = get_short_link(p.get('product_detail_url'))
            
            # בניית שורה למוצר
            msg_text += f"{i+1}. 🏆 <b>{html.escape(title_he[:55])}...</b>\n"
            msg_text += f"💰 מחיר: <b>{price}₪</b>{discount_str}\n"
            msg_text += f"🔗 <a href='{short_link}'>לחץ לפרטים נוספים</a>\n\n"
            
            # כפתור
            buttons.append(types.InlineKeyboardButton(text=f"🎁 לקנייה (מוצר {i+1})", url=short_link))

        msg_text += "🛍️ <b>קנייה מהנה! | DrDeals</b>"
        
        # הוספת הכפתורים
        for btn in buttons:
            markup.add(btn)

        bot.send_message(m.chat.id, msg_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        
    except Exception as e:
        bot.send_message(m.chat.id, f"שגיאה בהצגת התוצאות: {e}")

bot.infinity_polling()
