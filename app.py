# app.py
from flask import Flask, request, jsonify
import telebot
import os

app = Flask(__name__)

# ==================== إعدادات البوت ====================
TOKEN = os.getenv("TELEGRAM_TOKEN")  # ضع التوكن في الـ Environment Variables
bot = telebot.TeleBot(TOKEN)

# قائمة أوامر البوت
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, 
        "مرحباً 👋\n\n"
        "أنا بوت Telegram بسيط!\n"
        "أرسل أي رسالة وسأرد عليك بنفسها (Echo Bot)")

# رد على كل الرسائل
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    try:
        bot.reply_to(message, message.text)
    except Exception as e:
        print(f"خطأ: {e}")

# ==================== Webhook Routes ====================
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return '', 403

@app.route('/', methods=['GET'])
def index():
    return "✅ البوت يعمل بنجاح! (Telegram Webhook)"

# ==================== إعداد Webhook عند بدء التشغيل ====================
@app.route('/set_webhook')
def set_webhook():
    url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'your-app-name.onrender.com')}/{TOKEN}"
    result = bot.set_webhook(url=url)
    return f"Webhook set: {result} <br>URL: {url}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
