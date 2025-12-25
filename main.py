import telebot
import requests
import io
import hashlib
import time
import html
import json
import re
import os
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
GEMINI_API_KEY = "AIzaSyDNkixE64pO0muWxcqD2qtwZbTiH9UHT7w"

# הגדרת AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

bot = telebot.TeleBot(BOT_TOKEN)

class FreeSmartEngine:
    def __init__(self):
        self.universal_blacklist = ["link", "box", "deposit", "shipping fee", "extra fee"]

    def _enhance_query(self, user_query):
        try:
            return GoogleTranslator(source='auto', target='en').translate(user_query).lower()
        except:
            return user_query

    def _extract_number(self, val):
        try:
            val_str = str(val).lower().replace(',', '').replace('+', '').strip()
            if not val_str or val_str == '0': return 0
            match = re.search(r'(\d+(?:\.\d+)?)', val_str)
            if not match: return 0
            num = float(match.group(1))
            if 'k' in val_str: num *= 1000
            elif 'm' in val_str: num *= 1000000
            return int(num)
        except:
            return 0

    def _parse_sales(self, p):
        best_sales = 0
        for key, val in p.items():
            k_str = str(key).lower()
            if any(x in k_str for x in ['volume', 'sold', 'sales', 'order']) and 'price' not in k_str:
                current_sales = self._extract_number(val)
                if current_sales > best_sales:
                    best_sales = current_sales
        return best_sales

    # --- מסנן גיבוי: סטטיסטי (אם ה-AI נכשל) ---
    def _fallback_statistical_filter(self, products):
        if not products or len(products) < 5: return products
        prices = [p['price'] for p in products if p['price'] > 0]
        if not prices: return products
        
        median_price = statistics.median(prices)
        # מעיף כל מה שזול מ-30% מהמחיר הממוצע (מסנן זבל)
        threshold = median_price * 0.3
        
        clean = [p for p in products if p['price'] >= threshold]
        return clean if clean else products

    # --- מסנן ראשי: AI ---
    def _filter_with_ai(self, products, user_query):
        if not products: return []
        
        # הכנת הרשימה ל-AI
        products_text = "\n".join([f"ID {i}: {p['title_en']} (Price: {p['price']})" for i, p in enumerate(products)])

        prompt = f"""
        Query: "{user_query}"
        Task: Select items that match the query INTENT (Main product only).
        Exclude: Accessories, parts, batteries, cases, boxes, cheap replacements.
        
        List:
        {products_text}
        
        Output: Just the IDs numbers separated by comma. If none, say NONE.
        """

        try:
            response = model.generate_content(prompt)
            text_resp = response.text.strip()
            
            # שליפת מספרים גם אם ה-AI מקשקש מסביב
            valid_ids = [int(s) for s in re.findall(r'\b\d+\b', text_resp)]
            
            if not valid_ids: 
                return [] # ה-AI החליט שכלום לא מתאים
            
            return [products[i] for i in valid_ids if i < len(products)]

        except Exception as e:
            # דיווח על שגיאה למנהל כדי שנבין למה זה לא עובד
            error_msg = f"⚠️ **AI Error:** {str(e)}"
            bot.send_message(ADMIN_ID, error_msg, parse_mode="Markdown")
            return None # מסמן שהייתה תקלה

    def _process_results(self, resp_json, search_term_en="", original_query_he=""):
        data = resp_json.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {})
        products_raw = data.get('products', {}).get('product', [])
        if not products_raw: return []
        if isinstance(products_raw, dict): products_raw = [products_raw]

        parsed_products = []
        for p in products_raw:
            try:
                title_en = p['product_title']
                if any(bad in title_en.lower() for bad in self.universal_blacklist): continue
                
                try: title_he = GoogleTranslator(source='auto', target='iw').translate(title_en)
                except: title_he = title_en

                price = float(p.get('target_sale_price', 0))
                orig_price = float(p.get('target_original_price', 0))
                discount = int(round((1 - (price / orig_price)) * 100)) if orig_price > price else 0
                sales = self._parse_sales(p)
                
                # תמונות ולינקים
                img = p.get('product_main_image_url')
                url = p.get('product_detail_url', '')

                parsed_products.append({
                    "title": title_he[:85], "title_en": title_en,
                    "price": price, "orig_price": orig_price, "discount": discount,
                    "image": img, "raw_url": url, "sales": sales, "rating": 4.8
                })
            except: continue

        # --- שלב הסינון החכם ---
        
        # 1. ניסיון AI (על 15 המוצרים הראשונים)
        candidates = parsed_products[:15]
        ai_results = self._filter_with_ai(candidates, search_term_en)
        
        final_list = []
        filter_source = "AI"

        if ai_results is not None:
            # ה-AI עבד! (גם אם החזיר רשימה ריקה, זה אומר שהוא סינן הכל)
            final_list = ai_results
        else:
            # ה-AI נכשל (קרס), עוברים לתוכנית ב'
            filter_source = "Statistical Backup"
            final_list = self._fallback_statistical_filter(parsed_products)

        # מיון סופי והחזרה
        final_list.sort(key=lambda x: x['sales'], reverse=True)
        return final_list[:4], filter_source

    def search_text(self, original_query):
        search_term_en = self._enhance_query(original_query)
        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'keywords': search_term_en, 'target_currency': 'ILS', 'ship_to_country': 'IL',
            'sort': 'LAST_VOLUME_DESC', 'page_size': '30', 
        }
        params['sign'] = generate_sign(params)
        try:
            resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
            return self._process_results(resp, search_term_en, original_query)
        except: return [], "Error"

    def search_image(self, image_bytes): return [], "Image"

engine = FreeSmartEngine()

# --- עזרים ---
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

def create_collage(image_urls):
    images = []
    for url in image_urls:
        try:
            r = requests.get(url, timeout=5)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
            images.append(img)
        except: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
    while len(images) < 4: images.append(Image.new('RGB', (500,500), color='#FFFFFF'))
    collage = Image.new('RGB', (1000, 1000), 'white')
    positions = [(0,0), (500,0), (0,500), (500,500)]
    for i, img in enumerate(images[:4]): collage.paste(img, positions[i])
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

# --- הנדלרים ---
@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "👋 היי! כתוב לי מה לחפש (למשל: 'רחפן' או 'שעון').")

@bot.message_handler(func=lambda m: True)
def handle(m):
    q = m.text.replace("חפש לי", "").strip()
    if len(q) < 2: return
    
    loading = bot.reply_to(m, f"🔎 מחפש '{q}'...")
    products, source = engine.search_text(q)
    bot.delete_message(m.chat.id, loading.message_id)

    if not products:
        bot.send_message(m.chat.id, "❌ לא מצאתי תוצאות טובות.")
        return

    # יצירת קולאז' והודעה
    collage = create_collage([p['image'] for p in products])
    bot.send_photo(m.chat.id, collage, caption=f"תוצאות עבור: {q}\n(סינון: {source})")
    
    msg = ""
    for i, p in enumerate(products):
        link = get_short_link(p['raw_url'])
        msg += f"{i+1}. {p['title']}\n💰 {p['price']}₪ | 🔗 {link}\n\n"
    
    bot.send_message(m.chat.id, msg, disable_web_page_preview=True)

bot.infinity_polling()
