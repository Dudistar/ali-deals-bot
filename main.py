import telebot
import requests
import io
import hashlib
import time
import html
import json
import re
import os
import google.generativeai as genai
from telebot import types
from PIL import Image, ImageDraw

# ניסיון לייבא תרגום, אם אין - לא נורא
try:
    from deep_translator import GoogleTranslator
except ImportError:
    pass

# ==========================================
# הגדרות ופרטים אישיים (הכל מעודכן בפנים)
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
ADMIN_ID = 173837076

# המפתח שלך לגוגל (AI)
GEMINI_API_KEY = "AIzaSyDNkixE64pO0muWxcqD2qtwZbTiH9UHT7w"

# חיבור למוח של גוגל
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

print("🔄 מתחבר לטלגרם...")
bot = telebot.TeleBot(BOT_TOKEN)
print("✅ הבוט מחובר - גרסת ה-AI המלאה")

class FreeSmartEngine:
    def __init__(self):
        pass

    def _enhance_query(self, user_query):
        try:
            # מתרגם לאנגלית כדי שאליאקספרס יבינו
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

    def _filter_with_ai(self, products, user_query):
        """
        כאן הקסם קורה: שולחים את הרשימה לגוגל והוא אומר מה זבל ומה זהב
        """
        if not products: return []
        
        # בניית הרשימה לבדיקה
        products_list_text = ""
        for i, p in enumerate(products):
            products_list_text += f"ID {i}: {p['title_en']} (Price: {p['price']} ILS)\n"

        # ההוראה למוח של גוגל
        prompt = f"""
        User searched for: "{user_query}".
        I have a list of products from AliExpress.
        Identify ONLY the products that actully match the user's intent to buy the MAIN ITEM.
        
        Strict Filtering Rules:
        1. If user asks for "Drone", include ONLY the drone itself. EXCLUDE parts, batteries, propellers, lights, or accessories.
        2. If user asks for "Pants" or "Trousers", EXCLUDE pajamas, sleepwear, shorts, or underwear.
        3. If user asks for "Phone", EXCLUDE cases, covers, and glass protectors.
        
        Here is the product list:
        {products_list_text}
        
        Return ONLY the IDs of the correct products, separated by commas (e.g., 0, 3, 4).
        If none match, return nothing.
        """

        try:
            response = model.generate_content(prompt)
            valid_ids_text = response.text.strip()
            
            if not valid_ids_text: return []
            
            # פענוח התשובה
            valid_indices = []
            for x in valid_ids_text.split(','):
                clean_x = x.strip()
                if clean_x.isdigit():
                    valid_indices.append(int(clean_x))
            
            # יצירת הרשימה הנקייה
            clean_products = [products[i] for i in valid_indices if i < len(products)]
            return clean_products

        except Exception as e:
            print(f"⚠️ AI Filter Error: {e}")
            # במקרה תקלה בגוגל - נחזיר את הרשימה כמו שהיא
            return products

    def _process_results(self, resp_json, search_term_en="", original_query_he=""):
        data = resp_json.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {})
        products_raw = data.get('products', {}).get('product', [])
        if not products_raw: return []
        if isinstance(products_raw, dict): products_raw = [products_raw]

        parsed_products = []
        
        for p in products_raw:
            try:
                sales = self._parse_sales(p)
                title_en = p['product_title']
                
                try: title_he = GoogleTranslator(source='auto', target='iw').translate(p['product_title'])
                except: title_he = p['product_title']

                try: price = float(p.get('target_sale_price', 0))
                except: price = 0
                
                try: orig_price = float(p.get('target_original_price', 0))
                except: orig_price = 0
                
                discount = 0
                if orig_price > price and price > 0:
                    discount = int(round((1 - (price / orig_price)) * 100))

                rate_str = str(p.get('evaluate_rate', '0')).replace('%', '')
                rating = float(rate_str) / 20 if rate_str else 0.0

                prod_obj = {
                    "title": title_he[:85],
                    "title_en": title_en, 
                    "price": price,
                    "orig_price": orig_price,
                    "discount": discount,
                    "image": p.get('product_main_image_url'),
                    "raw_url": p.get('product_detail_url', ''),
                    "rating": round(rating, 1) if rating > 0 else 4.8,
                    "sales": sales
                }
                parsed_products.append(prod_obj)
            except: continue

        # שליחה לגוגל לסינון (לוקחים 20 מוצרים לבדיקה)
        clean_products = self._filter_with_ai(parsed_products[:20], search_term_en)
        
        # מיון סופי לפי מכירות
        clean_products.sort(key=lambda x: x['sales'], reverse=True)
        return clean_products[:4]

    def search_text(self, original_query):
        search_term_en = self._enhance_query(original_query)
        print(f"🔎 מחפש: {search_term_en}")
        
        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'keywords': search_term_en, 'target_currency': 'ILS', 'ship_to_country': 'IL',
            'sort': 'LAST_VOLUME_DESC', 'page_size': '20', 
        }
        params['sign'] = generate_sign(params)
        try:
            resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
            return self._process_results(resp, search_term_en, original_query)
        except Exception as e:
            print(f"Error: {e}")
            return []

    def search_image(self, image_bytes):
        return []

engine = FreeSmartEngine()

# --- פונקציות עזר ---
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

def notify_admin(user, query_type, content):
    if not ADMIN_ID or ADMIN_ID == 0: return
    try:
        user_name = user.first_name
        username = f"(@{user.username})" if user.username else ""
        user_id = user.id
        msg = (
            f"🕵️‍♂️ <b>פעילות חדשה!</b>\n"
            f"👤 <b>משתמש:</b> {user_name} {username}\n"
            f"🆔 <b>מזהה:</b> {user_id}\n"
            f"🔍 <b>סוג:</b> {query_type}\n"
            f"📝 <b>תוכן:</b> {content}"
        )
        bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
    except Exception as e:
        print(f"Error notifying admin: {e}")

# ==========================================
# הנדלרים (תגובות הבוט)
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    notify_admin(message.from_user, "Start", "נכנס לבוט")
    
    welcome_text = (
        "👋 <b>ברוכים הבאים ל-DrDeals!</b>\n"
        "הבוט החכם שמשתמש בבינה מלאכותית 🤖 כדי למצוא לכם רק את הדילים השווים באמת.\n\n"
        "🚀 <b>איך משתמשים?</b>\n"
        "פשוט כתבו לי מה אתם מחפשים!\n"
        "לדוגמה:\n"
        "• <i>חפש לי אוזניות אלחוטיות</i>\n"
        "• <i>חפש לי רחפן עם מצלמה</i>\n"
        "• <i>חפש לי מכנסי אלגנט</i>\n\n"
        "👇 <b>קדימה, נסו אותי! כתבו לי משהו...</b>"
    )

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("חפש לי שעון חכם")
    btn2 = types.KeyboardButton("חפש לי אוזניות")
    btn3 = types.KeyboardButton("חפש לי רחפן")
    btn4 = types.KeyboardButton("חפש לי מצלמת רכב")
    markup.add(btn1, btn2, btn3, btn4)

    if os.path.exists('welcome.jpg'):
        try:
            with open('welcome.jpg', 'rb') as photo:
                bot.send_photo(message.chat.id, photo, caption=welcome_text, parse_mode="HTML", reply_markup=markup)
        except:
            bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    bot.reply_to(message, "⚠️ חיפוש לפי תמונה יחזור בקרוב.")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    try:
        query = message.text.strip()
        notify_admin(message.from_user, "Text Search", query)

        if not query.lower().startswith("חפש לי"):
             # אם המשתמש סתם כותב טקסט, נזרום איתו
             if len(query) > 2:
                 search_query = query
             else:
                 return
        else:
            search_query = query[7:].strip()
        
        loading = bot.send_message(message.chat.id, f"🤖 <b>ה-AI סורק ומסנן תוצאות עבור: {search_query}...</b>", parse_mode="HTML")
        products = engine.search_text(search_query)
        
        bot.delete_message(message.chat.id, loading.message_id)
        
        if not products:
            bot.send_message(message.chat.id, "❌ לא מצאתי תוצאות מדויקות מספיק (ה-AI סינן הכל). נסה ניסוח אחר.")
            return

        links = []
        for p in products: links.append(get_short_link(p['raw_url']))
        collage = create_collage([p['image'] for p in products])
        
        bot.send_photo(message.chat.id, collage, caption=f"🎯 <b>תוצאות עבור: {search_query}</b>", parse_mode="HTML")

        text_msg = "💎 <b>נבחרת הדילים (מסונן ע''י AI)</b>\n" + "—" * 12 + "\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = []
        
        for i, p in enumerate(products):
            short_url = links[i]
            text_msg += f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
            text_msg += f"💰 מחיר: <b>{p['price']}₪</b> | ⭐ {p['rating']}\n"
            if p['discount'] > 0:
                 text_msg += f"📉 <b>{p['discount']}% הנחה!</b>\n"
            
            text_msg += f"🔗 {short_url}\n\n"
            buttons.append(types.InlineKeyboardButton(text=f"🎁 לקנייה {i+1}", url=short_url))

        text_msg += "🛍️ <b>קנייה מהנה! | DrDeals</b>"
        markup.add(*buttons)
        bot.send_message(message.chat.id, text_msg, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
            
    except Exception as e:
        print(f"Error text: {e}")

bot.remove_webhook()
bot.infinity_polling(timeout=60)
