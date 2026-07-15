import os
import asyncio
import logging
import requests

from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# إعدادات التوكن ومفتاح الأخبار
TOKEN = os.getenv("TOKEN")
NEWS_API_KEY = "2dce20869fdb4a1ab19a11038bd83d8e"

if not TOKEN:
    raise ValueError("TOKEN غير موجود في Environment Variables")

WEBHOOK_URL = "https://telegramfollowerbot2026-1.onrender.com"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

app = Flask(__name__)

telegram_app = Application.builder().token(TOKEN).build()

# دالة جلب الأخبار من API
def fetch_news(query):
    # نستخدم NewsAPI للبحث، ونحدد اللغة العربية ونجلب 5 نتائج فقط لتجنب الرسائل الطويلة جداً
    url = f"https://newsapi.org/v2/everything?q={query}&apiKey={NEWS_API_KEY}&language=ar&sortBy=publishedAt&pageSize=5"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if data.get("status") == "ok":
            articles = data.get("articles", [])
            if not articles:
                return f"لم أتمكن من العثور على أخبار حديثة بخصوص: {query}"
            
            result_text = f"📰 **أحدث الأخبار عن: {query}**\n\n"
            for index, article in enumerate(articles, 1):
                title = article.get("title", "بدون عنوان")
                link = article.get("url", "")
                result_text += f"{index}- {title}\n🔗 {link}\n\n"
                
            return result_text
        else:
            return "⚠️ حدث خطأ من مصدر الأخبار، يرجى المحاولة لاحقاً."
    except Exception as e:
        logging.error(f"Error fetching news: {e}")
        return "⚠️ حدث خطأ أثناء الاتصال بخادم الأخبار."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحباً بك في بوت الأخبار!\n\n"
        "أرسل لي أي كلمة أو موضوع (مثل: التكنولوجيا، الرياضة، فلسطين) وسأقوم بالبحث عن أحدث الأخبار المتعلقة به.\n\n"
        "أرسل /help لرؤية الأوامر."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠️ الأوامر المتاحة:\n\n"
        "/start - بدء البوت\n"
        "/help - المساعدة\n"
        "/info - معلومات البوت\n\n"
        "🔍 للبحث عن خبر: فقط اكتب الكلمة المفتاحية وأرسلها."
    )


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ البوت يعمل بنجاح على Render 🚀\n"
        "مصدر الأخبار: NewsAPI"
    )

# دالة التعامل مع الرسائل النصية للبحث عن الأخبار
async def search_news_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        query = update.message.text
        
        # إرسال رسالة انتظار للمستخدم
        wait_message = await update.message.reply_text(f"🔍 جاري البحث عن أحدث الأخبار حول: {query}...")
        
        # تشغيل دالة جلب الأخبار (نستخدم to_thread حتى لا نعطل الـ async loop)
        news_result = await asyncio.to_thread(fetch_news, query)
        
        # تعديل رسالة الانتظار بالنتائج
        await wait_message.edit_text(news_result, disable_web_page_preview=True)


telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(CommandHandler("info", info))

# ربط الرسائل النصية العادية بدالة البحث عن الأخبار
telegram_app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, search_news_handler)
)


@app.route("/")
def home():
    return "Telegram News Bot is running!"


@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(
        request.get_json(force=True),
        telegram_app.bot
    )

    async def process_update():
        await telegram_app.process_update(update)

    asyncio.run(process_update())

    return "OK"


async def setup_bot():
    await telegram_app.initialize()

    await telegram_app.bot.set_webhook(
        f"{WEBHOOK_URL}/{TOKEN}"
    )

    await telegram_app.start()

    print("🤖 News Bot started successfully")


if __name__ == "__main__":
    asyncio.run(setup_bot())

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
