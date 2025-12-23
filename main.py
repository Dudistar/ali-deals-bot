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

# --- הפרטים האישיים שלך ---
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
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
        response = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=5).json()
        res = response.get('aliexpress_affiliate_link_generate_response', {}).get('resp_result', {}).get('result', {}).get('promotion_links', {}).get('promotion_link', [])
        if res:
            return res[0].get('promotion_short_link') or res[0].get('promotion_link')
    except: pass
    return raw_url

def search_aliexpress(keyword):
    try:
        en_keyword = GoogleTranslator(source='auto', target='en').translate(keyword).lower()
        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'keywords': en_keyword, 'target_currency': 'ILS', 'ship_to_country': 'IL',
            'sort': 'LAST_VOLUME_DESC', 'page_size': '10'
        }
        params['sign'] = generate_sign(params)
        response = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10).json()
        res_data = response.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {})
        products_raw = res_data.get('products', {}).get('product', [])
        
        if isinstance(products_raw, dict): products_raw = [products_raw]
        
        results = []
        for p in products_raw:
            if len(results) >= 4: break
            title_raw = p.get('product_title', 'מוצר')
            try: title_he = GoogleTranslator(source='auto', target='iw').translate(title_raw)
            except: title_he = title_raw
            if len(title_he) > 50: title_he = title_he[:47] + "..."
            
            # חישוב הדירוג: הפיכת אחוזים למספר (למשל 96% הופך ל-4.8)
            try:
                raw_rate = float(str(p.get('evaluate_rate', '95')).replace('%', ''))
                star_rating = round(raw_rate / 20, 1) if raw_rate > 5 else round(raw_rate, 1)
            except: star_rating = 4.8

            results.append({
                "title": title_he, "price": p.get('target_sale_price', 'N/A'),
                "image": p.get('product_main_image_url'), "raw_url": p.get('product_detail_url', ''),
                "rating": star_rating, "orders": p.get('lastest_volume', "Top"),
                "discount": p.get('discount', '0%')
            })
        return results
    except: return None

def create_collage(image_urls):
    images = []
    sq = 500
    for url in image_urls:
        try:
            r = requests.get(url, timeout=10)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((sq, sq))
            images.append(img)
        except: images.append(Image.new('RGB', (sq, sq), color='#EEEEEE'))
    while len(images) < 4: images.append(Image.new('RGB', (sq, sq), color='#EEEEEE'))
    collage = Image.new('RGB', (sq*2, sq*2), 'white')
    positions = [(0, 0), (sq, 0), (0, sq), (sq, sq)]
    draw = ImageDraw.Draw(collage)
    for i, img in enumerate(images):
        collage.paste(img, positions[i])
        cx, cy = positions[i][0] + 20, positions[i][1] + 20
        draw.ellipse((cx, cy, cx+150, cy+150), fill="#FFD700", outline="black", width=6)
        draw.text((cx + 55, cy + 30), str(i+1), fill="black")
    output = io.BytesIO()
    collage.save(output, format='JPEG')
    output.seek(0)
    return output

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        query = message.text.strip()
        if not query.lower().startswith("חפש לי"):
            bot.reply_to(message, "ברוכים הבאים! כתבו 'חפש לי' ואת שם המוצר.")
            return
            
        search_query = query[7:].strip()
        loading = bot.send_message(message.chat.id, f"🔎 מחפש עבורכם דילים ל-'{search_query}'...")
        products = search_aliexpress(search_query)
        
        if not products:
            bot.edit_message_text("לא נמצאו תוצאות.", message.chat.id, loading.message_id)
            return

        img_urls = [p['image'] for p in products]
        collage = create_collage(img_urls)
        bot.delete_message(message.chat.id, loading.message_id)
        bot.send_photo(message.chat.id, collage, caption=f"🎯 תוצאות עבור: {search_query}")

        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = []
        text_msg = "⭐️ <b>דילים נבחרים:</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        for i, p in enumerate(products):
            short_link = get_short_link(p['raw_url'])
            # הוספת הכיתובים "הנחה באתר" ו-"דירוג"
            text_msg += f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
            text_msg += f"🔥 הנחה באתר: <b>{p['discount']}</b>\n"
            text_msg += f"💰 מחיר: <b>{p['price']}₪</b>\n"
            text_msg += f"⭐ דירוג: {p['rating']}/5 | 🛒 רכישות: {p['orders']}\n"
            text_msg += f"🔗 {short_link}\n\n"
            buttons.append(types.InlineKeyboardButton(text=f"🎁 לקנייה {i+1}", url=short_link))
        
        text_msg += "▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n🤖 <i>DrDeals</i>"
        markup.add(*buttons)
        bot.send_message(message.chat.id, text_msg, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except: pass

bot.infinity_polling()
