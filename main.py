import telebot
import requests
import time
import re
import os
import io
import hashlib
import statistics
import logging
import json
import random
from telebot import types
from PIL import Image, ImageDraw
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# ==========================================
# ⚙️ הגדרות מערכת
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
ADMIN_ID = 173837076
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

session = requests.Session()
retry = Retry(connect=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

HAS_GEMINI = False
model = None
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        HAS_GEMINI = True
    except Exception as e:
        logging.error(f"Gemini init failed: {e}")

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🔒 מיפוי קטגוריות
# ==========================================
CATEGORY_MAP = {
    'coat': '200001901', 'jacket': '200001901', 'מעיל': '200001901',
    'drone': '200002649', 'רחפן': '200002649',
    'watch': '200000095', 'שעון': '200000095',
    'headphones': '63705', 'earphones': '63705', 'אוזניות': '63705',
    'phone': '2000023', 'smartphone': '2000023', 'טלפון': '2000023',
    'dress': '200003482', 'שמלה': '200003482',
    'shoes': '322', 'נעליים': '322'
}

def get_category_id(user_query):
    for key, cat_id in CATEGORY_MAP.items():
        if key in user_query.lower():
            return cat_id
    return None

# ==========================================
# 🛠️ פונקציות עזר
# ==========================================
def safe_float(value):
    try:
        clean = str(value).replace('US', '').replace('$', '').replace('₪', '').strip()
        return float(clean)
    except: return 0.0

def translate_to_hebrew(text, delay=2.5):
    """תרגום לעברית עם זמן המתנה"""
    time.sleep(delay)
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target='iw').translate(text)
    except Exception as e:
        logging.error(f"Translation failed: {e}")
        return text

def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

# ==========================================
# 🧠 שלב 1: הבלש (Smart Query)
# ==========================================
def smart_query_optimizer(user_text, delay=2.5):
    time.sleep(delay)
    if HAS_GEMINI and model:
        try:
            prompt = f"""
            Task: Translate Hebrew search to English Keywords.
            Input: "{user_text}"
            Rules:
            1. Output ONLY English.
            2. Avoid parts or accessories.
            Output: Keywords only.
            """
            response = model.generate_content(prompt)
            if response.text:
                res = response.text.strip().replace('"', '')
                if not any("\u0590" <= char <= "\u05EA" for char in res):
                    return res
        except Exception as e:
            logging.error(f"Gemini smart query failed: {e}")

    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source='auto', target='en').translate(user_text)
        if translated and not any("\u0590" <= char <= "\u05EA" for char in translated):
            return translated
    except Exception as e:
        logging.error(f"Fallback translation failed: {e}")
    return None

# ==========================================
# 🎣 שלב 2: הרשת (API Fetcher)
# ==========================================
def get_ali_products(cleaned_query, category_id=None, delay=3.0):
    """מחפש ב-AliExpress עם השהייה מלאכותית"""
    if not cleaned_query: return []
    time.sleep(delay)
    params = {
        'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
        'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
        'keywords': cleaned_query, 
        'target_currency': 'ILS', 'ship_to_country': 'IL',
        'sort': 'LAST_VOLUME_DESC', 
        'page_size': '50',
    }
    if category_id:
        params['category_ids'] = category_id
    params['sign'] = generate_sign(params)

    try:
        response = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15)
        data = response.json().get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(data, dict): data = [data]
        logging.info(f"AliExpress returned {len(data)} products for query '{cleaned_query}'")
        return data
    except Exception as e:
        logging.error(f"AliExpress API failed: {e}")
        return []

# ==========================================
# 🛑 פילטר חכם
# ==========================================
def smart_filter(products, query_en):
    """סינון חכם של מוצרים, לא זורק הכל"""
    if not products: return []

    blacklist = [
        "vtx", "motor", "esc", "frame", "receiver", "antenna",
        "module", "spare part", "case", "strap", "screw", "film"
    ]
    clean_products = []
    prices = []

    for p in products:
        title = p.get('product_title', '').lower()
        price = safe_float(p.get('target_sale_price', 0))
        if any(bad in title for bad in blacklist): continue
        if price > 0:
            clean_products.append(p)
            prices.append(price)

    if not clean_products: return []

    # סינון לפי מחיר יחסית למדיהן
    if len(prices) > 5:
        median_price = statistics.median(prices)
        threshold = median_price * 0.3
        clean_products = [p for p in clean_products if safe_float(p.get('target_sale_price', 0)) >= threshold]

    clean_products.sort(key=lambda x: safe_float(x.get('target_sale_price', 0)), reverse=True)
    return clean_products[:20]

# ==========================================
# ✍️ AI Rewrite / Final Selection
# ==========================================
def ai_finalize(products, user_query_hebrew, query_en, delay=4.0):
    time.sleep(delay)
    if not products: return []

    if not HAS_GEMINI or not model:
        for p in products[:4]:
            p['ai_title'] = translate_to_hebrew(p.get('product_title'), delay=2)
        return products[:4]

    items_str = "\n".join([f"Item {i}: {p.get('product_title')} | Price: {p.get('target_sale_price')}" for i, p in enumerate(products[:10])])
    prompt = f"""
    Role: Product Curator.
    User Query: "{user_query_hebrew}"
    Task: Filter correct products, rewrite short Hebrew title with emoji.
    Items:
    {items_str}
    Output JSON ONLY: [{"index":0,"valid":true,"hebrew_title":"Example"}]
    """
    try:
        response = model.generate_content(prompt)
        text_resp = response.text.strip().replace("```json","").replace("```","")
        decisions = json.loads(text_resp)
        final = []
        for d in decisions:
            if d.get("valid") and d.get("index") < len(products):
                p = products[d.get("index")]
                p['ai_title'] = d.get("hebrew_title")
                final.append(p)
        if not final:
            for p in products[:3]:
                p['ai_title'] = translate_to_hebrew(p.get('product_title'), delay=2)
            return products[:3]
        return final[:4]
    except Exception as e:
        logging.error(f"AI finalization failed: {e}")
        for p in products[:3]:
            p['ai_title'] = translate_to_hebrew(p.get('product_title'), delay=2)
        return products[:3]

# ==========================================
# 🛠️ לינקים וקולאז'
# ==========================================
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
        resp = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10).json()
        result = resp.get('aliexpress_affiliate_link_generate_response', {}).get('resp_result', {}).get('result', {}).get('promotion_links', {}).get('promotion_link', [])
        if result: return result[0].get('promotion_short_link') or result[0].get('promotion_link')
    except: pass
    return clean_url

def create_collage(image_urls):
    try:
        images = []
        for url in image_urls[:4]:
            try:
                r = session.get(url, timeout=5)
                img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
                images.append(img)
            except:
                images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
        while len(images) < 4: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))

        collage = Image.new('RGB', (1000,1000), 'white')
        positions = [(0,0),(500,0),(0,500),(500,500)]
        for i, pos in enumerate(positions):
            collage.paste(images[i], pos)
        output = io.BytesIO()
        collage.save(output, format='JPEG', quality=85)
        output.seek(0)
        return output
    except: return None

def notify_admin(user, query):
    if not ADMIN_ID: return
    try:
        username = f"@{user.username}" if user.username else ""
        msg = f"🕵️‍♂️ **חיפוש:** {query}\n👤 {user.first_name} {username}"
        bot.send_message(ADMIN_ID, msg)
    except: pass

# ==========================================
# 🚀 בוט ראשי
# ==========================================
@bot.message_handler(commands=['start'])
def start(m):
    welcome_msg = (
        "✨ <b>ברוכים הבאים ל-DrDeals Premium</b> 💎\n\n"
        "כאן החיפוש מקצועי ומעמיק. כל תוצאה עוברת בדיקה AI וסינון.\n"
        "⌛ זהירות: החיפוש לוקח זמן – הבוט עובד ביסודיות.\n"
        "👇 <b>כתבו: 'חפש לי...' כדי להתחיל</b>"
    )
    bot.send_message(m.chat.id, welcome_msg, parse_mode="HTML")

@bot.message_handler(func=lambda m: True)
def handle_text(m):
    if "חפש לי" not in m.text:
        if len(m.text) > 3: bot.reply_to(m, "💡 נא לכתוב **'חפש לי'** לפני שם המוצר.")
        return

    raw_query = m.text.replace("חפש לי", "").strip()
    notify_admin(m.from_user, raw_query)
    bot.send_chat_action(m.chat.id, 'typing')
    msg = bot.send_message(m.chat.id, f"🕵️‍♂️ מחפש ביסודיות: {raw_query}...", parse_mode="HTML")

    cat_id = get_category_id(raw_query)
    query_en = smart_query_optimizer(raw_query, delay=4)

    if not query_en:
        bot.edit_message_text("⚠️ תקלה בתרגום. נסה שוב.", m.chat.id, msg.message_id)
        return

    products = get_ali_products(query_en, category_id=cat_id, delay=5)
    filtered = smart_filter(products, query_en)
    final_list = ai_finalize(filtered, raw_query, query_en, delay=6)

    bot.delete_message(m.chat.id, msg.message_id)

    if not final_list:
        bot.send_message(m.chat.id, f"🛑 <b>לא נמצאו תוצאות מדויקות.</b>\nהמוצרים שנמצאו לא עברו את הסינון החכם.")
        return

    image_urls = []
    full_text = f"🛍️ <b>הבחירות המובילות עבורך:</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)

    for i, p in enumerate(final_list):
        title = p.get('ai_title', translate_to_hebrew(p.get('product_title'), delay=2))
        price = safe_float(p.get('target_sale_price', 0))
        orig_price = safe_float(p.get('target_original_price', 0))
        sales = p.get('last_volume', 0)
        link = get_short_link(p.get('product_detail_url'))

        if not link: continue

        discount_txt = ""
        if orig_price > price:
            percent = int(((orig_price - price) / orig_price) * 100)
            if percent > 5: discount_txt = f" | 📉 <b>{percent}% הנחה</b>"

        sales_txt = ""
        if sales and int(sales) > 10: sales_txt = f" | 📦 <b>{sales}+ נרכשו</b>"

        image_urls.append(p.get('product_main_image_url'))
        full_text += f"{i+1}. {title}\n💰 <b>{price}₪</b>{discount_txt}{sales_txt}\n🔗 {link}\n\n"
        markup.add(types.InlineKeyboardButton(f"🛍️ עבור למוצר {i+1}", url=link))

    if image_urls:
        collage = create_collage(image_urls)
        if collage:
            bot.send_photo(m.chat.id, collage, caption=f"🏆 <b>תוצאות: {raw_query}</b>", parse_mode="HTML")

    full_text += "💎 <b>DrDeals Premium</b>"
    bot.send_message(m.chat.id, full_text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

bot.infinity_polling()# fallback_query: מה לחפש אם החיפוש המקורי נכשל
STRICT_LOGIC = {
    'מעיל': {
        'cat_id': '200001901', 
        'must_have': ['coat', 'jacket', 'parka', 'trench', 'outwear'],
        'fallback_query': 'Woman Coat Winter'
    },
    'רחפן': {
        'cat_id': '200002649', 
        'must_have': ['drone', 'quadcopter', 'uav'],
        'fallback_query': 'Professional Drone Camera'
    },
    'שעון': {
        'cat_id': '200000095', 
        'must_have': ['watch', 'smartwatch', 'band'],
        'fallback_query': 'Smart Watch'
    },
    'אוזניות': {
        'cat_id': '63705', 
        'must_have': ['headphone', 'earphone', 'earbud', 'headset'],
        'fallback_query': 'Wireless Headphones'
    },
    'טלפון': {
        'cat_id': '2000023', 
        'must_have': ['phone', 'smartphone', 'mobile', 'android'],
        'fallback_query': 'Smartphone Global Version'
    },
     'נעליים': {
        'cat_id': '322', 
        'must_have': ['shoe', 'sneaker', 'boot', 'heel'],
        'fallback_query': 'Women Shoes'
    }
}

# ==========================================
# 🔐 חתימה
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

# ==========================================
# 🎣 שליפת מוצרים
# ==========================================
def get_ali_products(query, cat_id=None):
    print(f"DEBUG: Searching '{query}' (Cat: {cat_id})")
    
    params = {
        "app_key": APP_KEY,
        "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "format": "json",
        "sign_method": "md5",
        "v": "2.0",
        "partner_id": "top-autopilot",
        "keywords": query,
        "target_currency": "ILS",
        "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC",
        "page_size": "50"
    }
    
    if cat_id:
        params["category_ids"] = cat_id

    params["sign"] = generate_sign(params)

    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        if "aliexpress_affiliate_product_query_response" not in data:
            return []
        products = data["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
        return products if isinstance(products, list) else [products]
    except Exception as e:
        print(f"Error: {e}")
        return []

# ==========================================
# 🕵️‍♂️ סינון (לא מוחק אם אין ברירה)
# ==========================================
def smart_filter(products, rule=None):
    clean = []
    
    # מילים שאסור שיהיו בשום מצב (חלקי חילוף)
    global_ban = ["screw", "repair tool", "connector", "adapter", "pipe", "aluminum alloy"]

    for p in products:
        title = p.get("product_title", "").lower()
        
        # 1. סינון גלובלי (הגנה ממברגים)
        if any(bad in title for bad in global_ban):
            continue

        # 2. סינון לפי קטגוריה (אם הוגדרה)
        if rule:
            # חייב להכיל אחת ממילות המפתח (למשל Coat)
            if not any(w in title for w in rule['must_have']):
                continue
        
        clean.append(p)
    
    return clean

# ==========================================
# 🔗 לינקים ותמונות
# ==========================================
def get_short_link(url):
    if not url: return None
    clean = url.split("?")[0]
    params = {
        "app_key": APP_KEY, "method": "aliexpress.affiliate.link.generate",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "format": "json",
        "sign_method": "md5", "v": "2.0", "partner_id": "top-autopilot",
        "promotion_link_type": "0", "source_values": clean, "tracking_id": TRACKING_ID
    }
    params["sign"] = generate_sign(params)
    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=5).json()
        link = r["aliexpress_affiliate_link_generate_response"]["resp_result"]["result"]["promotion_links"]["promotion_link"][0]
        return link.get("promotion_short_link") or link.get("promotion_link")
    except: return clean

def create_collage(urls):
    imgs = []
    for u in urls[:3]:
        try:
            img = Image.open(io.BytesIO(session.get(u, timeout=5).content)).resize((500,500))
        except: img = Image.new("RGB",(500,500),"white")
        imgs.append(img)
    while len(imgs)<3: imgs.append(Image.new("RGB",(500,500),"white"))
    
    canvas = Image.new("RGB",(1000,1000),"white")
    canvas.paste(imgs[0].resize((1000,500)),(0,0))
    canvas.paste(imgs[1],(0,500))
    canvas.paste(imgs[2],(500,500))
    
    out = io.BytesIO()
    canvas.save(out,"JPEG",quality=85)
    out.seek(0)
    return out

# ==========================================
# 🚀 בוט ראשי
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    if not m.text.startswith("חפש לי"): return

    query_he = m.text.replace("חפש לי","").strip()
    bot.send_chat_action(m.chat.id, "typing")
    bot.reply_to(m, f"🕵️‍♂️ מחפש: {query_he}...")

    # 1. זיהוי חוקים וקטגוריה
    rule = None
    for key, r in STRICT_LOGIC.items():
        if key in query_he:
            rule = r
            break
    
    cat_id = rule['cat_id'] if rule else None

    # 2. תרגום (ניסיון ראשון - ספציפי)
    try:
        query_en = GoogleTranslator(source='auto', target='en').translate(query_he)
    except:
        query_en = query_he

    # 3. חיפוש ראשון (ספציפי)
    products = get_ali_products(query_en, cat_id)
    final_products = smart_filter(products, rule)

    # 4. מנגנון הגיבוי (הצלה!)
    # אם החיפוש הספציפי נכשל (לא מצא כלום או שהכל סונן)
    if not final_products and rule:
        bot.send_message(m.chat.id, "⚠️ חיפוש מדויק לא הניב תוצאות, מפעיל חיפוש חכם בקטגוריה...")
        # משתמשים בביטוי כללי שמוגדר מראש (למשל 'Woman Coat')
        fallback_query = rule['fallback_query']
        products = get_ali_products(fallback_query, cat_id)
        final_products = smart_filter(products, rule)

    # 5. בדיקה סופית
    if not final_products:
        bot.send_message(m.chat.id, "🛑 לא נמצאו תוצאות. נסה ניסוח פשוט יותר.")
        return

    # 6. הצגה
    top_3 = final_products[:3]
    images = []
    text = f"🧥 <b>תוצאות עבור: {query_he}</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(top_3):
        try:
            title = GoogleTranslator(source='auto', target='iw').translate(p["product_title"])
        except:
            title = p["product_title"]
            
        price = p.get("target_sale_price", "?") + "₪"
        link = get_short_link(p.get("product_detail_url"))
        images.append(p.get("product_main_image_url"))

        text += f"{i+1}. {title[:55]}...\n💰 <b>{price}</b>\n🔗 {link}\n\n"
        kb.add(types.InlineKeyboardButton(f"🛍️ לרכישה {i+1}", url=link))

    if images:
        try:
            bot.send_photo(m.chat.id, create_collage(images), caption=text, parse_mode="HTML", reply_markup=kb)
        except:
            bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)

print("Bot is running with Smart Fallback...")
bot.infinity_polling()
