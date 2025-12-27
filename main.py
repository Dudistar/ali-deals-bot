# ==========================================
# DrDeals Premium – TRUE AI POWERED (The Real Deal)
# ==========================================
# זהו הקוד היחיד שמשתמש בבינה מלאכותית אמיתית לסינון וכתיבה.
# הוא איטי (כי הוא חושב), והוא מדויק.

import telebot
import requests
import time
import hashlib
import logging
import io
import sys
import os
import json
from telebot import types
from PIL import Image, ImageDraw
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# --- הגדרת AI (המוח) ---
import google.generativeai as genai

# הגדרות
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"
# מפתח ה-AI שלך (חובה שיהיה מוגדר במשתני הסביבה ב-Railway)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ שגיאה קריטית: חסר מפתח GEMINI_API_KEY בהגדרות!")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
bot = telebot.TeleBot(BOT_TOKEN)

session = requests.Session()
adapter = HTTPAdapter(max_retries=Retry(connect=3, backoff_factor=1))
session.mount('https://', adapter)

# ==========================================
# 🧠 פונקציית העל: ניתוח מוצר ע"י AI
# ==========================================
def analyze_product_with_ai(user_query, product_title, price):
    """
    שולח את המוצר ל-Gemini כדי שיחליט אם הוא רלוונטי ויכתוב כותרת שיווקית.
    """
    prompt = f"""
    Acting as a professional shopping assistant.
    User searched for: "{user_query}" (Hebrew).
    Found product on AliExpress: "{product_title}". Price: {price} ILS.
    
    Task:
    1. STRICTLY Check relevance. If User asks for "Drone" and Product is "Hair Clipper" or "Spare Part" -> REJECT.
    2. If Relevant: Write a short, engaging Hebrew title (max 10 words) with emojis. Not a direct translation, but a marketing title.
    3. Return JSON ONLY: {{"valid": true/false, "title": "..."}}
    """
    
    try:
        # כאן קורה הקסם (וההשהייה האמיתית)
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        return data
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return {"valid": False, "title": ""}

# ==========================================
# 🎣 אליאקספרס (מביא חומר גלם)
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_ali_products_raw(query):
    # חיפוש רחב - ה-AI כבר יסנן את הזבל
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
        "page_size": "20", # מביאים 20, ה-AI יבחר את הטובים
        "min_sale_price": "20"
    }
    params["sign"] = generate_sign(params)
    try:
        r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        return data["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]
    except: return []

# ==========================================
# 🔗 לינקים ותמונות
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

def create_collage(urls):
    imgs = []
    for u in urls[:4]:
        try:
            img = Image.open(io.BytesIO(session.get(u, timeout=5).content)).resize((500,500))
            imgs.append(img)
        except: imgs.append(Image.new("RGB",(500,500),"white"))
    
    while len(imgs)<4: imgs.append(Image.new("RGB",(500,500),"white"))
    canvas = Image.new("RGB",(1000,1000),"white")
    canvas.paste(imgs[0],(0,0)); canvas.paste(imgs[1],(500,0))
    canvas.paste(imgs[2],(0,500)); canvas.paste(imgs[3],(500,500))
    
    draw = ImageDraw.Draw(canvas)
    for i, (x,y) in enumerate([(30,30), (530,30), (30,530), (530,530)]):
        draw.ellipse((x,y,x+70,y+70),fill="#FFD700",outline="black",width=3)
        draw.text((x+25,y+15),str(i+1),fill="black", font_size=40)
    
    out = io.BytesIO()
    canvas.save(out,"JPEG",quality=85)
    out.seek(0)
    return out

# ==========================================
# 🚀 הבוט
# ==========================================
@bot.message_handler(func=lambda m: True)
def handler(m):
    if not m.text.startswith("חפש לי"): return
    query = m.text.replace("חפש לי","").strip()
    
    # 1. התחלה
    bot.reply_to(m, f"🕵️‍♂️ **מפעיל סריקת AI עבור:** {query}...\n⏳ _זה ייקח כ-15 שניות, אני בודק כל מוצר ידנית..._", parse_mode="Markdown")
    bot.send_chat_action(m.chat.id, "typing")

    # 2. תרגום ראשוני (רק כדי לשלוח לאליאקספרס)
    # נשתמש ב-Gemini גם לתרגום כדי שיהיה מדויק
    try:
        trans_prompt = f"Translate '{query}' to English for AliExpress search. Output ONLY the English keywords."
        query_en = model.generate_content(trans_prompt).text.strip()
    except:
        query_en = query # Fallback
    
    # 3. משיכת נתונים גולמיים
    raw_products = get_ali_products_raw(query_en)
    if not raw_products:
        bot.send_message(m.chat.id, "🛑 לא נמצאו מוצרים במאגר הראשוני.")
        return

    # 4. הלולאה החכמה (הלב של הבוט)
    final_products = []
    
    # עוברים על המוצרים הגולמיים ושולחים ל-AI לבדיקה
    # זה מה שיוצר את ההשהייה הטבעית ואת האיכות
    for p in raw_products:
        if len(final_products) >= 4: break # מספיק לנו 4 מושלמים
        
        # עדכון סטטוס למשתמש כל כמה שניות (כדי שלא יחשוב שנתקע)
        bot.send_chat_action(m.chat.id, "typing")
        
        analysis = analyze_product_with_ai(query, p["product_title"], p["target_sale_price"])
        
        if analysis["valid"]:
            p["ai_title"] = analysis["title"] # שומרים את הכותרת היפה שה-AI כתב
            final_products.append(p)
            print(f"✅ AI Approved: {analysis['title']}")
        else:
            print(f"❌ AI Rejected: {p['product_title'][:30]}...")

    if not final_products:
        bot.send_message(m.chat.id, "🛑 ה-AI סינן את כל התוצאות כי הן לא היו רלוונטיות מספיק (הגנה מפני זבל).")
        return

    # 5. הצגה
    images = []
    text = f"🧥 **הבחירות של ה-AI עבורך:**\n\n"
    kb = types.InlineKeyboardMarkup()

    for i, p in enumerate(final_products):
        link = get_short_link(p.get("product_detail_url"))
        if not link: continue
        
        images.append(p.get("product_main_image_url"))
        price = p.get("target_sale_price")
        
        text += f"{i+1}. 🥇 {p['ai_title']}\n" # שימוש בכותרת AI
        text += f"💰 מחיר: {price}₪\n"
        text += f"{link}\n\n"
        
        kb.add(types.InlineKeyboardButton(f"🛍️ מוצר {i+1}", url=link))

    if images:
        try:
            collage = create_collage(images)
            bot.send_photo(m.chat.id, collage, caption=text, parse_mode="Markdown", reply_markup=kb)
        except:
            bot.send_message(m.chat.id, text, parse_mode="Markdown", reply_markup=kb)
    else:
        bot.send_message(m.chat.id, text, parse_mode="Markdown", reply_markup=kb)

print("Bot is running in TRUE AI MODE...")
bot.infinity_polling()
