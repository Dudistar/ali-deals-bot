# ===============================
# DrDeals Premium – Final Stable
# ===============================

import telebot
import requests
import time
import os
import io
import hashlib
import logging
import json
import random
from telebot import types
from PIL import Image, ImageDraw
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from deep_translator import GoogleTranslator

# ==========================================
# ⚙️ הגדרות מערכת
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
ADMIN_ID = 173837076

logging.basicConfig(level=logging.INFO)

bot = telebot.TeleBot(BOT_TOKEN)

session = requests.Session()
retry = Retry(connect=3, backoff_factor=1, status_forcelist=[500,502,503,504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('https://', adapter)

# ==========================================
# 🔒 מיפוי קטגוריות (הגנה ממברגים!)
# ==========================================
CATEGORY_MAP = {
    'coat': '200001901', 'jacket': '200001901', 'מעיל': '200001901',
    'drone': '200002649', 'רחפן': '200002649',
    'watch': '200000095', 'שעון': '200000095',
    'headphones': '63705', 'earphones': '63705', 'אוזניות': '63705',
    'phone': '2000023', 'smartphone': '2000023', 'טלפון': '2000023',
    'dress': '200003482', 'שמלה': '200003482',
    'shoes': '322', 'נעליים': '322'
}

def get_category_id(user_query):
    for key, cat_id in CATEGORY_MAP.items():
        if key in user_query.lower():
            return cat_id
    return None

# ==========================================
# 🔐 חתימה
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

# ==========================================
# 🧠 תרגום חכם
# ==========================================
def smart_translate(text):
    try:
        return GoogleTranslator(source='auto', target='en').translate(text)
    except:
        return text

# ==========================================
# 🎣 AliExpress Fetch
# ==========================================
def get_ali_products(query, cat_id=None):
    params = {
        "app_key": APP_KEY,
        "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "format": "json",
        "sign_method": "md5",
        "v": "2.0",
        "partner_id": "top-autopilot",
        "keywords": query,
        "target_currency": "ILS",
        "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC",
        "page_size": "50"
    }
    
    # שימוש במיפוי קטגוריות אם קיים
    if cat_id:
        params["category_ids"] = cat_id

    params["sign"] = generate_sign(params)

    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        products = data["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
        return products if isinstance(products, list) else [products]
    except Exception as e:
        logging.error(e)
        return []

# ==========================================
# 🧹 סינון חכם (מתוקן!)
# ==========================================
BAD_WORDS = [
    "case","cover","holder","mount","adapter",
    "cable","film","strap","sticker","spare", "part"
]

def soft_filter(products, query_en):
    # לוקחים את כל מילות החיפוש (למעט מילות קישור קצרות)
    query_parts = [w.lower() for w in query_en.split() if len(w) > 2]
    clean = []

    for p in products:
        title = p.get("product_title","").lower()
        
        # 1. סינון מילים אסורות (רק אם המשתמש לא ביקש אותן במפורש)
        if any(b in title for b in BAD_WORDS) and not any(b in query_en.lower() for b in BAD_WORDS):
            continue
            
        # 2. בדיקה שלפחות מילה אחת מהותית מהחיפוש קיימת בכותרת
        if query_parts:
            if not any(part in title for part in query_parts):
                continue
                
        clean.append(p)

    return clean

# ==========================================
# 🔗 קיצור לינק
# ==========================================
def get_short_link(url):
    if not url: return None
    clean = url.split("?")[0]
    params = {
        "app_key": APP_KEY, "method": "aliexpress.affiliate.link.generate",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "format": "json",
        "sign_method": "md5", "v": "2.0", "partner_id": "top-autopilot",
        "promotion_link_type": "0", "source_values": clean, "tracking_id": TRACKING_ID
    }
    params["sign"] = generate_sign(params)
    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=5).json()
        link = r["aliexpress_affiliate_link_generate_response"]["resp_result"]["result"]["promotion_links"]["promotion_link"][0]
        return link.get("promotion_short_link") or link.get("promotion_link")
    except: return clean

# ==========================================
# 🖼️ קולאז'
# ==========================================
def create_collage(urls):
    imgs = []
    for u in urls[:3]:
        try:
            img = Image.open(io.BytesIO(session.get(u, timeout=5).content)).resize((500,500))
        except: img = Image.new("RGB",(500,500),"white")
        imgs.append(img)
    while len(imgs)<3: imgs.append(Image.new("RGB",(500,500),"white"))
    
    canvas = Image.new("RGB",(1000,1000),"white")
    canvas.paste(imgs[0].resize((1000,500)),(0,0))
    canvas.paste(imgs[1],(0,500))
    canvas.paste(imgs[2],(500,500))
    
    draw = ImageDraw.Draw(canvas)
    for i,(x,y) in enumerate([(30,30),(30,530),(530,530)]):
        draw.ellipse((x,y,x+70,y+70),fill="#FFD700",outline="black",width=3)
        draw.text((x+25,y+15),str(i+1),fill="black")
        
    out = io.BytesIO()
    canvas.save(out,"JPEG",quality=85)
    out.seek(0)
    return out

# ==========================================
# 🚀 בוט
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    if not m.text.startswith("חפש לי"): return

    query = m.text.replace("חפש לי","").strip()
    bot.send_chat_action(m.chat.id,"typing")
    bot.reply_to(m, f"🔎 מחפש: {query}...")

    # 1. תרגום
    q_en = smart_translate(query)
    
    # 2. זיהוי קטגוריה (ההגנה החשובה)
    cat_id = get_category_id(query)
    
    # 3. משיכה
    products = get_ali_products(q_en, cat_id)
    
    # 4. סינון משופר
    products = soft_filter(products, q_en)

    if not products:
        bot.send_message(m.chat.id,"❌ לא נמצאו תוצאות מדויקות.")
        return

    final = products[:3]
    images, text = [], f"🏆 <b>הבחירות עבור: {query}</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i,p in enumerate(final):
        # תרגום כותרת לעברית לתצוגה
        try:
            title = GoogleTranslator(source='auto',target='iw').translate(p["product_title"])
        except:
            title = p["product_title"]
            
        price = p.get("target_sale_price","?")
        link = get_short_link(p.get("product_detail_url"))
        images.append(p.get("product_main_image_url"))

        text += f"{i+1}. {title[:55]}...\n💰 {price}₪\n🔗 {link}\n\n"
        kb.add(types.InlineKeyboardButton(f"🛒 מוצר {i+1}",url=link))

    if images:
        try:
            bot.send_photo(m.chat.id, create_collage(images), caption=text, parse_mode="HTML", reply_markup=kb)
        except:
             bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)

bot.infinity_polling()
