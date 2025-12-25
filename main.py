import telebot
import requests
import time
import re
import os
import io
import hashlib
import google.generativeai as genai
from telebot import types
from PIL import Image, ImageDraw

# ייבוא מתרגם - חובה לעיצוב בעברית
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

# חיבור ל-AI (מודל יציב)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# פונקציות מנוע (Logic)
# ==========================================

def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

def get_short_link(raw_url):
    # יוצר לינק מקוצר כדי שלא יהיה לינק באורך הגלות
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
    return clean_url # אם נכשל מחזיר את המקורי

def translate_to_hebrew(text):
    try:
        return GoogleTranslator(source='auto', target='iw').translate(text)
    except:
        return text

def create_collage(image_urls):
    images = []
    # מוריד עד 4 תמונות
    for url in image_urls[:4]:
        try:
            r = requests.get(url, timeout=5)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
            images.append(img)
        except: 
            images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
    
    # משלים ל-4 ריבועים לבנים אם חסר
    while len(images) < 4: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
    
    # יצירת הקולאז'
    collage = Image.new('RGB', (1000, 1000), 'white')
    positions = [(0,0), (500,0), (0,500), (500,500)]
    draw = ImageDraw.Draw(collage)
    
    for i, img in enumerate(images):
        collage.paste(img, positions[i])
        if i < len(image_urls): # רק אם יש מוצר אמיתי מצייר מספר
            x, y = positions[i]
            # עיגול צהוב בולט
            draw.ellipse((x+20, y+20, x+80, y+80), fill="#FFD700", outline="black", width=3)
            # מספר שחור באמצע
            draw.text((x+42, y+35), str(i+1), fill="black", font_size=50)
            
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

def get_ali_products(query):
    # תרגום לאנגלית לטובת החיפוש באליאקספרס
    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query).lower()
    except:
        query_en = query

    params = {
        'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
        'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
        'keywords': query_en, 'target_currency': 'ILS', 'ship_to_country': 'IL',
        'sort': 'LAST_VOLUME_DESC', 'page_size': '20', # מושך 20 כדי שיהיה ממה לסנן
    }
    params['sign'] = generate_sign(params)
    
    try:
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
        data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {})
        products = data.get('products', {}).get('product', [])
        if isinstance(products, dict): products = [products]
        return products, query_en
    except Exception as e:
        print(f"Ali API Error: {e}")
        return [], str(e)

def filter_products_smartly(products, user_query_en):
    if not products: return []
    
    # מכין רשימה קריאה ל-AI
    # שולח לו: כותרת + מחיר. המחיר קריטי לזיהוי אביזרים זולים.
    list_text = "\n".join([f"ID {i}: {p['product_title']} (Price: {p.get('target_sale_price', '0')} ILS)" for i, p in enumerate(products)])
    
    prompt = f"""
    Search Query: "{user_query_en}"
    
    Task: Identify the IDs of the MAIN products that match the query.
    
    STRICT RULES:
    1. Ignore accessories, parts, cables, cases, or "mini" versions if the user asked for the main device.
    2. Example: If searching for "Drone", DO NOT pick propellers, motors, lights (strobe), or batteries. Pick ONLY the drone itself.
    3. Example: If searching for "Pants", DO NOT pick underwear or pajamas.
    4. Use the Price as a hint (Main items are usually more expensive than accessories).
    
    Product List:
    {list_text}
    
    Output format: Just the numbers separated by commas (e.g: 0, 2, 5).
    """
    
    try:
        response = model.generate_content(prompt)
        text_resp = response.text
        # מחלץ רק מספרים מהתשובה
        ids = [int(s) for s in re.findall(r'\b\d+\b', text_resp)]
        
        # בוחר את המוצרים לפי המספרים שה-AI החזיר
        filtered = [products[i] for i in ids if i < len(products)]
        
        return filtered
    except Exception as e:
        print(f"AI Filter Error: {e}")
        return [] # במקרה של שגיאה נחזיר רשימה ריקה והקוד יטפל בזה

# ==========================================
# הנדלרים (Bot Interaction)
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    # הודעת ברוכים הבאים מושקעת
    welcome_msg = (
        "👋 <b>ברוכים הבאים ל-DrDeals!</b>\n\n"
        "אני הבוט החדשני שלכם לקניות חכמות. אני משתמש בבינה מלאכותית 🧠 "
        "כדי לסנן את הזבל ולהביא לכם רק את המוצרים השווים.\n\n"
        "👇 <b>מה מחפשים היום?</b>"
    )
    # מקלדת כפתורים קבועה למטה
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("חפש לי אוזניות", "חפש לי רחפן", "חפש לי שעון חכם", "חפש לי מצלמת רכב")
    
    bot.send_message(m.chat.id, welcome_msg, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    if "חפש לי" not in m.text: return
    
    # מנקה את הטקסט
    user_query = m.text.replace("חפש לי", "").strip()
    
    bot.send_chat_action(m.chat.id, 'typing')
    loading = bot.send_message(m.chat.id, f"🔎 <b>סורק את העולם עבור: {user_query}...</b>", parse_mode="HTML")
    
    # 1. מביא 20 מוצרים מאליאקספרס
    raw_products, query_en = get_ali_products(user_query)
    
    if not raw_products:
        bot.delete_message(m.chat.id, loading.message_id)
        bot.send_message(m.chat.id, "❌ לא מצאתי שום מוצר. נסה חיפוש כללי יותר.")
        return

    # 2. שולח לסינון AI
    ai_filtered_products = filter_products_smartly(raw_products, query_en)
    
    # 3. גיבוי: אם ה-AI החליט שהכל זבל (או נכשל), קח את ה-4 הנמכרים ביותר
    # אבל - ננסה לסנן ידנית מוצרים זולים מדי (מתחת ל-10 שקל) אם זה מוצר אלקטרוני
    final_list = []
    if ai_filtered_products:
        final_list = ai_filtered_products[:4]
    else:
        # Fallback Logic: Take top sellers that cost more than 15 NIS (to avoid cheap parts)
        final_list = [p for p in raw_products if float(p.get('target_sale_price', 0)) > 15][:4]
        if not final_list: final_list = raw_products[:4] # ממש אין ברירה

    bot.delete_message(m.chat.id, loading.message_id)

    # 4. בונה את ההודעה היפה (החלק שהיה חסר!)
    try:
        # א. קולאז'
        image_urls = [p.get('product_main_image_url') for p in final_list]
        collage = create_collage(image_urls)
        bot.send_photo(m.chat.id, collage, caption=f"💎 <b>הנבחרים עבור: {user_query}</b>", parse_mode="HTML")
        
        # ב. רשימת מוצרים עם כפתורים
        full_text = ""
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for i, p in enumerate(final_list):
            # תרגום כותרת
            title_en = p.get('product_title')
            title_he = translate_to_hebrew(title_en)
            
            # מחיר והנחה
            price = float(p.get('target_sale_price', 0))
            orig_price = float(p.get('target_original_price', 0))
            
            discount_txt = ""
            if orig_price > price:
                percent = int(((orig_price - price) / orig_price) * 100)
                discount_txt = f" | 📉 <b>{percent}% הנחה</b>"
            
            # מכירות
            sales = p.get('lastest_volume', 0)
            
            # קישור
            link = get_short_link(p.get('product_detail_url'))
            
            # בניית הטקסט למוצר
            full_text += f"{i+1}. 🏆 <b>{title_he[:55]}...</b>\n"
            full_text += f"💰 מחיר: <b>{price}₪</b>{discount_txt}\n"
            full_text += f"🔥 נחטף ע''י: <b>{sales}+ רוכשים</b>\n"
            full_text += f"🔗 <a href='{link}'>לחץ לפרטים ורכישה</a>\n\n"
            
            # כפתור
            btn = types.InlineKeyboardButton(text=f"🎁 לקנייה (מוצר {i+1})", url=link)
            markup.add(btn)
            
        full_text += "🛍️ <b>קנייה מהנה! | DrDeals</b>"
        
        bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        
    except Exception as e:
        bot.send_message(m.chat.id, f"שגיאה בהצגה: {e}")

bot.infinity_polling()
