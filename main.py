import telebot

# הפרטים שלך
BOT_TOKEN = "8575064945:AAH_2WmHMH25TMFvt4FM6OWwfqFcDAaqCPw"

print("בודק חיבור לטלגרם...")
try:
    bot = telebot.TeleBot(BOT_TOKEN)
    me = bot.get_me()
    print(f"✅ הצלחה! מחובר בתור: {me.first_name}")
    print("הטוקן תקין. הבעיה היא בקוד הגדול.")
except Exception as e:
    print(f"❌ שגיאה: הטוקן לא תקין או חסום.")
    print(f"פירוט: {e}")
