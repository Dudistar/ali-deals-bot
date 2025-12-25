import telebot
import requests
import io
import time
import html
import re
import os
import google.generativeai as genai
from telebot import types
from PIL import Image, ImageDraw

# --- הגדרות ---
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
# המפתח שלך מהתמונה ששלחת
GEMINI_API_KEY = "AIzaSyDNkixE64pO0muWxcqD2qtwZbTiH9UHT7w"

# הגדרת AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

bot = telebot.TeleBot(BOT_TOKEN)

# --- מנוע ---
def generate_sign(params):
    import hashlib
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

def get_products_from_ali(query):
    # חיפוש באליאקספרס
    try:
        from deep_translator import GoogleTranslator
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
    # סינון AI עם דיווח שגיאות
    if not products: return []
    
    text_list = "\n".join([f"ID {i}: {p['product_title']} (Price: {p['target_sale_price']})" for i, p in enumerate(products)])
    
    prompt = f"""
    Query: "{user_query}"
    Task: Return IDs of products that are the MAIN ITEM. 
    Exclude parts, accessories, cheap trash, clothes for wrong gender/age.
    
    Items:
    {text_list}
    
    Return ONLY IDs (e.g., 0, 2, 5).
    """
    
    try:
        response = model.generate_content(prompt)
        # ניסיון לחלץ מספרים
        ids = [int(s) for s in re.findall(r'\b\d+\b', response.text)]
        return [products[i] for i in ids if i < len(products)]
    except Exception as e:
        return f"ERROR: {str(e)}" # מחזיר את השגיאה כטקסט

# --- הנדלרים ---

@bot.message_handler(commands=['start'])
def start(m):
    # שינוי דרמטי כדי שנראה אם זה התעדכן
    msg = (
        "🔴 **בדיקת מערכת חדשה** 🔴\n\n"
        "אם אתה רואה את ההודעה הזאת - הקוד התעדכן!\n"
        "המערכת מחוברת למפתח גוגל שמסתיים ב-HT7w.\n\n"
        "נסה לחפש עכשיו: 'חפש לי מכנסי אלגנט'"
    )
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle(m):
    if "חפש לי" not in m.text: return
    query = m.text.replace("חפש לי", "").strip()
    
    bot.send_message(m.chat.id, "🤖 שולח לגוגל לבדיקה... (וודא ש-requirements.txt מעודכן!)")
    
    # 1. משיכת מוצרים
    raw_products, query_en = get_products_from_ali(query)
    
    if not raw_products:
        bot.send_message(m.chat.id, "❌ תקלה במשיכה מאליאקספרס.")
        return

    # 2. סינון AI
    filtered = filter_with_ai(raw_products, query_en)
    
    # 3. בדיקה אם ה-AI נכשל
    if isinstance(filtered, str) and "ERROR" in filtered:
        # כאן נקבל את הסיבה האמיתית למה זה לא עבד!
        bot.send_message(m.chat.id, f"⚠️ **שגיאת AI קריטית:**\n{filtered}\n\nמציג תוצאות לא מסוננות:")
        final_list = raw_products[:4]
    elif not filtered:
        bot.send_message(m.chat.id, "🧹 ה-AI סינן את כל המוצרים (חשב שהכל זבל).")
        final_list = raw_products[:4] # גיבוי
    else:
        bot.send_message(m.chat.id, "✅ ה-AI הצליח לסנן!")
        final_list = filtered[:4]

    # שליחת תוצאות
    for p in final_list:
        try:
            img = p.get('product_main_image_url')
            title = p.get('product_title')[:50]
            price = p.get('target_sale_price')
            url = p.get('product_detail_url')
            
            caption = f"{title}\n💰 {price}₪\n🔗 {url}"
            bot.send_photo(m.chat.id, img, caption=caption)
        except: pass

bot.infinity_polling()
