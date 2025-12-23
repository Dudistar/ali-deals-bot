import telebot
import requests
import io
import hashlib
import time
import html
from telebot import types
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator

# ================== פרטים אישיים ==================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

bot = telebot.TeleBot(BOT_TOKEN)

# ================== כלי עזר ==================
def generate_sign(params):
    s = APP_SECRET + ''.join([f"{k}{v}" for k, v in sorted(params.items())]) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def normalize_rating(v):
    try:
        x = float(str(v).replace('%', ''))
        return round(x / 20, 1) if x > 5 else round(x, 1)
    except:
        return 4.5

# ================== קיצור קישורים ==================
def get_short_link(url):
    try:
        time.sleep(2.5)  # השהיה משופרת ל-s.click
        params = {
            'app_key': APP_KEY,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5',
            'method': 'aliexpress.affiliate.link.generate',
            'partner_id': 'top-autopilot',
            'format': 'json',
            'v': '2.0',
            'promotion_link_type': '0',
            'source_values': url.split('?')[0],
            'tracking_id': TRACKING_ID
        }
        params['sign'] = generate_sign(params)
        r = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=6).json()
        pl = r.get('aliexpress_affiliate_link_generate_response', {}) \
            .get('resp_result', {}).get('result', {}) \
            .get('promotion_links', {}).get('promotion_link', [])
        if pl and pl[0].get('promotion_short_link'):
            return pl[0]['promotion_short_link']
    except:
        pass
    return url

# ================== חיפוש חכם + זיהוי כוונה ==================
def search_aliexpress(keyword):
    try:
        en = GoogleTranslator(source='auto', target='en').translate(keyword).lower()
        words = en.split()

        # זיהוי כוונה – מצלמת רכב = DASHCAM קדמית
        is_dashcam = any(k in en for k in [
            'dash', 'dashcam', 'driving recorder', 'car camera'
        ])

        params = {
            'app_key': APP_KEY,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5',
            'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot',
            'format': 'json',
            'v': '2.0',
            'keywords': en,
            'target_currency': 'ILS',
            'ship_to_country': 'IL',
            'sort': 'LAST_VOLUME_DESC',
            'page_size': '50'
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10).json()

        products = resp.get('aliexpress_affiliate_product_query_response', {}) \
            .get('resp_result', {}).get('result', {}) \
            .get('products', {}).get('product', [])

        if isinstance(products, dict):
            products = [products]

        banned = ['rear', 'reverse', 'backup', 'parking', 'screen',
                  'monitor', 'carplay', 'endoscope']
        required_dash = ['dash', 'recorder', 'driving', 'front']

        good, fallback = [], []

        for p in products:
            title = p.get('product_title', '').lower()

            if is_dashcam:
                if any(b in title for b in banned):
                    continue
                if not any(r in title for r in required_dash):
                    fallback.append(p)
                    continue

            rating = normalize_rating(p.get('evaluate_rate'))
            if rating < 4.2:
                continue

            good.append(p)

        final = good[:4]
        if len(final) < 4:
            final += fallback[:4 - len(final)]

        results = []
        for p in final:
            try:
                title_he = GoogleTranslator(source='auto', target='iw').translate(p['product_title'])
            except:
                title_he = p['product_title']

            results.append({
                'title': title_he[:60],
                'price': p.get('target_sale_price', 'N/A'),
                'image': p.get('product_main_image_url'),
                'url': p.get('product_detail_url', ''),
                'rating': normalize_rating(p.get('evaluate_rate')),
                'orders': p.get('lastest_volume', '')
            })

        return results
    except:
        return None

# ================== קולאז' – WhatsApp Style (מספרים ענקיים באמת) ==================
def create_collage(image_urls):
    imgs = []
    for url in image_urls:
        try:
            r = requests.get(url, timeout=10)
            imgs.append(Image.open(io.BytesIO(r.content)).convert('RGB').resize((500, 500)))
        except:
            imgs.append(Image.new('RGB', (500, 500), '#EEE'))

    while len(imgs) < 4:
        imgs.append(Image.new('RGB', (500, 500), '#EEE'))

    canvas = Image.new('RGB', (1000, 1000), 'white')
    draw = ImageDraw.Draw(canvas)

    pos = [(0, 0), (500, 0), (0, 500), (500, 500)]
    circle_size = 120
    green = "#25D366"

    for i, img in enumerate(imgs):
        canvas.paste(img, pos[i])
        cx, cy = pos[i][0] + 20, pos[i][1] + 20

        # עיגול
        draw.ellipse(
            (cx, cy, cx + circle_size, cy + circle_size),
            fill=green,
            outline="white",
            width=6
        )

        # --- מספר בשכבה נפרדת (טריק מקצועי) ---
        num = str(i + 1)
        num_img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        num_draw = ImageDraw.Draw(num_img)

        big_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            380
        )

        bbox = num_draw.textbbox((0, 0), num, font=big_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        num_draw.text(
            ((400 - tw) // 2, (400 - th) // 2),
            num,
            font=big_font,
            fill="white"
        )

        # הקטנה מדויקת והדבקה
        num_img = num_img.resize((circle_size, circle_size), Image.LANCZOS)
        canvas.paste(num_img, (cx, cy), num_img)

    out = io.BytesIO()
    canvas.save(out, 'JPEG', quality=95)
    out.seek(0)
    return out

# ================== טלגרם ==================
@bot.message_handler(func=lambda m: True)
def handle(m):
    if not m.text or not m.text.lower().startswith("חפש לי"):
        bot.reply_to(m, "כתוב: חפש לי <שם מוצר>")
        return

    q = m.text[7:].strip()
    msg = bot.send_message(m.chat.id, f"🔎 מחפש את הדילים הכי שווים ל־{q}…")

    items = search_aliexpress(q)
    if not items:
        bot.edit_message_text("לא מצאתי תוצאות רלוונטיות כרגע.", m.chat.id, msg.message_id)
        return

    collage = create_collage([i['image'] for i in items])
    bot.delete_message(m.chat.id, msg.message_id)
    bot.send_photo(m.chat.id, collage, caption=f"🎯 תוצאות מומלצות ל־{q}")

    text = "⭐️ <b>הבחירות הטובות ביותר:</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(items):
        link = get_short_link(p['url'])
        text += (
            f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
            f"💰 מחיר: <b>{p['price']}₪</b>\n"
            f"⭐ דירוג: {p['rating']} | 🛒 {p['orders']} רכישות\n"
            f"🔗 {link}\n\n"
        )
        kb.add(types.InlineKeyboardButton(f"🟢 קנייה {i+1}", url=link))

    bot.send_message(
        m.chat.id,
        text,
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True
    )

bot.infinity_polling()
