import telebot
import requests
import io
import hashlib
import time
import json
import html
from telebot import types
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator

# --- הפרטים שלך ---
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asQV78oziICQEs"
TRACKING_ID = "DrDeals"

bot = telebot.TeleBot(BOT_TOKEN)

def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

def get_short_link(raw_url):
    try:
        time.sleep(1.2)
        clean_url = raw_url.split('?')[0]
        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.link.generate',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'promotion_link_type': '0', 'source_values': clean_url, 'tracking_id': TRACKING_ID
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=5).json()
        res = resp.get('aliexpress_affiliate_link_generate_response', {}).get('resp_result', {}).get('result', {}).get('promotion_links', {}).get('promotion_link', [])
        if res:
            return res[0].get('promotion_link') or res[0].get('promotion_short_link')
    except: pass
    return raw_url

def search_aliexpress(keyword):
    """חיפוש עם סינון חכם של אביזרים לא רלוונטיים"""
    try:
        en_keyword = GoogleTranslator(source='auto', target='en').translate(keyword).lower()
        query_words = en_keyword.split()
        
        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'keywords': en_keyword, 'target_currency': 'ILS', 'ship_to_country': 'IL',
            'sort': 'LAST_VOLUME_DESC', 'page_size': '30' # מושכים יותר תוצאות כדי שיהיה ממה לסנן
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10).json()
        products_raw = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        
        if isinstance(products_raw, dict): products_raw = [products_raw]
        
        results = []
        # רשימת אביזרים לסינון חכם
        accessories = ['reader', 'adapter', 'cable', 'case', 'cover', 'mount', 'stand', 'bag', 'card', 'holder']
        
        for p in products_raw:
            if len(results) >= 4: break
            title_raw = p.get('product_title', '').lower()
            
            # בדיקה האם המוצר הוא אביזר
            is_acc = any(acc in title_raw for acc in accessories)
            query_is_acc = any(word in accessories for word in query_words)
            
            # אם זה אביזר והמשתמש לא חיפש אביזר - נדלג עליו
            if is_acc and not query_is_acc:
                continue
            
            try: title_he = GoogleTranslator(source='auto', target='iw').translate(p.get('product_title', ''))
            except: title_he = p.get('product_title', '')
            if len(title_he) > 55: title_he = title_he[:52] + "..."

            try:
                raw_rate = float(str(p.get('evaluate_rate', '95')).replace('%', ''))
                star_rating = round(raw_rate / 20, 1) if raw_rate > 5 else round(raw_rate, 1)
            except: star_rating = 4.8

            results.append({
                "title": title_he, "price": p.get('target_sale_price','N/A'),
                "image": p.get('product_main_image_url'), "raw_url": p.get('product_detail_url',''),
                "rating": star_rating, "orders": p.get('lastest_volume','Top'),
                "discount": p.get('discount','0%')
            })
        return results
    except: return None

def create_collage(image_urls):
    images = []
    sq = 500
    for url in image_urls:
        try:
            r = requests.get(url, timeout=10)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((sq,sq))
            images.append(img)
        except: images.append(Image.new('RGB', (sq,sq), color='#EEEEEE'))
    while len(images) < 4: images.append(Image.new('RGB', (sq,sq), color='#EEEEEE'))
    collage = Image.new('RGB', (sq*2, sq*2), 'white')
    positions = [(0,0), (sq,0), (0,sq), (sq,sq)]
    draw = ImageDraw.Draw(collage)
    try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 150)
    except: font = ImageFont.load_default()
    for i, img in enumerate(images):
        collage.paste(img, positions[i])
        cx, cy = positions[i][0] + 30, positions[i][1] + 30
        draw.ellipse((cx, cy, cx+160, cy+160), fill="#FFD700", outline="black", width=10)
        draw.text((cx + 45, cy + 5), str(i+1), fill="black", font=font)
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        query = message.text.strip()
        if not query.lower().startswith("חפש לי"):
            bot.reply_to(message, "שלום! כדי לחפש דילים כתבו: 'חפש לי' ואז שם המוצר.")
            return
        search_query = query[7:].strip()
        loading = bot.send_message(message.chat.id, f"🔎 מחפש עבורכם דילים ל-'{search_query}'...")
        products = search_aliexpress(search_query)
        if not products:
            bot.edit_message_text("לא נמצאו תוצאות מדויקות. נסו חיפוש אחר.", message.chat.id, loading.message_id)
            return
        img_urls = [p['image'] for p in products if p.get('image')]
        collage = create_collage(img_urls)
        bot.delete_message(message.chat.id, loading.message_id)
        bot.send_photo(message.chat.id, collage, caption=f"🎯 מוצרים מומלצים עבור: <b>{search_query}</b>", parse_mode="HTML")
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = []
        text_msg = "⭐️ <b>דילים נבחרים:</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        for i, p in enumerate(products):
            short_url = get_short_link(p['raw_url'])
            text_msg += f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
            text_msg += f"🔥 הנחה באתר: <b>-{p['discount']}</b>\n"
            text_msg += f"💰 מחיר: <b>{p['price']}₪</b>\n"
            text_msg += f"⭐ דירוג: {p['rating']}/5 | 🛒 רכישות: {p['orders']}\n"
            text_msg += f"🔗 {short_url}\n\n"
            buttons.append(types.InlineKeyboardButton(text=f"🎁 לקנייה {i+1}", url=short_url))
        text_msg += "▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n🤖 <i>DrDeals - צייד הדילים</i>"
        markup.add(*buttons)
        bot.send_message(message.chat.id, text_msg, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except: pass

print("Bot is LIVE - High Accuracy Edition!")
bot.infinity_polling()
