import telebot
import requests
import io
import hashlib
import time
import html
from telebot import types
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator

# --- הפרטים המדויקים שלך ---
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

bot = telebot.TeleBot(BOT_TOKEN)
user_sessions = {}

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

def search_aliexpress(keyword, offset=0):
    try:
        en_keyword = GoogleTranslator(source='auto', target='en').translate(keyword).lower()
        
        # סינון מחיר דינמי: רק למוצרים טכנולוגיים
        min_price = "0"
        high_tech = ['camera', 'dash', 'phone', 'tablet', 'watch', 'monitor', 'projector', 'mictoscope']
        if any(word in en_keyword for word in high_tech):
            min_price = "35" 

        params = {
            'app_key': APP_KEY, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'sign_method': 'md5', 'method': 'aliexpress.affiliate.product.query',
            'partner_id': 'top-autopilot', 'format': 'json', 'v': '2.0',
            'keywords': en_keyword, 'target_currency': 'ILS', 'ship_to_country': 'IL',
            'min_sale_price': min_price,
            'sort': 'SALE_PRICE_DESC', 
            'page_size': '50'
        }
        params['sign'] = generate_sign(params)
        resp = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10).json()
        products_raw = resp.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {}).get('result', {}).get('products', {}).get('product', [])
        if isinstance(products_raw, dict): products_raw = [products_raw]

        bad_words = ['case', 'cover', 'adapter', 'cable', 'mount', 'holder', 'part']
        results, backup = [], []
        for p in products_raw:
            title = p.get('product_title', '').lower()
            is_bad = any(bw in title for bw in bad_words) and not any(bw in en_keyword for bw in bad_words)
            if not is_bad: results.append(p)
            else: backup.append(p)

        all_sorted = results + backup
        final_list = all_sorted[offset : offset + 4]
        if not final_list: final_list = all_sorted[:4]

        output = []
        for p in final_list:
            try: title_he = GoogleTranslator(source='auto', target='iw').translate(p['product_title'])
            except: title_he = p['product_title']
            
            # הדגשת פיצ'רים והארכת טקסט
            for f in ['4K', 'UHD', 'GPS', 'Sony', 'WiFi']:
                if f.lower() in p['product_title'].lower():
                    title_he = f"💎 {f} | " + title_he
            
            title_he = title_he[:85] + "..." if len(title_he) > 85 else title_he

            output.append({
                "title": title_he, "price": p.get('target_sale_price', 'N/A'),
                "image": p.get('product_main_image_url'), "raw_url": p.get('product_detail_url', ''),
                "rating": round(float(str(p.get('evaluate_rate', '95')).replace('%',''))/20, 1), 
                "orders": p.get('lastest_volume', "1K+"), "coupon": p.get('coupon_code')
            })
        return output
    except: return None

def draw_minimal_number(draw, cx, cy, num):
    """ציור מספרים קטנים ואלגנטיים בפינה"""
    # עיגול קטן ועדין (רדיוס 35)
    draw.ellipse((cx, cy, cx+35, cy+35), fill="#FFD700", outline="black", width=2)
    base_x, base_y, thick = cx + 12, cy + 7, 5
    # ציור סכמטי פשוט ודק
    if num == 1: draw.rectangle([base_x+3, base_y, base_x+7, base_y+20], fill="black")
    elif num == 2:
        for r in [[0,0,12,3],[10,0,12,10],[0,8,12,11],[0,10,3,20],[0,17,12,20]]:
            draw.rectangle([base_x+r[0], base_y+r[1], base_x+r[2], base_y+r[3]], fill="black")
    elif num == 3:
        for r in [[0,0,12,3],[10,0,12,20],[0,8,12,11],[0,17,12,20]]:
            draw.rectangle([base_x+r[0], base_y+r[1], base_x+r[2], base_y+r[3]], fill="black")
    elif num == 4:
        for r in [[0,0,3,10],[0,8,12,11],[10,0,12,20]]:
            draw.rectangle([base_x+r[0], base_y+r[1], base_x+r[2], base_y+r[3]], fill="black")

def create_collage(image_urls):
    images = []
    for url in image_urls:
        try:
            r = requests.get(url, timeout=7)
            img = Image.open(io.BytesIO(r.content)).convert('RGB').resize((500,500))
            images.append(img)
        except: images.append(Image.new('RGB', (500,500), color='#EEEEEE'))
    
    collage = Image.new('RGB', (1000, 1000), 'white')
    positions = [(0,0), (500,0), (0,500), (500,500)]
    draw = ImageDraw.Draw(collage)
    for i, img in enumerate(images):
        collage.paste(img, positions[i])
        # הזזה לפינה (15 פיקסלים מהקצה)
        draw_minimal_number(draw, positions[i][0]+15, positions[i][1]+15, i+1)
    
    output = io.BytesIO()
    collage.save(output, format='JPEG', quality=90)
    output.seek(0)
    return output

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        query = message.text.strip()
        if not query.lower().startswith("חפש לי"): return
        search_query = query[7:].strip().lower()
        chat_id = message.chat.id
        current_time = time.time()
        
        offset = 0
        if chat_id in user_sessions:
            session = user_sessions[chat_id]
            if session['query'] == search_query and (current_time - session['time']) < 120:
                offset = session['offset'] + 4
        
        user_sessions[chat_id] = {'query': search_query, 'time': current_time, 'offset': offset}
        loading = bot.send_message(chat_id, f"🔎 <b>מחפש את הדילים הכי טובים ל-'{search_query}'...</b>", parse_mode="HTML")
        products = search_aliexpress(search_query, offset=offset)
        
        if not products:
            bot.edit_message_text("מצטער, לא מצאתי משהו ששווה לשלוח.", chat_id, loading.message_id)
            return

        collage = create_collage([p['image'] for p in products])
        bot.delete_message(chat_id, loading.message_id)
        bot.send_photo(chat_id, collage, caption=f"🎯 <b>נמצאו 4 {search_query} מומלצים:</b>", parse_mode="HTML")

        text_msg = "💎 <b>נבחרת הדילים:</b>\n" + "▬" * 15 + "\n\n"
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = []
        for i, p in enumerate(products):
            short_url = get_short_link(p['raw_url'])
            text_msg += f"{i+1}. 🏆 <b>{html.escape(p['title'])}</b>\n"
            text_msg += f"💰 מחיר: <b>{p['price']}₪</b> | ⭐ דירוג: <b>{p['rating']}</b>\n"
            if p['coupon']: text_msg += f"🎫 קופון: <code>{p['coupon']}</code>\n"
            text_msg += f"🔗 {short_url}\n\n"
            buttons.append(types.InlineKeyboardButton(text=f"🎁 לקנייה {i+1}", url=short_url))

        text_msg += "▬" * 15 + "\n🤖 <b>DrDeals</b>"
        markup.add(*buttons)
        bot.send_message(chat_id, text_msg, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except: pass

bot.infinity_polling()
