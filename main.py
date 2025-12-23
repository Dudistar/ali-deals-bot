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
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

def normalize_rating(val):
    try:
        v = float(str(val).replace('%', ''))
        return round(v / 20, 1) if v > 5 else round(v, 1)
    except:
        return 4.5

# ================== קיצור קישורים ==================
def get_short_link(raw_url):
    try:
        time.sleep(3)  # השהיה ארוכה יותר
        params = {
            'app_key': APP_KEY,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5',
            'method': 'aliexpress.affiliate.link.generate',
            'partner_id': 'top-autopilot',
            'format': 'json',
            'v': '2.0',
            'promotion_link_type': '0',
            'source_values': raw_url.split('?')[0],
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
    return raw_url

# ================== חיפוש חכם עם זיהוי כוונה ==================
def search_aliexpress(keyword):
    try:
        en_kw = GoogleTranslator(source='auto', target='en').translate(keyword).lower()
        kw_words = en_kw.split()

        # --- זיהוי כוונה ---
        is_dashcam = any(k in en_kw for k in [
            "dash", "dashcam", "car camera", "driving recorder", "vehicle camera"
        ])

        params = {
            'app_key': APP_KEY,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5',
            'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot',
            'format': 'json',
            'v': '2.0',
            'keywords': en_kw,
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

        banned_dashcam = [
            'rear', 'reverse', 'backup', 'parking', 'endoscope',
            'carplay', 'monitor', 'screen', 'display'
        ]

        scored = []

        for p in products:
            title = p.get('product_title', '')
            title_l = title.lower()

            # פסילה מוחלטת
            if is_dashcam and any(b in title_l for b in banned_dashcam):
                continue

            score = 0

            for w in kw_words:
                if w in title_l:
                    score += 3

            rating = normalize_rating(p.get('evaluate_rate'))
            if rating < 4.2:
                continue
            elif rating >= 4.6:
                score += 3

            orders = int(p.get('lastest_volume', 0)) if str(p.get('lastest_volume', '')).isdigit() else 0
            score += min(orders / 1000, 5)

            scored.append((score, p, rating, orders))

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[:4]

        results = []
        for _, p, rating, orders in best:
            try:
                title_he = GoogleTranslator(source='auto', target='iw').translate(p['product_title'])
            except:
                title_he = p['product_title']

            results.append({
                "title": title_he[:60],
                "price": p.get('target_sale_price', 'N/A'),
                "image": p.get('product_main_image_url'),
                "url": p.get('product_detail_url', ''),
                "rating": rating,
                "orders": orders
            })

        return results
    except:
        return None

# ================== קולאז' – WhatsApp Style ==================
def create_collage(image_urls):
    imgs = []
    for url in image_urls:
        try:
            r = requests.get(url, timeout=10)
            imgs.append(Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500)))
        except:
            imgs.append(Image.new('RGB', (500,500), '#EEE'))

    while len(imgs) < 4:
        imgs.append(Image.new('RGB', (500,500), '#EEE'))

    canvas = Image.new('RGB', (1000,1000), 'white')
    draw = ImageDraw.Draw(canvas)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 300)
    except:
        font = ImageFont.load_default()

    pos = [(0,0),(500,0),(0,500),(500,500)]
    circle_size = 120
    green = "#25D366"

    for i, img in enumerate(imgs):
        canvas.paste(img, pos[i])
        cx, cy = pos[i][0] + 20, pos[i][1] + 20

        draw.ellipse(
            (cx, cy, cx + circle_size, cy + circle_size),
            fill=green,
            outline="white",
            width=6
        )

        num = str(i + 1)
        bbox = draw.textbbox((0, 0), num, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = cx + (circle_size - tw) // 2
        ty = cy + (circle_size - th) // 2 - 20

        for dx, dy in [(-2,0),(2,0),(0,-2),(0,2)]:
            draw.text((tx+dx, ty+dy), num, fill="black", font=font)

        draw.text((tx, ty), num, fill="white", font=font)

    out = io.BytesIO()
    canvas.save(out, format='JPEG', quality=95)
    out.seek(0)
    return out

# ================== טלגרם ==================
@bot.message_handler(func=lambda m: True)
def handle_message(m):
    q = m.text.strip()
    if not q.lower().startswith("חפש לי"):
        bot.reply_to(m, "כתוב: חפש לי <שם מוצר>")
        return

    query = q[7:].strip()
    msg = bot.send_message(m.chat.id, f"🔎 מחפש את הדילים הכי שווים ל־{query}…")

    products = search_aliexpress(query)
    if not products:
        bot.edit_message_text("לא מצאתי תוצאות רלוונטיות כרגע.", m.chat.id, msg.message_id)
        return

    collage = create_collage([p['image'] for p in products])
    bot.delete_message(m.chat.id, msg.message_id)
    bot.send_photo(m.chat.id, collage, caption=f"🎯 תוצאות מומלצות ל־{query}")

    text = "⭐️ <b>הבחירות הטובות ביותר:</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i,p in enumerate(products):
        link = get_short_link(p['url'])
        text += (
            f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
            f"💰 מחיר: <b>{p['price']}₪</b>\n"
            f"⭐ דירוג: {p['rating']} | 🛒 {p['orders']} רכישות\n"
            f"🔗 {link}\n\n"
        )
        kb.add(types.InlineKeyboardButton(f"🟢 קנייה {i+1}", url=link))

    text += "<i>DrDeals</i>"
    bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)

bot.infinity_polling()
