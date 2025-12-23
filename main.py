import telebot
import requests
import io
import hashlib
import time
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
        time.sleep(1.5)  # השהייה למניעת תקיעה
        clean_url = raw_url.split('?')[0]
        params = {
            'app_key': APP_KEY,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5',
            'method': 'aliexpress.affiliate.link.generate',
            'partner_id': 'top-autopilot',
            'format': 'json',
            'v': '2.0',
            'promotion_link_type': '0',
            'source_values': clean_url,
            'tracking_id': TRACKING_ID
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10).json()
        links = resp.get('aliexpress_affiliate_link_generate_response', {}).get('resp_result', {}).get('result', {}).get('promotion_links', {}).get('promotion_link', [])
        if links:
            return links[0].get('promotion_short_link') or links[0].get('promotion_link')
    except:
        pass
    return raw_url

def search_aliexpress(keyword):
    """חיפוש חכם ומסונן"""
    try:
        en_keyword = GoogleTranslator(source='auto', target='en').translate(keyword).lower()
        params = {
            'app_key': APP_KEY,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5',
            'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot',
            'format': 'json',
            'v': '2.0',
            'keywords': en_keyword,
            'target_currency': 'ILS',
            'ship_to_country': 'IL',
            'sort': 'RELEVANCE',
            'page_size': '50'
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
        products_raw = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(products_raw, dict): products_raw = [products_raw]

        bad_words = ['case', 'cover', 'adapter', 'cable', 'mount', 'holder', 'part']
        results = []
        for p in products_raw:
            title = p.get('product_title', '').lower()
            if not any(bw in title for bw in bad_words):
                results.append(p)
            if len(results) >= 10:  # נשמור רק 10 ראשונים
                break

        final_list = results[:4]
        output = []
        for p in final_list:
            try:
                title_he = GoogleTranslator(source='auto', target='iw').translate(p['product_title'])
            except:
                title_he = p['product_title']
            output.append({
                "title": title_he[:80] + "...",
                "price": p.get('target_sale_price', 'N/A'),
                "image": p.get('product_main_image_url'),
                "raw_url": p.get('product_detail_url', ''),
                "rating": round(float(str(p.get('evaluate_rate', '95')).replace('%',''))/20,1) if p.get('evaluate_rate') else 4.8,
                "orders": p.get('lastest_volume', '100+')
            })
        return output
    except:
        return None

def create_collage(image_urls):
    """קולאז’ 2x2 עם מספרים גדולים"""
    images = []
    for url in image_urls:
        try:
            r = requests.get(url, timeout=12)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
            images.append(img)
        except:
            images.append(Image.new('RGB', (500,500), color='#EEEEEE'))

    while len(images) < 4:
        images.append(Image.new('RGB', (500,500), color='#EEEEEE'))

    collage = Image.new('RGB', (1000,1000), 'white')
    positions = [(0,0),(500,0),(0,500),(500,500)]
    draw = ImageDraw.Draw(collage)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 120)
    except:
        font = ImageFont.load_default()

    for i, img in enumerate(images):
        collage.paste(img, positions[i])
        # עיגול קטן יותר
        cx, cy = positions[i][0]+20, positions[i][1]+20
        draw.ellipse((cx, cy, cx+80, cy+80), fill="#FFD700", outline="black", width=5)
        # מספר גדול
        w, h = draw.textsize(str(i+1), font=font)
        draw.text((cx + 40 - w/2, cy + 40 - h/2), str(i+1), fill="black", font=font)

    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        query = message.text.strip()
        if not query.lower().startswith("חפש לי"):
            bot.reply_to(message, "שלום! כתבו 'חפש לי' ואז שם המוצר.")
            return

        search_query = query[7:].strip()
        loading = bot.send_message(message.chat.id, f"💎 מחפש דילים עבור: '{search_query}'...")

        products = search_aliexpress(search_query)
        if not products:
            bot.edit_message_text("מצטער, לא נמצאו תוצאות איכותיות כרגע.", message.chat.id, loading.message_id)
            return

        # הכנת הקישורים מראש
        final_links = [get_short_link(p['raw_url']) for p in products]

        collage = create_collage([p['image'] for p in products])
        bot.delete_message(message.chat.id, loading.message_id)
        bot.send_photo(message.chat.id, collage, caption=f"🎯 <b>דילים מובחרים עבור: {search_query}</b>", parse_mode="HTML")

        text_msg = "⭐️ <b>TOP DEALS:</b>\n" + "▬"*20 + "\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = []

        for i, p in enumerate(products):
            text_msg += f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
            text_msg += f"💰 מחיר: <b>{p['price']}₪</b> | ⭐ דירוג: <b>{p['rating']}</b>\n"
            text_msg += f"🛒 רכישות: <b>{p['orders']}</b>\n"
            text_msg += f"🔗 {final_links[i]}\n\n"
            buttons.append(types.InlineKeyboardButton(text=f"🎁 לקנייה {i+1}", url=final_links[i]))

        text_msg += "▬"*20 + "\n🤖 <i>DrDeals</i>"
        markup.add(*buttons)
        bot.send_message(message.chat.id, text_msg, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)

    except Exception as e:
        print(f"GLOBAL ERROR: {e}")
        bot.send_message(message.chat.id, "אירעה תקלה בעיבוד הנתונים. נסו שוב.")

# --- הפתרון לשגיאת 409 (Conflict) ---
try:
    bot.remove_webhook()
    print("Bot is LIVE - Starting polling...")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
except Exception as e:
    print(f"Polling error: {e}")
