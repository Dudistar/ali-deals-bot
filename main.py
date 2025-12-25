
import telebot
import requests
import io
import hashlib
import time
import html
import json
from telebot import types
from PIL import Image, ImageDraw
try:
    from deep_translator import GoogleTranslator
except ImportError:
    print("❌ שגיאה: ספריית deep_translator חסרה!")
    print("אנא הרץ בטרמינל: pip install deep-translator")
    input("לחץ אנטר ליציאה...")
    exit()

# ==========================================
# הפרטים האישיים שלך (לא נגעתי בהם!)
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

print("🔄 מתחבר לטלגרם...")
try:
    bot = telebot.TeleBot(BOT_TOKEN)
    print("✅ מחובר בהצלחה! הבוט מאזין...")
except Exception as e:
    print(f"❌ שגיאה בהתחברות לבוט: {e}")
    exit()

# ==============================================================================
#  המנוע החכם - גרסת Debug (בודק למה אין תוצאות)
# ==============================================================================

class FreeSmartEngine:
    def __init__(self):
        self.keyword_booster = {
            "charger": "GaN fast charging",
            "cable": "braided fast data",
            "headphones": "noise cancelling bluetooth 5.3",
            "earbuds": "tws anc",
            "watch": "amoled smart watch waterproof",
            "case": "shockproof silicone",
            "screen protector": "tempered glass 9h",
            "camera": "4k wifi ip",
            "cleaner": "robot vacuum parts",
            "holder": "car mount magnetic strong",
            "bag": "waterproof anti-theft",
            "dash": "70mai ddpai 4k",
        }

    def _enhance_query(self, user_query):
        try:
            en_query = GoogleTranslator(source='auto', target='en').translate(user_query).lower()
            final_query = en_query
            for key, boost in self.keyword_booster.items():
                if key in en_query and boost not in en_query:
                    final_query = f"{en_query} {boost}"
                    break
            return final_query
        except:
            return user_query

    def search(self, original_query):
        print("\n" + "-"*30)
        print(f"🔎 מחפש: {original_query}")
        
        smart_keywords = self._enhance_query(original_query)
        
        params = {
            'app_key': APP_KEY,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5',
            'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot',
            'format': 'json',
            'v': '2.0',
            'keywords': smart_keywords,
            'target_currency': 'ILS',
            'ship_to_country': 'IL',
            'sort': 'LAST_VOLUME_DESC',
            'page_size': '50',
        }
        params['sign'] = generate_sign(params)
        
        try:
            print("⏳ שולח בקשה ל-AliExpress...")
            resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
            
            if 'error_response' in resp:
                print(f"❌ שגיאת API: {resp['error_response']}")
                return []
            
            data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {})
            products_raw = data.get('products', {}).get('product', [])
            
            if not products_raw:
                print("⚠️ ה-API החזיר 0 מוצרים.")
                return []
            
            if isinstance(products_raw, dict): products_raw = [products_raw]

            print(f"📦 התקבלו {len(products_raw)} מוצרים. מסנן...")

            parsed_products = []
            for p in products_raw:
                try:
                    sales = int(p.get('last_volume', 0))
                    rate_str = str(p.get('evaluate_rate', '0')).replace('%', '')
                    rating = float(rate_str) / 20 if rate_str else 0.0
                    
                    parsed_products.append({
                        "title": p['product_title'],
                        "price": p.get('target_sale_price', 'N/A'),
                        "image": p.get('product_main_image_url'),
                        "raw_url": p.get('product_detail_url', ''),
                        "rating": round(rating, 1),
                        "sales": sales
                    })
                except: continue

            # מדרג איכות
            premium = [p for p in parsed_products if p['rating'] >= 4.7 and p['sales'] >= 10]
            if len(premium) >= 2:
                premium.sort(key=lambda x: x['sales'], reverse=True)
                return premium[:4]
            
            good = [p for p in parsed_products if p['rating'] >= 4.5]
            if len(good) >= 1:
                good.sort(key=lambda x: x['sales'], reverse=True)
                return good[:4]
            
            parsed_products.sort(key=lambda x: x['sales'], reverse=True)
            return parsed_products[:4]

        except Exception as e:
            print(f"❌ שגיאה בחיפוש: {e}")
            return []

engine = FreeSmartEngine()

# ==============================================================================
#  פונקציות עזר (חתימה, קיצור, תמונה)
# ==============================================================================

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
    collage.save(output, format='JPEG', quality=85)
    output.seek(0)
    return output

# ==============================================================================
#  טלגרם הנדלר
# ==============================================================================

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        query = message.text.strip()
        if not query.lower().startswith("חפש לי"): return
        search_query = query[7:].strip()
        
        loading = bot.send_message(message.chat.id, f"🔍 מחפש: {search_query}...")
        
        products = engine.search(search_query)
        
        if not products:
            bot.edit_message_text("❌ לא נמצאו תוצאות.", message.chat.id, loading.message_id)
            return

        links = []
        for p in products: links.append(get_short_link(p['raw_url']))
        
        collage = create_collage([p['image'] for p in products])
        bot.delete_message(message.chat.id, loading.message_id)
        
        caption = f"תוצאות עבור: {search_query}"
        bot.send_photo(message.chat.id, collage, caption=caption)

        text_msg = "💎 התוצאות:\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for i, p in enumerate(products):
            text_msg += f"{i+1}. {p['title'][:40]}...\n💵 {p['price']}₪ | ⭐ {p['rating']}\n\n"
            markup.add(types.InlineKeyboardButton(f"לקנייה ({p['price']}₪)", url=links[i]))

        bot.send_message(message.chat.id, text_msg, reply_markup=markup)
        
    except Exception as e:
        print(f"Error: {e}")

bot.remove_webhook()
bot.infinity_polling(timeout=60)
