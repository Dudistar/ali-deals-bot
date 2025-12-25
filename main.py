import telebot
import requests
import io
import hashlib
import time
import html
import json
import re
import os
from telebot import types
from PIL import Image, ImageDraw

# בדיקה שספריית התרגום קיימת
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

print("🔄 מתחבר לטלגרם...")
bot = telebot.TeleBot(BOT_TOKEN)
print("✅ הבוט מחובר - גרסה נקייה (ללא הבטחת תמונות)")

class FreeSmartEngine:
    def __init__(self):
        self.keyword_booster = {
            "charger": "GaN fast charging",
            "cable": "braided fast data",
            "headphones": "noise cancelling bluetooth 5.3",
            "watch": "amoled smart watch waterproof",
            "dash": "70mai ddpai 4k",
        }

    def _enhance_query(self, user_query):
        try:
            en_query = GoogleTranslator(source='auto', target='en').translate(user_query).lower()
            for key, boost in self.keyword_booster.items():
                if key in en_query and boost not in en_query:
                    return f"{en_query} {boost}"
            return en_query
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
            elif 'w' in val_str: num *= 10000
            return int(num)
        except:
            return 0

    def _parse_sales(self, p):
        best_sales = 0
        for key, val in p.items():
            k_str = str(key).lower()
            if any(x in k_str for x in ['volume', 'sold', 'sales', 'order']) and 'price' not in k_str and 'currency' not in k_str:
                current_sales = self._extract_number(val)
                if current_sales > best_sales:
                    best_sales = current_sales
        return best_sales

    def _process_results(self, resp_json):
        data = resp_json.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {})
        if not data:
            data = resp_json.get('aliexpress_affiliate_image_search_response', {}).get('resp_result', {}).get('result', {})
            
        products_raw = data.get('products', {}).get('product', [])
        if not products_raw: return []
        if isinstance(products_raw, dict): products_raw = [products_raw]

        parsed_products = []
        for p in products_raw:
            try:
                sales = self._parse_sales(p)
                rate_str = str(p.get('evaluate_rate', '0')).replace('%', '')
                rating = float(rate_str) / 20 if rate_str else 0.0
                
                try: title_he = GoogleTranslator(source='auto', target='iw').translate(p['product_title'])
                except: title_he = p['product_title']

                try: price = float(p.get('target_sale_price', 0))
                except: price = 0
                try: orig_price = float(p.get('target_original_price', 0))
                except: orig_price = 0
                
                discount = 0
                if orig_price > price and price > 0:
                    discount = int(round((1 - (price / orig_price)) * 100))

                parsed_products.append({
                    "title": title_he[:85],
                    "price": price,
                    "orig_price": orig_price,
                    "discount": discount,
                    "image": p.get('product_main_image_url'),
                    "raw_url": p.get('product_detail_url', ''),
                    "rating": round(rating, 1),
                    "sales": sales
                })
            except: continue

        parsed_products.sort(key=lambda x: x['sales'], reverse=True)
        return parsed_products[:4]

    def search_text(self, original_query):
        print(f"🔎 מחפש טקסט: {original_query}")
        smart_keywords = self._enhance_query(original_query)
        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'keywords': smart_keywords, 'target_currency': 'ILS', 'ship_to_country': 'IL',
            'sort': 'LAST_VOLUME_DESC', 'page_size': '50',
        }
        params['sign'] = generate_sign(params)
        try:
            resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
            return self._process_results(resp)
        except Exception as e:
            print(f"❌ שגיאה בחיפוש טקסט: {e}")
            return []

    def search_image(self, image_bytes):
        print("📸 מנסה חיפוש לפי תמונה...")
        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.image.search',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'target_currency': 'ILS', 'ship_to_country': 'IL',
            'sort': 'LAST_VOLUME_DESC', 'page_size': '20',
            'img_file_bytes': 'BINARY_PLACEHOLDER'
        }
        sign_params = {k: v for k, v in params.items() if k != 'img_file_bytes'}
        params['sign'] = generate_sign(sign_params)
        del params['img_file_bytes']

        try:
            files = {'img_file_bytes': ('search.jpg', image_bytes, 'image/jpeg')}
            resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, files=files, timeout=20).json()
            if 'error_response' in resp: return None
            return self._process_results(resp)
        except Exception as e:
            print(f"❌ שגיאה בחיפוש תמונה: {e}")
            return None

engine = FreeSmartEngine()

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
    positions, draw = [(0,0), (500,0), (0,500), (500,500)], ImageDraw.Draw(collage)
    
    def draw_num(d, cx, cy, num):
        d.ellipse((cx, cy, cx+35, cy+35), fill="#FFD700", outline="black", width=2)
        bx, by = cx + 13, cy + 7
        if num == 1: d.rectangle([bx+2, by, bx+6, by+22], fill="black")
        elif num == 2:
            for r in [[0,0,10,3],[8,0,10,12],[0,10,10,13],[0,12,3,25],[0,22,10,25]]: d.rectangle([bx+r[0], by+r[1], bx+r[2], by+r[3]], fill="black")
        elif num == 3:
            for r in [[0,0,10,3],[8,0,10,25],[0,10,10,13],[0,22,10,25]]: d.rectangle([bx+r[0], by+r[1], bx+r[2], by+r[3]], fill="black")
        elif num == 4:
            for r in [[0,0,3,12],[0,10,15,13],[8,0,10,20]]: d.rectangle([bx+r[0], by+r[1], bx+r[2], by+r[3]], fill="black")

    for i, img in enumerate(images[:4]):
        collage.paste(img, positions[i])
        if i < len(image_urls):
            draw_num(draw, positions[i][0]+15, positions[i][1]+15, i+1)
            
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

def send_results_to_user(chat_id, products, query_text):
    if not products:
        bot.send_message(chat_id, "❌ לא מצאתי תוצאות. נסה חיפוש אחר.")
        return

    links = []
    for p in products: links.append(get_short_link(p['raw_url']))
    collage = create_collage([p['image'] for p in products])
    
    bot.send_photo(chat_id, collage, caption=f"🎯 <b>תוצאות עבור: {query_text}</b>", parse_mode="HTML")

    text_msg = "💎 <b>נבחרת הדילים של DrDeals</b>\n" + "—" * 12 + "\n\n"
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    
    for i, p in enumerate(products):
        short_url = links[i]
        text_msg += f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
        text_msg += f"💰 מחיר: <b>{p['price']}₪</b> | ⭐ דירוג: <b>{p['rating']}</b>\n"
        
        if p['discount'] > 0:
             text_msg += f"📉 <b>{p['discount']}% הנחה!</b> (במקום {p['orig_price']}₪)\n"

        if p['sales'] > 0:
            text_msg += f"🔥 נחטף ע''י: <b>{p['sales']}+ רוכשים</b>\n"
        else:
            text_msg += f"✨ <b>פריט מבוקש ומומלץ</b>\n"
            
        text_msg += f"🚚 <b>משלוח מהיר / Choice</b>\n"
        text_msg += f"🔗 {short_url}\n\n"
        
        buttons.append(types.InlineKeyboardButton(text=f"🎁 לקנייה {i+1}", url=short_url))

    text_msg += "—" * 12 + "\n🛍️ <b>קנייה מהנה! | DrDeals</b>"
    markup.add(*buttons)
    bot.send_message(chat_id, text_msg, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

# ==========================================================
#  הנדלר לפקודת ההתחלה - מעודכן (בלי תמונות)
# ==========================================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    # הטקסט המעודכן ללא אזכור חיפוש תמונה
    welcome_text = (
        "👋 <b>ברוכים הבאים ל-DrDeals!</b>\n"
        "הבוט החכם שימצא לכם את הדילים הכי שווים באליאקספרס.\n\n"
        "🤖 <b>מה אני יודע לעשות?</b>\n"
        "אני סורק את הרשת בזמן אמת ומוצא מוצרים עם:\n"
        "✅ דירוג איכות גבוה\n"
        "✅ כמות רכישות מוכחת\n"
        "✅ הנחות ומחירים משתלמים\n\n"
        "🚀 <b>איך משתמשים?</b>\n"
        "פשוט כתבו לי מה אתם מחפשים!\n"
        "לדוגמה:\n"
        "• <i>חפש לי אוזניות אלחוטיות</i>\n"
        "• <i>חפש לי שעון חכם</i>\n"
        "• <i>חפש לי מטען מהיר לאייפון</i>\n\n"
        "👇 <b>קדימה, נסו אותי! כתבו לי משהו...</b>"
    )

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("חפש לי שעון חכם")
    btn2 = types.KeyboardButton("חפש לי אוזניות")
    btn3 = types.KeyboardButton("חפש לי רחפן")
    btn4 = types.KeyboardButton("חפש לי מצלמת רכב")
    markup.add(btn1, btn2, btn3, btn4)

    # בדיקה אם קובץ התמונה קיים בתיקייה
    if os.path.exists('welcome.jpg'):
        try:
            with open('welcome.jpg', 'rb') as photo:
                bot.send_photo(message.chat.id, photo, caption=welcome_text, parse_mode="HTML", reply_markup=markup)
        except:
            bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup)

# --- הנדלר לתמונות (נשאר מוסתר ברקע) ---
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    # כאן לא שיניתי, כדי שאם בטעות ישלחו לא יקרוס, אבל זה לא מפורסם
    try:
        loading = bot.send_message(message.chat.id, "📸 <b>קולט תמונה ומפעיל סריקה...</b>", parse_mode="HTML")
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        products = engine.search_image(downloaded_file)
        bot.delete_message(message.chat.id, loading.message_id)
        
        if products is None:
             # הודעה מעודכנת - יותר כללית
            bot.send_message(message.chat.id, "⚠️ <b>חיפוש לפי תמונה לא זמין כרגע.</b>\nאנא כתוב לי את שם המוצר במקום.", parse_mode="HTML")
        elif not products:
             bot.send_message(message.chat.id, "❌ לא מצאתי מוצר דומה.")
        else:
            send_results_to_user(message.chat.id, products, "סריקת תמונה")
    except Exception as e:
        print(f"Error photo: {e}")
        bot.send_message(message.chat.id, "תקלה בעיבוד התמונה.")

# --- הנדלר לטקסט ---
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    try:
        query = message.text.strip()
        if not query.lower().startswith("חפש לי"): return
        search_query = query[7:].strip()
        
        loading = bot.send_message(message.chat.id, f"🔍 <b>סורק עבור: {search_query}...</b>", parse_mode="HTML")
        products = engine.search_text(search_query)
        
        bot.delete_message(message.chat.id, loading.message_id)
        send_results_to_user(message.chat.id, products, search_query)
    except Exception as e:
        print(f"Error text: {e}")

bot.remove_webhook()
bot.infinity_polling(timeout=60)
