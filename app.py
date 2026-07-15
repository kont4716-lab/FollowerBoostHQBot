import os
import asyncio
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN غير موجود")

WEBHOOK_URL = os.getenv("WEBHOOK_URL","https://followerboosthqbot.onrender.com")

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
telegram_app = Application.builder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 مرحباً بك")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start\n/help\n/info")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("البوت يعمل")

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(CommandHandler("info", info))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
    lambda u,c: u.message.reply_text(u.message.text)))

@app.route("/")
def home():
    return "OK"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    asyncio.run(telegram_app.process_update(update))
    return "OK"

async def setup():
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/{TOKEN}")
    await telegram_app.start()

asyncio.run(setup())
