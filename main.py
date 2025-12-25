import telebot
import requests
import io
import hashlib
import time
import html
import json
import re # הוספנו לטובת ניקוי כותרות
from telebot import types
from PIL import Image, ImageDraw

# בדיקה שספריית התרגום קיימת
try:
    from deep_translator import GoogleTranslator
except ImportError:
    print("❌ שגיאה: ספריית deep_translator חסרה!")
    print("אנא הרץ בטרמינל: pip install deep-translator")
    exit()

# ==========================================
# הגדרות ופרטים אישיים
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

print("🔄 מתחבר לטלגרם...")
bot = telebot.TeleBot(BOT_TOKEN)
print("✅ הבוט מחובר ומוכן לעבודה!")

# ==============================================================================
#  המנוע החכם - גרסה מתוקנת (חילוץ מכירות מתקדם)
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

    def _parse_sales(self, p):
        """פונקציה אגרסיבית לחילוץ מספר מכירות"""
        # רשימת כל השדות האפשריים שבהם אליאקספרס מחביאים את המכירות
        keys_to_check = ['last_volume', 'sale_volume', 'app_sale_volume', 'orders', 'volume']
        
        for key in keys_to_check:
            val = p.get(key)
            if not val: continue
            
            # המרה לטקסט וניקוי
            val_str = str(val).lower().replace(',', '').replace('+', '').replace(' sold', '').replace('orders', '').strip()
            
            try:
                multiplier = 1
                if 'k' in val_str:
                    multiplier = 1000
                    val_str = val_str.replace('k', '')
                elif 'w' in val_str: # סימון סיני ל-10,000 לפעמים בורח ל-API
                    multiplier = 10000
                    val_str = val_str.replace('w', '')
                elif 'm' in val_str:
                    multiplier = 1000000
                    val_str = val_str.replace('m', '')
                
                # המרה למספר
                number = float(val_str) * multiplier
                
                if number > 0:
                    return int(number)
            except:
                continue
                
        return 0

    def search(self, original_query):
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
            resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
            data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {})
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

                    parsed_products.append({
                        "title": title_he[:85],
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
#  פונקציות עזר ועיצוב
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

def draw_small_number(draw, cx, cy, num):
    draw.ellipse((cx, cy, cx+35, cy+35), fill="#FFD700", outline="black", width=2)
    bx, by = cx + 13, cy + 7
    if num == 1: draw.rectangle([bx+2, by, bx+6, by+22], fill="black")
    elif num == 2:
        for r in [[0,0,10,3],[8,0,10,12],[0,10,10,13],[0,12,3,25],[0,22,10,25]]:
            draw.rectangle([bx+r[0], by+r[1], bx+r[2], by+r[3]], fill="black")
    elif num == 3:
        for r in [[0,0,10,3],[8,0,10,25],[0,10,10,13],[0,22,10,25]]:
            draw.rectangle([bx+r[0], by+r[1], bx+r[2], by+r[3]], fill="black")
    elif num == 4:
        for r in [[0,0,3,12],[0,10,15,13],[8,0,10,20]]:
            draw.rectangle([bx+r[0], by+r[1], bx+r[2], by+r[3]], fill="black")

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
    
    for i, img in enumerate(images[:4]):
        collage.paste(img, positions[i])
        if i < len(image_urls):
            draw_small_number(draw, positions[i][0]+15, positions[i][1]+15, i+1)
            
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        query = message.text.strip()
        if not query.lower().startswith("חפש לי"): return
        search_query = query[7:].strip()
        
        loading = bot.send_message(message.chat.id, f"🔍 <b>סורק את הרשת עבור: {search_query}...</b>", parse_mode="HTML")
        
        products = engine.search(search_query)
        
        if not products:
            bot.edit_message_text("❌ לא מצאתי תוצאות איכותיות. נסה חיפוש אחר.", message.chat.id, loading.message_id)
            return

        links = []
        for p in products: links.append(get_short_link(p['raw_url']))
        
        collage = create_collage([p['image'] for p in products])
        bot.delete_message(message.chat.id, loading.message_id)
        
        bot.send_photo(message.chat.id, collage, caption=f"🎯 <b>הדילים הכי טובים ל-{search_query}:</b>", parse_mode="HTML")

        text_msg = "💎 <b>נבחרת הדילים של DrDeals</b>\n" + "—" * 12 + "\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = []
        
        for i, p in enumerate(products):
            short_url = links[i]
            
            # --- שיפור התצוגה ---
            text_msg += f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
            text_msg += f"💰 מחיר: <b>{p['price']}₪</b> | ⭐ דירוג: <b>{p['rating']}</b>\n"
            
            # הצגת מכירות רק אם יש מספר אמיתי
            if p['sales'] > 0:
                text_msg += f"🔥 נחטף ע''י: <b>{p['sales']}+ רוכשים</b>\n"
            else:
                # אם אין מספר - שמים שורה אחרת שלא נראית כמו באג
                text_msg += f"✨ <b>פריט מבוקש ומומלץ</b>\n"
            
            text_msg += f"🚚 <b>משלוח מהיר / Choice</b>\n"
            text_msg += f"🔗 {short_url}\n\n"
            
            buttons.append(types.InlineKeyboardButton(text=f"🎁 לקנייה {i+1}", url=short_url))

        text_msg += "—" * 12 + "\n🛍️ <b>קנייה מהנה! | DrDeals</b>"
        markup.add(*buttons)
        
        bot.send_message(message.chat.id, text_msg, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        
    except Exception as e:
        print(f"Error: {e}")

bot.remove_webhook()
bot.infinity_polling(timeout=60)
