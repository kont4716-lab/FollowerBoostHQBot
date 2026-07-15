# main.py
import os
import requests
from urllib.parse import quote
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import asyncio

TOKEN=os.getenv("TOKEN")
WEBHOOK_URL=os.getenv("WEBHOOK_URL","https://your-render-url.onrender.com")
app=Flask(__name__)
tg=Application.builder().token(TOKEN).build()

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أرسل أي موضوع للبحث في ويكيبيديا.")

async def help_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start /help /info")

async def info(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بوت ويكيبيديا")

def wiki_summary(q,lang):
    url=f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(q)}"
    r=requests.get(url,headers={"User-Agent":"TelegramWikiBot/1.0"},timeout=10)
    if r.status_code==200:
        return r.json()
    return None

async def search(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.message.text.strip()
    data=wiki_summary(q,"ar") or wiki_summary(q,"en")
    if not data:
        await update.message.reply_text("لم يتم العثور على نتيجة.")
        return
    msg=f"📚 {data.get('title')}\n\n{data.get('extract','')}"
    await update.message.reply_text(msg)
    img=data.get("thumbnail",{}).get("source")
    if img:
        await update.message.reply_photo(img)

tg.add_handler(CommandHandler("start",start))
tg.add_handler(CommandHandler("help",help_command))
tg.add_handler(CommandHandler("info",info))
tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,search))

@app.route("/")
def home(): return "OK"

@app.route(f"/{TOKEN}",methods=["POST"])
def webhook():
    upd=Update.de_json(request.get_json(force=True),tg.bot)
    asyncio.run(tg.process_update(upd))
    return "OK"

async def setup():
    await tg.initialize()
    await tg.bot.set_webhook(f"{WEBHOOK_URL}/{TOKEN}")
    await tg.start()

if __name__=="__main__":
    asyncio.run(setup())
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))
