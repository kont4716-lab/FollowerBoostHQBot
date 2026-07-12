from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import os

TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أنا أعمل ✅")

application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))

if __name__ == "__main__":
    application.run_polling()
