# ==========================================
# DrDeals Premium – PRO SEARCH EDITION
# ==========================================
import telebot, requests, time, hashlib, logging, io, sys, os, json
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
genai.configure(api_key=os.environ.get(
    "GEMINI_API_KEY",
    "AIzaSyBzR-46-B13sdh1UIPVM2hOJDjIR_8ZQ-4"
))
model = genai.GenerativeModel("gemini-pro")

# ==========================================
# ⚙️ מערכת
# ==========================================
logging.basicConfig(level=logging.INFO)
bot = telebot.TeleBot(BOT_TOKEN)
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(connect=3, backoff_factor=1)))

# ==========================================
# 🎨 גרפיקה – מספרים גדולים
# ==========================================
def load_font(size):
    try:
        return ImageFont.truetype("RobotoSlab-Bold.ttf", size)
    except:
        return ImageFont.load_default()

def create_collage(urls):
    imgs = []
    for u in urls[:4]:
        try:
            r = session.get(u, timeout=5)
            imgs.append(Image.open(io.BytesIO(r.content)).resize((500,500)))
        except:
            imgs.append(Image.new("RGB",(500,500),"white"))

    canvas = Image.new("RGB",(1000,1000),"white")
    for i,(x,y) in enumerate([(0,0),(500,0),(0,500),(500,500)]):
        canvas.paste(imgs[i],(x,y))

    draw = ImageDraw.Draw(canvas)
    font = load_font(110)

    for i,(x,y) in enumerate([(30,30),(530,30),(30,530),(530,530)]):
        draw.ellipse([x,y,x+140,y+140],fill="#FFD700",outline="black",width=5)
        num = str(i+1)
        box = draw.textbbox((0,0),num,font=font)
        tx = x + (140-(box[2]-box[0]))//2
        ty = y + (140-(box[3]-box[1]))//2 - 5
        draw.text((tx,ty),num,font=font,fill="black")

    out = io.BytesIO()
    canvas.save(out,"JPEG",quality=95)
    out.seek(0)
    return out

# ==========================================
# 🧠 AI – רק תוכן, בלי פסילה
# ==========================================
def ai_rewrite(search, title, price):
    prompt = f"""
אתה קופירייטר עברי.
חיפוש: "{search}"
מוצר: "{title}"
מחיר: {price}

תן:
1. כותרת בעברית (עד 5 מילים)
2. תיאור קצר (עד 7 מילים)

JSON בלבד:
{{"title":"...","desc":"..."}}
"""
    try:
        r = model.generate_content(prompt).text
        return json.loads(r.replace("```json","").replace("```",""))
    except:
        return {"title": title[:25], "desc": "בחירה מומלצת"}

# ==========================================
# 🔧 אליאקספרס
# ==========================================
def sign(p):
    s = APP_SECRET + ''.join(f"{k}{v}" for k,v in sorted(p.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def ali_search(q):
    p = {
        "app_key":APP_KEY,"method":"aliexpress.affiliate.product.query",
        "timestamp":time.strftime('%Y-%m-%d %H:%M:%S'),
        "format":"json","v":"2.0","sign_method":"md5",
        "keywords":q,"page_size":"30","target_currency":"ILS",
        "ship_to_country":"IL"
    }
    p["sign"]=sign(p)
    r = session.post("https://api-sg.aliexpress.com/sync",data=p,timeout=15).json()
    return r["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]

def short_link(url):
    if not url: return url
    p = {
        "app_key":APP_KEY,"method":"aliexpress.affiliate.link.generate",
        "timestamp":time.strftime('%Y-%m-%d %H:%M:%S'),
        "format":"json","v":"2.0","sign_method":"md5",
        "source_values":url.split("?")[0],"tracking_id":TRACKING_ID
    }
    p["sign"]=sign(p)
    try:
        r = session.post("https://api-sg.aliexpress.com/sync",data=p,timeout=10).json()
        return r["aliexpress_affiliate_link_generate_response"]["resp_result"]["result"]["promotion_links"]["promotion_link"][0]["promotion_short_link"]
    except:
        return url

# ==========================================
# 🚀 הבוט
# ==========================================
@bot.message_handler(func=lambda m: m.text and m.text.startswith("חפש לי"))
def run(m):
    q_he = m.text.replace("חפש לי","").strip()
    msg = bot.reply_to(m,f"🕵️‍♂️ מחפש לעומק:\n<b>{q_he}</b>",parse_mode="HTML")

    time.sleep(2)
    q_en = GoogleTranslator(source="auto",target="en").translate(q_he)

    time.sleep(2)
    products = ali_search(q_en)

    if not products:
        bot.edit_message_text(f"❌ לא נמצאו תוצאות עבור:\n<b>{q_he}</b>",m.chat.id,msg.message_id,parse_mode="HTML")
        return

    final = []
    for p in products:
        if len(final)==4: break
        time.sleep(1.5)
        ai = ai_rewrite(q_he,p["product_title"],p["target_sale_price"])
        p["t"]=ai["title"]
        p["d"]=ai["desc"]
        final.append(p)

    collage = create_collage([p["product_main_image_url"] for p in final])

    text = f"🏆 <b>הבחירות עבור:</b> {q_he}\n\n"
    kb = types.InlineKeyboardMarkup()

    for i,p in enumerate(final):
        link = short_link(p["product_detail_url"])
        text += f"<b>{i+1}. {p['t']}</b>\n{p['d']}\n💰 {p['target_sale_price']}₪\n{link}\n\n"
        kb.add(types.InlineKeyboardButton(f"🛒 קנה {i+1}",url=link))

    bot.delete_message(m.chat.id,msg.message_id)
    bot.send_photo(m.chat.id,collage,caption=text,parse_mode="HTML",reply_markup=kb)

print("🚀 DrDeals PRO RUNNING")
bot.infinity_polling()
