import telebot
import requests
import io
import hashlib
import time
import html
from telebot import types
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator

# --- הפרטים שלך ---
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
        time.sleep(0.3) 
        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.link.generate',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'promotion_link_type': '0', 'source_values': raw_url.split('?')[0], 'tracking_id': TRACKING_ID
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=5).json()
        res = resp.get('aliexpress_affiliate_link_generate_response', {}).get('resp_result', {}).get('result', {}).get('promotion_links', {}).get('promotion_link', [])
        if res: return res[0].get('promotion_short_link') or res[0].get('promotion_link')
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
            'sort': 'LAST_VOLUME_DESC', 'page_size': '40'
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10).json()
        products_raw = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(products_raw, dict): products_raw = [products_raw]

        bad_words = ['case', 'cover', 'adapter', 'cable', 'mount']
        results, backup = [], []
        for p in products_raw:
            title = p.get('product_title', '').lower()
            is_bad = any(bw in title for bw in bad_words) and not any(bw in en_keyword for bw in bad_words)
            if not is_bad: results.append(p)
            else: backup.append(p)

        final_list = (results + backup)[:4]
        output = []
        for p in final_list:
            try: title_he = GoogleTranslator(source='auto', target='iw').translate(p['product_title'])
            except: title_he = p['product_title']
            
            try:
                val = float(str(p.get('evaluate_rate', '95')).replace('%', ''))
                rate = round(val / 20, 1) if val > 5 else round(val, 1)
            except: rate = 4.8

            output.append({
                "title": title_he[:50] + "...", "price": p.get('target_sale_price', 'N/A'),
                "image": p.get('product_main_image_url'), "raw_url": p.get('product_detail_url', ''),
                "rating": rate, "orders": p.get('lastest_volume', "Top"), "discount": p.get('discount', '0%')
            })
        return output
    except: return None

def draw_number(draw, cx, cy, num):
    """מצייר מספר בצורה גרפית בתוך עיגול"""
    # עיגול צהוב
    draw.ellipse((cx, cy, cx+160, cy+160), fill="#FFD700", outline="black", width=10)
    
    # קורדינטות בסיס לציור בתוך העיגול
    base_x = cx + 40
    base_y = cy + 20
    thickness = 20
    
    # ציור גרפי של ספרות 1-4
    if num == 1:
        draw.rectangle([base_x+30, base_y, base_x+30+thickness, base_y+120], fill="black")
    elif num == 2:
        draw.rectangle([base_x, base_y, base_x+80, base_y+thickness], fill="black")
        draw.rectangle([base_x+80-thickness, base_y, base_x+80, base_y+60], fill="black")
        draw.rectangle([base_x, base_y+60-thickness, base_x+80, base_y+60], fill="black")
        draw.rectangle([base_x, base_y+60, base_x+thickness, base_y+120], fill="black")
        draw.rectangle([base_x, base_y+120-thickness, base_x+80, base_y+120], fill="black")
    elif num == 3:
        draw.rectangle([base_x, base_y, base_x+80, base_y+thickness], fill="black")
        draw.rectangle([base_x+80-thickness, base_y, base_x+80, base_y+120], fill="black")
        draw.rectangle([base_x, base_y+60-thickness, base_x+80, base_y+60], fill="black")
        draw.rectangle([base_x, base_y+120-thickness, base_x+80, base_y+120], fill="black")
    elif num == 4:
        draw.rectangle([base_x, base_y, base_x+thickness, base_y+60], fill="black")
        draw.rectangle([base_x, base_y+60-thickness, base_x+80, base_y+60], fill="black")
        draw.rectangle([base_x+80-thickness, base_y, base_x+80, base_y+120], fill="black")

def create_collage(image_urls):
    images = []
    for url in image_urls:
        try:
            r = requests.get(url, timeout=7)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
            images.append(img)
        except: images.append(Image.new('RGB', (500,500), color='#EEEEEE'))
    while len(images) < 4: images.append(Image.new('RGB', (500,500), color='#EEEEEE'))
    
    collage = Image.new('RGB', (1000, 1000), 'white')
    positions = [(0,0), (500,0), (0,500), (500,500)]
    draw = ImageDraw.Draw(collage)

    for i, img in enumerate(images):
        collage.paste(img, positions[i])
        cx, cy = positions[i][0]+30, positions[i][1]+30
        # שימוש בפונקציית הציור הגרפית
        draw_number(draw, cx, cy, i+1)

    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=85)
    output.seek(0)
    return output

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        query = message.text.strip()
        if not query.lower().startswith("חפש לי"):
            bot.reply_to(message, "שלום! כתבו 'חפש לי' ואת שם המוצר.")
            return

        search_query = query[7:].strip()
        loading = bot.send_message(message.chat.id, f"🔎 מחפש עבורכם דילים ל-'{search_query}'...")
        products = search_aliexpress(search_query)

        if not products:
            bot.edit_message_text("לא נמצאו תוצאות כרגע.", message.chat.id, loading.message_id)
            return

        collage = create_collage([p['image'] for p in products])
        bot.delete_message(message.chat.id, loading.message_id)
        bot.send_photo(message.chat.id, collage, caption=f"🎯 תוצאות עבור: <b>{search_query}</b>", parse_mode="HTML")

        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons, text_msg = [], "⭐️ <b>דילים נבחרים:</b>\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        for i, p in enumerate(products):
            short_url = get_short_link(p['raw_url'])
            text_msg += f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
            text_msg += f"🔥 הנחה באתר: <b>-{p['discount']}</b>\n💰 מחיר: <b>{p['price']}₪</b>\n"
            text_msg += f"⭐ דירוג: {p['rating']}/5 | 🛒 רכישות: {p['orders']}\n🔗 {short_url}\n\n"
            buttons.append(types.InlineKeyboardButton(text=f"🎁 לקנייה {i+1}", url=short_url))

        text_msg += "▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n🤖 <i>צייד הדילים - DrDeals</i>"
        markup.add(*buttons)
        bot.send_message(message.chat.id, text_msg, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except: pass

bot.infinity_polling()
