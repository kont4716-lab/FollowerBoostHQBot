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

    async def process_update():
        await telegram_app.initialize()
        await telegram_app.process_update(update)

    asyncio.run(process_update())

    return "OK"


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
  )
