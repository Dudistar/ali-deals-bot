# ==========================================
# DrDeals Premium – FINAL PROFESSIONAL EDITION
# ==========================================
import telebot
import requests
import time
import hashlib
import logging
import io
import sys
import os
import json
import html
from telebot import types
from PIL import Image, ImageDraw, ImageFont
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from deep_translator import GoogleTranslator
import google.generativeai as genai

# ==========================================
# 👮 הגדרות
# ==========================================
ADMIN_ID = 173837076
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

# ==========================================
# 🔑 AI
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
HAS_AI = False

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-pro")
        HAS_AI = True
        print("✅ AI connected")
    except Exception as e:
        print("❌ AI failed:", e)

# ==========================================
# ⚙️ מערכת
# ==========================================
logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)])
bot = telebot.TeleBot(BOT_TOKEN)

session = requests.Session()
adapter = HTTPAdapter(max_retries=Retry(connect=3, backoff_factor=1))
session.mount("https://", adapter)

# ==========================================
# 🛡️ ניקוי טקסט
# ==========================================
def safe(text):
    return html.escape(str(text)) if text else ""

# ==========================================
# 🎨 קולאז'
# ==========================================
def create_collage(images):
    canvas = Image.new("RGB", (1000, 1000), "white")
    draw = ImageDraw.Draw(canvas)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90)
    except:
        font = ImageFont.load_default()

    positions = [(0,0),(500,0),(0,500),(500,500)]

    for i, url in enumerate(images[:4]):
        try:
            img = Image.open(io.BytesIO(session.get(url, timeout=5).content)).resize((500,500))
        except:
            img = Image.new("RGB",(500,500),"#eee")
        canvas.paste(img, positions[i])

        x,y = positions[i]
        draw.ellipse([x+20,y+20,x+140,y+140], fill="#FFD700", outline="black", width=5)
        draw.text((x+55,y+35), str(i+1), fill="black", font=font)

    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=95)
    out.seek(0)
    return out

# ==========================================
# 🧠 AI תיאור בלבד (לא סינון!)
# ==========================================
def ai_describe(query, title):
    if not HAS_AI:
        return title[:35], "מוצר פופולרי בקטגוריה"

    prompt = f"""
    User searched: "{query}"
    Product: "{title}"

    Rewrite into Hebrew:
    1. Short title (max 5 words)
    2. Short benefit (max 6 words)

    Return JSON:
    {{"title":"...","desc":"..."}}
    """

    try:
        r = model.generate_content(prompt)
        txt = r.text.replace("```json","").replace("```","").strip()
        data = json.loads(txt)
        return data.get("title", title[:30]), data.get("desc","מוצר מומלץ")
    except:
        return title[:30], "מוצר מומלץ"

# ==========================================
# 🔧 AliExpress
# ==========================================
def sign(params):
    s = APP_SECRET + "".join(f"{k}{v}" for k,v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def ali_search(q):
    params = {
        "app_key": APP_KEY,
        "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "format": "json",
        "sign_method": "md5",
        "v": "2.0",
        "partner_id": "top-autopilot",
        "keywords": q,
        "target_currency": "ILS",
        "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC",
        "page_size": "40"
    }
    params["sign"] = sign(params)

    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=12).json()
        p = r["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
        return p if isinstance(p,list) else [p]
    except:
        return []

def short_link(url):
    if not url: return ""
    clean = url.split("?")[0]
    params = {
        "app_key": APP_KEY,
        "method": "aliexpress.affiliate.link.generate",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "format": "json",
        "sign_method": "md5",
        "v": "2.0",
        "partner_id": "top-autopilot",
        "promotion_link_type": "0",
        "source_values": clean,
        "tracking_id": TRACKING_ID
    }
    params["sign"] = sign(params)

    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=6).json()
        link = r["aliexpress_affiliate_link_generate_response"]["resp_result"]["result"]["promotion_links"]["promotion_link"][0]
        return link.get("promotion_short_link") or link.get("promotion_link")
    except:
        return clean

# ==========================================
# 🚀 הבוט
# ==========================================
@bot.message_handler(func=lambda m: m.text and m.text.startswith("חפש לי"))
def handle(m):
    query_he = m.text.replace("חפש לי","").strip()

    # 🕵️ דיווח מנהל
    try:
        bot.send_message(
            ADMIN_ID,
            f"🔎 חיפוש חדש\n👤 {safe(m.from_user.first_name)} (@{safe(m.from_user.username)})\n📦 {safe(query_he)}"
        )
    except:
        pass

    status = bot.reply_to(m, f"🕵️‍♂️ מחפש ביסודיות:\n<b>{safe(query_he)}</b>", parse_mode="HTML")

    time.sleep(1.5)

    try:
        query_en = GoogleTranslator(source="auto", target="en").translate(query_he)
    except:
        query_en = query_he

    time.sleep(1.5)

    products = ali_search(query_en)
    if not products:
        bot.edit_message_text("❌ לא נמצאו תוצאות.", m.chat.id, status.message_id)
        return

    final = []
    for p in products:
        if len(final) == 4: break
        if not p.get("product_main_image_url"): continue
        title, desc = ai_describe(query_he, p["product_title"])
        p["h_title"] = title
        p["h_desc"] = desc
        final.append(p)

    collage = create_collage([p["product_main_image_url"] for p in final])

    text = f"🏆 <b>הבחירות עבור:</b> {safe(query_he)}\n\n"
    kb = types.InlineKeyboardMarkup()

    for i,p in enumerate(final):
        link = short_link(p.get("product_detail_url"))
        price = p.get("target_sale_price","?")
        rating = p.get("evaluate_rate","?")
        orders = p.get("last_volume","?")

        text += f"<b>{i+1}. {safe(p['h_title'])}</b>\n"
        text += f"📝 {safe(p['h_desc'])}\n"
        text += f"💰 {price}₪ | ⭐ {rating} | 🛒 {orders}\n"
        text += f"🔗 {link}\n\n"

        kb.add(types.InlineKeyboardButton(f"🛒 לקנייה {i+1}", url=link))

    bot.delete_message(m.chat.id, status.message_id)
    bot.send_photo(m.chat.id, collage, caption=text, parse_mode="HTML", reply_markup=kb)

print("🚀 DrDeals FINAL running")
bot.infinity_polling(timeout=30, long_polling_timeout=15)
