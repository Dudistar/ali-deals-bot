import telebot
import requests
import io
import hashlib
import time
import html
import json
from telebot import types
from PIL import Image, ImageDraw
from deep_translator import GoogleTranslator

# ==========================================
# הגדרות מערכת ופרטי גישה
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

bot = telebot.TeleBot(BOT_TOKEN)

# ==============================================================================
#  המנוע החכם - גרסת החינם המשופרת (Tiered Search)
# ==============================================================================

class FreeSmartEngine:
    def __init__(self):
        # מילון מילות כוח - מוסיף מילים מקצועיות לחיפוש אוטומטית
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
            "lamp": "led dimmable smart",
            "bag": "waterproof anti-theft",
            "dash": "70mai ddpai 4k", # חיזוק ספציפי למצלמות רכב
            "mouse": "ergonomic wireless silent"
        }

    def _enhance_query(self, user_query):
        """תרגום ושיפור מילות החיפוש"""
        try:
            # תרגום עברית לאנגלית
            en_query = GoogleTranslator(source='auto', target='en').translate(user_query).lower()
            
            # בדיקת מילות כוח
            final_query = en_query
            for key, boost in self.keyword_booster.items():
                if key in en_query:
                    # אם המילה קיימת, נוסיף את הביטוי המקצועי
                    if boost not in en_query: 
                        final_query = f"{en_query} {boost}"
                    break
            
            return final_query
        except:
            return user_query # במקרה של תקלה בתרגום, מחזיר את המקור

    def search(self, original_query):
        """הלוגיקה המרכזית: מנסה להביא את הכי טוב, אבל לא מחזיר ריק"""
        
        # 1. הכנת מילות חיפוש
        smart_keywords = self._enhance_query(original_query)
        print(f"[*] Processing Query: '{original_query}' -> '{smart_keywords}'")

        # 2. שליפת נתונים רחבה מאליאקספרס
        # הסרנו פילטרים קשוחים מה-API כדי לקבל כמה שיותר תוצאות לסינון עצמי
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
            'sort': 'LAST_VOLUME_DESC', # הכי נמכרים
            'page_size': '50', # מושכים מספיק כדי שיהיה ממה לבחור
        }
        params['sign'] = generate_sign(params)
        
        try:
            resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
            data = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {})
            products_raw = data.get('products', {}).get('product', [])
            
            if not products_raw:
                print("[-] AliExpress API returned 0 results.")
                return []
            
            if isinstance(products_raw, dict): products_raw = [products_raw]

            # 3. נרמול נתונים (סידור המספרים)
            parsed_products = []
            for p in products_raw:
                try:
                    sales = int(p.get('last_volume', 0))
                    
                    # טיפול בדירוג (לפעמים מגיע ריק)
                    rate_str = str(p.get('evaluate_rate', '0')).replace('%', '')
                    if not rate_str or rate_str == '0':
                        rating = 4.5 # ברירת מחדל למוצר חדש ומבטיח
                    else:
                        rating = float(rate_str) / 20
                    
                    # תרגום כותרת לעברית לתצוגה יפה
                    try: title_he = GoogleTranslator(source='auto', target='iw').translate(p['product_title'])
                    except: title_he = p['product_title']

                    parsed_products.append({
                        "title": title_he[:80], # חיתוך כותרת ארוכה
                        "price": p.get('target_sale_price', 'N/A'),
                        "image": p.get('product_main_image_url'),
                        "raw_url": p.get('product_detail_url', ''),
                        "rating": round(rating, 1),
                        "sales": sales
                    })
                except Exception as e:
                    continue

            if not parsed_products:
                return []

            # 4. מדרג הסינון (The Tier System)
            
            # שלב א': היהלומים (דירוג מעולה + מכירות מוכחות)
            premium = [p for p in parsed_products if p['rating'] >= 4.7 and p['sales'] >= 10]
            if len(premium) >= 2:
                print(f"[+] Found {len(premium)} Premium items")
                premium.sort(key=lambda x: x['sales'], reverse=True)
                return premium[:4]
            
            # שלב ב': האיכותיים (דירוג טוב)
            good = [p for p in parsed_products if p['rating'] >= 4.5]
            if len(good) >= 1:
                print(f"[+] Found {len(good)} Good items (Tier 2)")
                good.sort(key=lambda x: x['sales'], reverse=True)
                return good[:4]
            
            # שלב ג': רשת הביטחון (פשוט הכי נמכרים)
            print("[+] Fallback to Top Sales (Tier 3)")
            parsed_products.sort(key=lambda x: x['sales'], reverse=True)
            return parsed_products[:4]

        except Exception as e:
            print(f"Search Engine Error: {e}")
            return []

engine = FreeSmartEngine()

# ==============================================================================
#  פונקציות עזר (חתימות, קיצורים, תמונות)
# ==============================================================================

def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

def get_short_link(raw_url):
    clean_url = raw_url.split('?')[0]
    try:
        # time.sleep(0.2) # מינימום המתנה
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
    # ציור מספרים על הקולאז'
    draw.ellipse((cx, cy, cx+35, cy+35), fill="#FFD700", outline="black", width=2)
    bx, by = cx + 13, cy + 7
    # פונט ידני פשוט (פיקסלים)
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
            r = requests.get(url, timeout=10)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
            images.append(img)
        except: images.append(Image.new('RGB', (500,500), color='#EEEEEE'))
    
    # אם יש פחות מ-4 תמונות, נשלים ל-4 כדי שהקוד לא יקרוס
    while len(images) < 4:
        images.append(Image.new('RGB', (500,500), color='#FFFFFF'))

    collage = Image.new('RGB', (1000, 1000), 'white')
    positions, draw = [(0,0), (500,0), (0,500), (500,500)], ImageDraw.Draw(collage)
    
    for i, img in enumerate(images[:4]):
        collage.paste(img, positions[i])
        # מצייר מספר רק אם יש שם מוצר אמיתי
        if i < len(image_urls):
            draw_small_number(draw, positions[i][0]+15, positions[i][1]+15, i+1)
            
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

# ==============================================================================
#  טלגרם הנדלר - הממשק מול המשתמש
# ==============================================================================

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        query = message.text.strip()
        if not query.lower().startswith("חפש לי"): return
        search_query = query[7:].strip()
        
        # הודעת פתיחה
        loading = bot.send_message(message.chat.id, f"🕵️‍♂️ <b>מפעיל סוכנים לאיתור: {search_query}...</b>", parse_mode="HTML")
        
        # הרצת החיפוש החכם
        products = engine.search(search_query)
        
        if not products:
            bot.edit_message_text("❌ לא מצאתי תוצאות. נסה לחפש באנגלית או מילים כלליות יותר.", message.chat.id, loading.message_id)
            return

        # המרת קישורים (לוקח שניה-שתיים)
        links = []
        for p in products:
            links.append(get_short_link(p['raw_url']))
        
        # יצירת תמונה
        collage = create_collage([p['image'] for p in products])
        bot.delete_message(message.chat.id, loading.message_id)
        
        # כותרת ההודעה
        caption_text = f"🎯 <b>הנה מה שמצאתי עבור: {search_query}</b>"
        bot.send_photo(message.chat.id, collage, caption=caption_text, parse_mode="HTML")

        # תוכן ההודעה והכפתורים
        text_msg = "💎 <b>המומלצים של DrDeals</b>\n" + "—" * 15 + "\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1) # כפתור אחד בשורה לנוחות
        buttons = []
        
        for i, p in enumerate(products):
            short_url = links[i]
            # בניית הטקסט לכל מוצר
            text_msg += f"<b>{i+1}. {html.escape(p['title'])}</b>\n"
            text_msg += f"⭐ דירוג: <b>{p['rating']}</b> | 🔥 נמכר: <b>{p['sales']}+ יח'</b>\n"
            text_msg += f"💵 מחיר: <b>{p['price']}₪</b>\n"
            text_msg += f"🔗 <i>לחץ למטה לרכישה</i>\n\n"
            
            # כפתור הנעה לפעולה
            btn_text = f"🛍️ לרכישת מוצר {i+1} ב-{p['price']}₪"
            buttons.append(types.InlineKeyboardButton(text=btn_text, url=short_url))

        text_msg += "—" * 15 + "\n🛡️ <b>קנייה בטוחה דרך אליאקספרס</b>"
        markup.add(*buttons)
        
        bot.send_message(message.chat.id, text_msg, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        try:
            bot.send_message(message.chat.id, "אופס, קרתה תקלה טכנית קטנה. נסה שוב עוד רגע.")
        except: pass

print("✅ Bot is live and running with Tiered Search Engine!")
bot.remove_webhook()
bot.infinity_polling(timeout=60)
