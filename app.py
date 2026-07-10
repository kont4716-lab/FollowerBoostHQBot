import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN")

app = Flask(__name__)

telegram_app = Application.builder().token(TOKEN).build()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحبًا بك في FollowerBoostHQBot\n\n✅ البوت يعمل بنجاح"
    )


telegram_app.add_handler(CommandHandler("start", start))


# إنشاء حلقة asyncio عند تشغيل التطبيق
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

loop.run_until_complete(telegram_app.initialize())


@app.route("/")
def home():
    return "FollowerBoostHQBot is running ✅"


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)

    update = Update.de_json(
        data,
        telegram_app.bot
    )

    loop.run_until_complete(
        telegram_app.process_update(update)
    )

    return "OK"


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
)
