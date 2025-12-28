# ==========================================
# DrDeals Premium – FINAL STABLE EDITION
# ==========================================
import telebot, requests, time, hashlib, io, os, json
from telebot import types
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator

# ================== CONFIG ==================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

bot = telebot.TeleBot(BOT_TOKEN)
session = requests.Session()

# ================== HELPERS ==================
def slow(step=2.5):
    time.sleep(step)

def sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

# ================== CATEGORY LOGIC ==================
CATEGORY_RULES = {
    "drone": ["drone", "quadcopter", "uav"],
    "smart watch": ["smart watch"],
}

def detect_category(en_query):
    for cat, keys in CATEGORY_RULES.items():
        if any(k in en_query for k in keys):
            return cat
    return None

def valid_for_category(title, category):
    title = title.lower()
    if category == "drone":
        return any(k in title for k in ["drone", "quadcopter"])
    if category == "smart watch":
        return "watch" in title and "smart" in title
    return True

# ================== ALI SEARCH ==================
def ali_search(query_en):
    slow(3)
    params = {
        "app_key": APP_KEY,
        "method": "aliexpress.affiliate.product.query",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "format": "json",
        "sign_method": "md5",
        "v": "2.0",
        "partner_id": "top-autopilot",
        "keywords": query_en,
        "target_currency": "ILS",
        "ship_to_country": "IL",
        "sort": "LAST_VOLUME_DESC",
        "page_size": "50"
    }
    params["sign"] = sign(params)
    r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=20)
    return r.json().get("aliexpress_affiliate_product_query_response", {}) \
        .get("resp_result", {}).get("result", {}) \
        .get("products", {}).get("product", [])

def short_link(url):
    slow(1.5)
    params = {
        "app_key": APP_KEY,
        "method": "aliexpress.affiliate.link.generate",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "format": "json",
        "sign_method": "md5",
        "v": "2.0",
        "partner_id": "top-autopilot",
        "promotion_link_type": "0",
        "source_values": url.split("?")[0],
        "tracking_id": TRACKING_ID
    }
    params["sign"] = sign(params)
    r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15).json()
    return r["aliexpress_affiliate_link_generate_response"]["resp_result"]["result"] \
        ["promotion_links"]["promotion_link"][0].get("promotion_short_link")

# ================== IMAGE ==================
def collage(urls):
    imgs = []
    for u in urls:
        try:
            slow(1)
            img = Image.open(io.BytesIO(session.get(u).content)).resize((500,500))
        except:
            img = Image.new("RGB",(500,500),"white")
        imgs.append(img)

    base = Image.new("RGB",(1000,1000),"white")
    pos = [(0,0),(500,0),(0,500),(500,500)]
    for i in range(4):
        base.paste(imgs[i],pos[i])

    d = ImageDraw.Draw(base)
    font = ImageFont.truetype("DejaVuSans-Bold.ttf", 90)

    for i,(x,y) in enumerate([(30,30),(530,30),(30,530),(530,530)]):
        d.ellipse([x,y,x+130,y+130],fill="#FFD700",outline="black",width=6)
        d.text((x+45,y+25),str(i+1),fill="black",font=font)

    buf = io.BytesIO()
    base.save(buf,"JPEG",quality=95)
    buf.seek(0)
    return buf

# ================== BOT ==================
@bot.message_handler(func=lambda m: m.text.startswith("חפש לי"))
def run(m):
    query_he = m.text.replace("חפש לי","").strip()
    bot.reply_to(m, f"🕵️‍♂️ מחפש לעומק: {query_he}...")
    slow(4)

    query_en = GoogleTranslator(source="auto",target="en").translate(query_he).lower()
    category = detect_category(query_en)

    raw = ali_search(query_en)
    results = []

    for p in raw:
        if len(results) == 4:
            break
        if not valid_for_category(p["product_title"], category):
            continue

        results.append(p)

    if not results:
        bot.send_message(m.chat.id, "🛑 לא נמצאו מוצרים אמיתיים שעומדים בסטנדרט.")
        return

    links = [short_link(p["product_detail_url"]) for p in results]
    img = collage([p["product_main_image_url"] for p in results])

    text = f"🏆 <b>הבחירות עבור: {query_he}</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i,p in enumerate(results):
        title_he = GoogleTranslator(source="auto",target="iw").translate(p["product_title"])
        text += f"{i+1}. <b>{title_he}</b>\n"
        text += f"💰 {p['target_sale_price']}₪ | ⭐ {p.get('evaluate_rate','4.7')} | 🛒 {p.get('last_volume','100+')}\n"
        text += f"{links[i]}\n\n"
        kb.add(types.InlineKeyboardButton(f"🛒 קנייה {i+1}", url=links[i]))

    bot.send_photo(m.chat.id, img, caption=text, parse_mode="HTML", reply_markup=kb)

print("✅ DrDeals FINAL RUNNING")
bot.infinity_polling()
