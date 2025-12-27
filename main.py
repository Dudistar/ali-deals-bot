import telebot
import requests
import time
import hashlib
import logging
import json

# ==========================================
# ⚙️ הגדרות
# ==========================================
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"
APP_KEY = "523460"
APP_SECRET = "Co7bNfYfqlu8KTdj2asXQV78oziICQEs"
TRACKING_ID = "DrDeals"

logging.basicConfig(level=logging.INFO)
bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 🔐 חתימה
# ==========================================
def generate_sign(params):
    s = APP_SECRET + ''.join(f"{k}{v}" for k, v in sorted(params.items())) + APP_SECRET
    return hashlib.md5(s.encode()).hexdigest().upper()

# ==========================================
# 🧪 הפונקציה שבודקת את ה"דם" של המערכת
# ==========================================
def run_system_test():
    # חיפוש נקי באנגלית, בלי קטגוריות, בלי פילטרים
    query = "Women Elegant Cream Coat"
    
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
        "page_size": "5"
    }
    params["sign"] = generate_sign(params)

    log_report = f"🧪 **דוח בדיקת מערכת**\nחיפוש: `{query}`\n\n"
    
    try:
        r = requests.post("https://api-sg.aliexpress.com/sync", data=params, timeout=10)
        data = r.json()
        
        # בדיקה 1: האם ה-API החזיר תשובה תקינה?
        if "aliexpress_affiliate_product_query_response" not in data:
            return log_report + f"❌ **שגיאה קריטית:**\n{json.dumps(data, indent=2)}"

        resp = data["aliexpress_affiliate_product_query_response"]["resp_result"]
        
        # בדיקה 2: קוד תשובה
        if resp["resp_code"] != 200:
             return log_report + f"⚠️ **שגיאת API:** קוד {resp['resp_code']}\nהודעה: {resp.get('resp_msg')}"
             
        products = resp["result"]["products"]["product"]
        if not isinstance(products, list): products = [products]
        
        # בדיקה 3: מה באמת קיבלנו? (החלק החשוב!)
        log_report += "📦 **תוצאות גולמיות (מה אליאקספרס רואה):**\n"
        for i, p in enumerate(products):
            title = p.get('product_title')
            cat_id = p.get('product_category_id')
            price = p.get('target_sale_price')
            
            log_report += f"\n{i+1}. **{title}**\n🆔 קטגוריה: `{cat_id}` | 💰 {price}\n"
            
        return log_report

    except Exception as e:
        return f"🔥 **שגיאה בביצוע הבדיקה:**\n{str(e)}"

# ==========================================
# 🚀 הבוט
# ==========================================
@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "הבוט במצב דיאגנוסטיקה.\nשלח `/test` כדי לראות מה אליאקספרס מחזיר באמת.")

@bot.message_handler(commands=['test'])
def test_command(m):
    bot.send_message(m.chat.id, "🔄 מריץ בדיקה מול השרתים של אליאקספרס... (בלי פילטרים)")
    report = run_system_test()
    # שליחת הדוח לטלגרם (בחלקים אם הוא ארוך מידי)
    if len(report) > 4000:
        bot.send_message(m.chat.id, report[:4000], parse_mode="Markdown")
        bot.send_message(m.chat.id, report[4000:], parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, report, parse_mode="Markdown")

bot.infinity_polling()
