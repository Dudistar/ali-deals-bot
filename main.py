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

# --- משיכת המפתח מהכספת של Railway ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# חיבור למודל (רק אם יש מפתח)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
else:
    print("⚠️ Warning: No GEMINI_API_KEY found in environment variables.")

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# פונקציות ליבה
# ==========================================

def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

def get_short_link(raw_url):
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

def get_ali_products(query):
    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query).lower()
    except:
        query_en = query

    params = {
        'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
        'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
        'keywords': query_en, 'target_currency': 'ILS', 'ship_to_country': 'IL',
        'sort': 'LAST_VOLUME_DESC', 
        'page_size': '50', 
    }
    params['sign'] = generate_sign(params)
    
    try:
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
        data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(data, dict): data = [data]
        return data, query_en
    except: return [], query_en

def remove_cheap_knockoffs(products):
    """
    מסנן מוצרים שזולים בצורה קיצונית מהמחיר הממוצע (מונע זבל)
    """
    if not products or len(products) < 3: return products
    
    prices = []
    for p in products:
        try:
            price = float(p.get('target_sale_price', 0))
            if price > 0: prices.append(price)
        except: pass
    
    if not prices: return products
    
    median_price = statistics.median(prices)
    # סף איכות: 60% מהחציון (למשל אם הרוב עולה 100, כל מה שמתחת ל-60 עף)
    quality_threshold = median_price * 0.6 
    
    high_quality_products = []
    for p in products:
        try:
            price = float(p.get('target_sale_price', 0))
            if price >= quality_threshold:
                high_quality_products.append(p)
        except: pass
        
    return high_quality_products

def filter_premium(products, query_en):
    if not products: return []
    
    # אם אין מפתח, אין AI, אז מחזירים רגיל
    if not GEMINI_API_KEY:
        return products[:4]

    # שלב 1: AI
    list_text = "\n".join([f"ID {i}: {p['product_title']} (Price: {p.get('target_sale_price', '0')})" for i, p in enumerate(products[:20])])
    prompt = f"""
    Query: "{query_en}"
    Select IDs of HIGH QUALITY main products only.
    Ignore cheap plastic toys, spare parts, and accessories.
    List:
    {list_text}
    Output IDs:
    """
    
    try:
        response = model.generate_content(prompt)
        ids = [int(s) for s in re.findall(r'\b\d+\b', response.text)]
        ai_filtered = [products[i] for i in ids if i < len(products)]
    except:
        ai_filtered = products

    if not ai_filtered: return products[:4]

    # שלב 2: סינון מחיר (העפת זבל)
    final_quality_list = remove_cheap_knockoffs(ai_filtered)
    
    if not final_quality_list:
        return ai_filtered

    # מיון לפי מחיר יורד (הכי יקר ואיכותי למעלה)
    final_quality_list.sort(key=lambda x: float(x.get('target_sale_price', 0)), reverse=True)
    
    return final_quality_list[:4]

# ==========================================
# הנדלרים
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    welcome_msg = (
        "👋 <b>ברוכים הבאים ל-DrDeals Premium!</b>\n\n"
        "👇 <b>נסה אותי:</b>"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("חפש לי אוזניות", "חפש לי רחפן", "חפש לי שעון חכם")
    bot.send_message(m.chat.id, welcome_msg, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    if "חפש לי" not in m.text: return
    user_query = m.text.replace("חפש לי", "").strip()
    
    bot.send_chat_action(m.chat.id, 'typing')
    loading = bot.send_message(m.chat.id, f"💎 <b>מחפש את הטופ של ה-Top עבור: {user_query}...</b>", parse_mode="HTML")
    
    raw_products, query_en = get_ali_products(user_query)
    
    if not raw_products:
        bot.delete_message(m.chat.id, loading.message_id)
        bot.send_message(m.chat.id, "❌ לא נמצאו מוצרים.")
        return

    final_list = filter_premium(raw_products, query_en)
    
    bot.delete_message(m.chat.id, loading.message_id)

    try:
        image_urls = [p.get('product_main_image_url') for p in final_list]
        collage = create_collage(image_urls)
        
        bot.send_photo(m.chat.id, collage, caption=f"🏆 <b>הבחירות המובילות: {user_query}</b>", parse_mode="HTML")
        
        full_text = ""
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for i, p in enumerate(final_list):
            title_he = translate_to_hebrew(p.get('product_title'))
            price = float(p.get('target_sale_price', 0))
            orig_price = float(p.get('target_original_price', 0))
            
            discount_txt = ""
            if orig_price > price:
                percent = int(((orig_price - price) / orig_price) * 100)
                discount_txt = f" | 📉 <b>{percent}% הנחה</b>"
            
            sales = p.get('lastest_volume', 0)
            link = get_short_link(p.get('product_detail_url'))
            
            full_text += f"{i+1}. 🏅 <b>{title_he[:55]}...</b>\n"
            full_text += f"💰 מחיר: <b>{price}₪</b>{discount_txt}\n"
            full_text += f"⭐ דירוג איכות: <b>{p.get('evaluate_rate', '4.8')}</b>\n"
            full_text += f"🔗 {link}\n\n"
            
            btn = types.InlineKeyboardButton(text=f"🛍️ לרכישת מוצר {i+1}", url=link)
            markup.add(btn)
            
        full_text += "💎 <b>DrDeals Premium Selection</b>"
        
        bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        
    except Exception as e:
        bot.send_message(m.chat.id, f"שגיאה: {e}")

bot.infinity_polling()
