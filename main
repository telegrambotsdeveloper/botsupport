import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Переменные окружения
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("✉️ Написать в поддержку")]]
    await update.message.reply_text(
        "🤖 Добро пожаловать в *Betsense AI Support Bot*!\n"
        "Нажмите кнопку ниже, чтобы связаться с поддержкой 👇",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# Обработка сообщений пользователей
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Пересылаем сообщение админу
        await update.message.forward(chat_id=ADMIN_ID)
        await update.message.reply_text("✅ Ваше сообщение отправлено в поддержку!")
    except Exception as e:
        print(f"Ошибка пересылки: {e}")
        await update.message.reply_text("❌ Произошла ошибка при отправке сообщения.")

# Основная функция
def main():
    app = Application.builder().token(TOKEN).build()

    # Обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    # Запуск бота
    app.run_polling()

if __name__ == "__main__":
    main()
