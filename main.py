# ==========================================
# DrDeals Premium – FIXED & STABLE
# ==========================================
import telebot, requests, time, hashlib, io, os, json
from telebot import types
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator

# ================== CONFIG ==================
# עדיף למשוך משתנים מהסביבה, אבל השארתי ככה לנוחותך כרגע
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

bot = telebot.TeleBot(BOT_TOKEN)
session = requests.Session()

# ================== HELPERS ==================
def sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

# פונקציה להורדת פונט אם הוא חסר (מונע קריסה בשרתים)
def get_font():
    font_path = "DejaVuSans-Bold.ttf"
    if not os.path.exists(font_path):
        try:
            print("Downloading font...")
            url = "https://github.com/google/fonts/raw/main/apache/robotoslab/RobotoSlab-Bold.ttf"
            r = requests.get(url)
            with open(font_path, 'wb') as f:
                f.write(r.content)
            return ImageFont.truetype(font_path, 80)
        except:
            return ImageFont.load_default()
    return ImageFont.truetype(font_path, 80)

# ================== CATEGORY LOGIC ==================
# הוספתי עוד קטגוריות בסיסיות למניעת זבל
CATEGORY_RULES = {
    "drone": ["drone", "quadcopter", "uav"],
    "smart watch": ["watch", "smartwatch", "band"],
    "headphones": ["headphone", "earphone", "earbuds"],
}

def detect_category(en_query):
    for cat, keys in CATEGORY_RULES.items():
        if any(k in en_query for k in keys):
            return cat
    return None

def valid_for_category(title, category):
    if not category: return True # אם אין קטגוריה מזוהה, לא מסננים
    title = title.lower()
    keys = CATEGORY_RULES.get(category, [])
    return any(k in title for k in keys)

# ================== ALI SEARCH ==================
def ali_search(query_en):
    # הסרתי את time.sleep כדי שיהיה מהיר
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
    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        return r.json().get("aliexpress_affiliate_product_query_response", {}) \
            .get("resp_result", {}).get("result", {}) \
            .get("products", {}).get("product", [])
    except Exception as e:
        print(f"Error searching: {e}")
        return []

def short_link(url):
    try:
        clean_url = url.split("?")[0]
        params = {
            "app_key": APP_KEY,
            "method": "aliexpress.affiliate.link.generate",
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "format": "json",
            "sign_method": "md5",
            "v": "2.0",
            "partner_id": "top-autopilot",
            "promotion_link_type": "0",
            "source_values": clean_url,
            "tracking_id": TRACKING_ID
        }
        params["sign"] = sign(params)
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10).json()
        return r["aliexpress_affiliate_link_generate_response"]["resp_result"]["result"] \
            ["promotion_links"]["promotion_link"][0].get("promotion_short_link")
    except:
        return url # במקרה של שגיאה מחזיר את הלינק המקורי

# ================== IMAGE ==================
def collage(urls):
    imgs = []
    for u in urls:
        try:
            resp = session.get(u, timeout=5)
            img = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((500,500))
            imgs.append(img)
        except:
            img = Image.new("RGB",(500,500),"white") # ריבוע לבן אם התמונה נכשלה
            imgs.append(img)

    # משלימים ל-4 תמונות אם יש פחות
    while len(imgs) < 4:
        imgs.append(Image.new("RGB",(500,500),"white"))

    base = Image.new("RGB",(1000,1000),"white")
    base.paste(imgs[0],(0,0)); base.paste(imgs[1],(500,0))
    base.paste(imgs[2],(0,500)); base.paste(imgs[3],(500,500))

    d = ImageDraw.Draw(base)
    font = get_font() # שימוש בפונקציה הבטוחה

    for i,(x,y) in enumerate([(30,30),(530,30),(30,530),(530,530)]):
        # רק אם יש באמת מוצר (לא ריבוע לבן סתם)
        if i < len(urls):
            d.ellipse([x,y,x+130,y+130],fill="#FFD700",outline="black",width=6)
            # מרכוז קל של המספר
            offset_x = 45 if i < 9 else 25
            d.text((x+offset_x,y+15),str(i+1),fill="black",font=font)

    buf = io.BytesIO()
    base.save(buf,"JPEG",quality=90)
    buf.seek(0)
    return buf

# ================== BOT ==================
@bot.message_handler(func=lambda m: m.text.startswith("חפש לי"))
def run(m):
    query_he = m.text.replace("חפש לי","").strip()
    msg = bot.reply_to(m, f"🕵️‍♂️ מחפש: {query_he}...")
    
    # שלב 1: תרגום
    try:
        query_en = GoogleTranslator(source="auto",target="en").translate(query_he).lower()
    except:
        query_en = query_he # אם התרגום נכשל משתמשים במקור

    category = detect_category(query_en)
    
    # שלב 2: חיפוש וסינון
    raw = ali_search(query_en)
    results = []

    for p in raw:
        if len(results) == 4: break
        if not valid_for_category(p["product_title"], category): continue
        results.append(p)

    if not results:
        bot.edit_message_text("🛑 לא נמצאו מוצרים תואמים.", m.chat.id, msg.message_id)
        return

    # שלב 3: יצירת תשובה
    bot.edit_message_text("🎨 מייצר תמונה וקישורים...", m.chat.id, msg.message_id)
    
    links = [short_link(p["product_detail_url"]) for p in results]
    img = collage([p["product_main_image_url"] for p in results])

    text = f"🏆 <b>הבחירות עבור: {query_he}</b>\n\n"
    kb = types.InlineKeyboardMarkup()

    for i,p in enumerate(results):
        try:
            title_he = GoogleTranslator(source="auto",target="iw").translate(p["product_title"])
        except:
            title_he = p["product_title"][:50] # כותרת מקורית אם התרגום נכשל
            
        text += f"{i+1}. <b>{title_he}</b>\n"
        text += f"💰 {p['target_sale_price']}₪ | ⭐ {p.get('evaluate_rate','4.7')} | 🛒 {p.get('last_volume','100+')}\n"
        text += f"{links[i]}\n\n"
        kb.add(types.InlineKeyboardButton(f"🛒 קנייה {i+1}", url=links[i]))

    bot.delete_message(m.chat.id, msg.message_id)
    bot.send_photo(m.chat.id, img, caption=text, parse_mode="HTML", reply_markup=kb)

print("✅ DrDeals FIXED IS RUNNING")
bot.infinity_polling()
