# ==========================================
# DrDeals Premium – THINKING EDITION
# ==========================================
import telebot, requests, time, hashlib, logging, io, sys, os, json, re
from telebot import types
from PIL import Image, ImageDraw, ImageFont
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
HARDCODED_KEY = "AIzaSyBzR-46-B13sdh1UIPVM2hOJDjIR_8ZQ-4"
genai.configure(api_key=HARDCODED_KEY)
model = genai.GenerativeModel("gemini-pro")

# ==========================================
# ⚙️ מערכת
# ==========================================
bot = telebot.TeleBot(BOT_TOKEN)
session = requests.Session()
logging.basicConfig(level=logging.INFO)

# ==========================================
# 🧠 AI אמיתי
# ==========================================
def analyze_with_ai(query, title):
    prompt = f"""
    Is this product REALLY matching the search?

    Search: "{query}"
    Product: "{title}"

    Rules:
    - Clothing only
    - Must be a coat / jacket / trench
    - If accessory / tool / part → INVALID

    Return JSON only:
    {{
      "valid": true/false,
      "short_title": "עברית קצר",
      "reason": "סיבה קצרה"
    }}
    """

    try:
        time.sleep(2)  # 🧠 חשיבה
        r = model.generate_content(prompt)
        data = json.loads(r.text.strip("```json").strip("```"))
        return data
    except:
        return {"valid": False}

# ==========================================
# 🔍 AliExpress
# ==========================================
def sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

def get_products(q):
    params = {
        "app_key": APP_KEY,
        "method": "aliexpress.affiliate.product.query",
        "keywords": q,
        "format": "json",
        "v": "2.0",
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "sign_method": "md5",
        "page_size": "50",
        "target_currency": "ILS",
        "ship_to_country": "IL"
    }
    params["sign"] = sign(params)
    r = session.post("https://api-sg.aliexpress.com/sync", data=params, timeout=15)
    return r.json()["aliexpress_affiliate_product_query_response"]["resp_result"]["result"]["products"]["product"]

# ==========================================
# 🚀 בוט
# ==========================================
@bot.message_handler(func=lambda m: m.text.startswith("חפש לי"))
def handle(m):
    query = m.text.replace("חפש לי", "").strip()

    msg = bot.reply_to(m, f"🧠 מתחיל חיפוש רציני עבור:\n<b>{query}</b>", parse_mode="HTML")

    time.sleep(2)
    query_en = GoogleTranslator(source="auto", target="en").translate(query)

    time.sleep(3)
    products = get_products(query_en)

    results = []
    for p in products:
        title = p["product_title"].lower()

        # סינון לוגי
        if not any(w in title for w in ["coat", "jacket", "trench"]):
            continue
        if any(bad in title for bad in ["tool", "aluminum", "protector", "part"]):
            continue

        ai = analyze_with_ai(query, p["product_title"])
        if ai.get("valid"):
            p["ai_title"] = ai.get("short_title", p["product_title"])
            results.append(p)

        if len(results) == 4:
            break

    if not results:
        bot.edit_message_text(
            "🛑 חיפשתי לעומק.\nלא נמצא מעיל אמיתי שעומד בסטנדרט.",
            m.chat.id,
            msg.message_id
        )
        return

    text = f"🏆 <b>תוצאות איכותיות עבור:</b>\n{query}\n\n"
    for i, p in enumerate(results):
        text += f"{i+1}. {p['ai_title']}\n💰 {p['target_sale_price']}₪\n\n"

    bot.edit_message_text(text, m.chat.id, msg.message_id, parse_mode="HTML")

print("🧠 DrDeals THINKING MODE ON")
bot.infinity_polling()
