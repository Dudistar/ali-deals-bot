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
# הגדרות
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
ADMIN_ID = 173837076  # <--- לכאן יישלח הדיווח

# משיכת מפתח
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
    """
    המלשינון: שולח הודעה למנהל על כל חיפוש
    """
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

def the_guillotine_filter(products):
    """
    שיטת הגיליוטינה: חותך את החצי התחתון של המחירים ומעיף מילים אסורות
    """
    if not products or len(products) < 5: return products
    
    blacklist = ["strobe", "light", "lamp", "propeller", "battery", "part", "accessory", "cable", "case", "cover", "gift", "toy", "mini"]
    clean_products = []
    
    for p in products:
        title = p.get('product_title', '').lower()
        if any(bad in title for bad in blacklist):
            continue
        clean_products.append(p)
    
    if len(clean_products) < 2: 
        clean_products = products
    
    # מיון מהיקר לזול
    clean_products.sort(key=lambda x: float(x.get('target_sale_price', 0)), reverse=True)
    
    # לוקחים את החצי היקר יותר
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
    You are a Shopping Assistant for a wealthy client.
    User Query: "{query_en}"
    Task: Pick the BEST quality items.
    STRICT RULES:
    1. REJECT cheap toys or knockoffs. 
    2. REJECT accessories.
    3. Look at the Price: If it looks too cheap, REJECT IT.
    List:
    {list_text}
    Output: Only the IDs of the high-quality items (e.g., 0, 2).
    """
    try:
        response = model.generate_content(prompt)
        ids = [int(s) for s in re.findall(r'\b\d+\b', response.text)]
        ai_filtered = [candidates[i] for i in ids if i < len(candidates)]
        
        if not ai_filtered:
            return candidates[:4]
            
        return ai_filtered[:4]
    except: 
        return candidates[:4]

# ==========================================
# הנדלרים
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    # הפעלת המלשינון גם בהתחלה (אופציונלי, כדי לדעת מי נכנס)
    notify_admin(m.from_user, "לחץ START")
    
    welcome_msg = (
        "👋 <b>ברוכים הבאים ל-DrDeals Premium!</b> 💎\n\n"
        "הבוט שעושה סדר באליאקספרס.\n"
        "אני משתמש באלגוריתם 'גיליוטינה' 🪓 כדי לחתוך את כל הזיופים והצעצועים הזולים,\n"
        "ומשאיר לכם רק ציוד איכותי.\n\n"
        "👇 <b>נסה אותי עכשיו:</b>"
    )
    markup = types.ReplyKeyboardMarkup(resize_
