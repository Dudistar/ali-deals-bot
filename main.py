import telebot
import requests
import time
import re
import os
import io
import google.generativeai as genai
from telebot import types
from PIL import Image, ImageDraw

# --- הגדרות ---
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
GEMINI_API_KEY = "AIzaSyDNkixE64pO0muWxcqD2qtwZbTiH9UHT7w"
ADMIN_ID = 173837076

# הגדרת AI למודל היציב
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

bot = telebot.TeleBot(BOT_TOKEN)

# --- פונקציות עזר ---
def generate_sign(params):
    import hashlib
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

def create_collage(image_urls):
    # יצירת תמונה אחת מ-4 תמונות מוצרים
    images = []
    for url in image_urls[:4]:
        try:
            r = requests.get(url, timeout=5)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
            images.append(img)
        except: 
            images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
    
    # השלמה ל-4 אם יש פחות
    while len(images) < 4: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
    
    collage = Image.new('RGB', (1000, 1000), 'white')
    positions = [(0,0), (500,0), (0,500), (500,500)]
    draw = ImageDraw.Draw(collage)
    
    for i, img in enumerate(images):
        collage.paste(img, positions[i])
        # ציור מספר צהוב על התמונה
        if i < len(image_urls):
            x, y = positions[i]
            draw.ellipse((x+20, y+20, x+70, y+70), fill="#FFD700", outline="black")
            draw.text((x+40, y+35), str(i+1), fill="black", font_size=30)
            
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

def get_products_from_ali(query):
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
    if not products: return []
    
    text_list = "\n".join([f"ID {i}: {p['product_title']} (Price: {p['target_sale_price']})" for i, p in enumerate(products)])
    
    prompt = f"""
    Search Query: "{user_query}"
    Task: Select the best items that match the user's intent.
    Rules:
    1. EXCLUDE accessories, parts, or unrelated cheap items.
    2. If searching for a main device (e.g. Drone, Phone), do not return cables or cases.
    3. Return ONLY the ID numbers separated by commas (e.g. 0, 2, 5).
    
    Items:
    {text_list}
    """
    
    try:
        response = model.generate_content(prompt)
        ids = [int(s) for s in re.findall(r'\b\d+\b', response.text)]
        return [products[i] for i in ids if i < len(products)]
    except Exception as e:
        return f"AI ERROR: {str(e)}"

# --- הנדלרים ---

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "✅ הבוט מוכן!\nנסה לחפש: 'חפש לי אוזניות'")

@bot.message_handler(func=lambda m: True)
def handle(m):
    if "חפש לי" not in m.text: return
    query = m.text.replace("חפש לי", "").strip()
    
    bot.send_chat_action(m.chat.id, 'typing')
    
    # 1. שליפה מאליאקספרס
    raw_products, query_en = get_products_from_ali(query)
    
    if not raw_products:
        bot.send_message(m.chat.id, "❌ לא נמצאו מוצרים.")
        return

    # 2. סינון AI
    filtered = filter_with_ai(raw_products, query_en)
    
    # בדיקת תקינות
    if isinstance(filtered, str) and "ERROR" in filtered:
        # במקרה תקלה ב-AI, נחזיר רשימה רגילה
        final_list = raw_products[:4]
    elif not filtered:
        bot.send_message(m.chat.id, "🧹 לא נמצאו מוצרים תואמים לחיפוש המדויק.")
        final_list = []
    else:
        final_list = filtered[:4]

    if not final_list: return

    # 3. יצירת קולאז' ושליחה מרוכזת (החלק שביקשת)
    try:
        # יצירת התמונה
        image_urls = [p.get('product_main_image_url') for p in final_list]
        collage = create_collage(image_urls)
        
        # שליחת התמונה
        bot.send_photo(m.chat.id, collage, caption=f"💎 נבחרת הדילים עבור: **{query}**", parse_mode="Markdown")
        
        # יצירת הטקסט
        msg = ""
        for i, p in enumerate(final_list):
            title = p.get('product_title')[:50]
            price = p.get('target_sale_price')
            url = p.get('product_detail_url')
            
            # ניקוי הקישור (לא חובה אבל אסתטי)
            clean_link = url.split('?')[0]
            
            msg += f"{i+1}. **{title}**\n💰 מחיר: {price}₪\n🔗 [לרכישה לחץ כאן]({clean_link})\n\n"
            
        bot.send_message(m.chat.id, msg, parse_mode="Markdown", disable_web_page_preview=True)
        
    except Exception as e:
        bot.send_message(m.chat.id, f"שגיאה בשליחה: {e}")

bot.infinity_polling()
