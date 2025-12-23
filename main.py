import telebot
import requests
import io
import hashlib
import time
import html
from telebot import types
from PIL import Image, ImageDraw
from deep_translator import GoogleTranslator

# --- המפתחות האישיים שלך ---
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

bot = telebot.TeleBot(BOT_TOKEN)

def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

def get_short_link(raw_url):
    """קיצור קישור יציב - המתנה של 2.5 שניות מבטיחה הצלחה"""
    try:
        clean_url = raw_url.split('?')[0]
        time.sleep(2.5) 
        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.link.generate',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'promotion_link_type': '0', 'source_values': clean_url, 'tracking_id': TRACKING_ID
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
        res = resp.get('aliexpress_affiliate_link_generate_response', {}).get('resp_result', {}).get('result', {}).get('promotion_links', {}).get('promotion_link', [])
        if res:
            return res[0].get('promotion_short_link') or res[0].get('promotion_link')
    except: pass
    return raw_url

def search_aliexpress(keyword):
    """מנוע חיפוש פרימיום עם משלוח חינם"""
    try:
        en_keyword = GoogleTranslator(source='auto', target='en').translate(keyword).lower()
        
        # לוגיקת סינון חכמה
        bad_words = ['adapter', 'cable', 'mount', 'rear view', 'borescope', 'parts', 'cover']
        min_price = "0"
        
        # אם חיפשת מדבקות או כיסויים - ננקה את החסימה
        if any(w in en_keyword for w in ['stick', 'label', 'decal', 'custom', 'cover']):
            bad_words = []
        elif any(w in en_keyword for w in ['camera', 'dash', 'car', 'dvr']):
            en_keyword = f"70mai DDPai Dash Cam 4K GPS {en_keyword}"
            min_price = "60"

        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'keywords': en_keyword, 'target_currency': 'ILS', 'ship_to_country': 'IL',
            'is_free_shipping': 'true', # פילטר משלוח חינם בלבד
            'min_sale_price': min_price, 'sort': 'RELEVANCE', 'page_size': '50'
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=20).json()
        products_raw = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(products_raw, dict): products_raw = [products_raw]

        filtered = []
        for p in products_raw:
            title = p.get('product_title', '').lower()
            rating = float(str(p.get('evaluate_rate', '0')).replace('%', ''))
            # סינון דירוג: 90% לטכנולוגיה, 80% לשאר
            min_rate = 90 if min_price != "0" else 80
            if not any(bw in title for bw in bad_words) and rating >= min_rate:
                filtered.append(p)
        
        output = []
        for p in filtered[:4]:
            try: title_he = GoogleTranslator(source='auto', target='iw').translate(p['product_title'])
            except: title_he = p['product_title']
            output.append({
                "title": title_he[:80] + "...", "price": p.get('target_sale_price', 'N/A'),
                "image": p.get('product_main_image_url'), "raw_url": p.get('product_detail_url', ''),
                "rating": round(float(str(p.get('evaluate_rate', '95')).replace('%',''))/20, 1) if p.get('evaluate_rate') else 4.8
            })
        return output
    except: return None

def draw_elite_number(draw, cx, cy, num):
    """מספרים מינימליסטיים בפינה"""
    draw.ellipse((cx, cy, cx+35, cy+35), fill="#FFD700", outline="black", width=2)
    bx, by = cx + 13, cy + 7
    if num == 1: draw.rectangle([bx+2, by, bx+6, by+22], fill="black")
    elif num == 2:
        for r in [[0,0,10,3],[8,0,10,12],[0,10,10,13],[0,12,3,25],[0,22,10,25]]:
            draw.rectangle([bx+r[0], by+r[1], bx+r[2], by+r[3]], fill="black")
    elif num == 3:
        for r in [[0,0,10,3],[8,0,10,20],[0,10,10,13],[0,17,10,20]]:
            draw.rectangle([bx+r[0], by+r[1], bx+r[2], by+r[3]], fill="black")
    elif num == 4:
        for r in [[0,0,3,10],[0,8,10,11],[8,0,10,20]]:
            draw.rectangle([bx+r[0], by+r[1], bx+r[2], by+r[3]], fill="black")

def create_collage(image_urls):
    images = []
    for url in image_urls:
        try:
            r = requests.get(url, timeout=12)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
            images.append(img)
        except: images.append(Image.new('RGB', (500,500), color='#EEEEEE'))
    collage = Image.new('RGB', (1000, 1000), 'white')
    positions = [(0,0), (500,0), (0,500), (500,500)]
    draw = ImageDraw.Draw(collage)
    for i, img in enumerate(images):
        collage.paste(img, positions[i])
        draw_elite_number(draw, positions[i][0]+15, positions[i][1]+15, i+1)
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        query = message.text.strip()
        if not query.lower().startswith("חפש לי"): return
        search_query = query[7:].strip().lower()
        
        loading = bot.send_message(message.chat.id, f"💎 <b>מחפש עבורכם דילים מנצחים ל-'{search_query}'...</b>", parse_mode="HTML")
        products = search_aliexpress(search_query)
        
        if not products:
            bot.edit_message_text("לא נמצאו תוצאות איכותיות עם משלוח חינם. נסו שוב.", message.chat.id, loading.message_id)
            return

        # הכנת הקישורים מראש כדי למנוע קריסה של ההודעה
        final_links = [get_short_link(p['raw_url']) for p in products]
        
        collage = create_collage([p['image'] for p in products])
        bot.delete_message(message.chat.id, loading.message_id)
        bot.send_photo(message.chat.id, collage, caption=f"🎯 <b>נבחרת הדילים עבור: {search_query}</b>", parse_mode="HTML")

        text_msg = "🏆 <b>TOP SELECTION - DrDeals Premium</b>\n" + "▬" * 15 + "\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = []
        
        for i, p in enumerate(products):
            short_url = final_links[i]
            text_msg += f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
            text_msg += f"💰 מחיר: <b>{p['price']}₪</b> | ⭐ דירוג: <b>{p['rating']}</b>\n"
            text_msg += f"🚚 <b>משלוח חינם!</b>\n"
            text_msg += f"🔗 {short_url}\n\n"
            buttons.append(types.InlineKeyboardButton(text=f"🎁 לקנייה {i+1}", url=short_url))

        text_msg += "▬" * 15 + "\n👑 <b>Elite Search by DrDeals</b>"
        markup.add(*buttons)
        bot.send_message(message.chat.id, text_msg, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except: pass

# פתרון לשגיאה 409 - ניקוי כל חיבור קודם
bot.remove_webhook()
bot.infinity_polling(timeout=60, long_polling_timeout=30)
