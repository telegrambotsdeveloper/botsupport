import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# -------------------
# Настройки
# -------------------
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

if not TOKEN or not ADMIN_ID:
    raise ValueError("Не установлены TELEGRAM_BOT_TOKEN или ADMIN_ID!")

# -------------------
# Логирование
# -------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------
# Команды
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("✉️ Написать в поддержку")]]
    await update.message.reply_text(
        "🤖 Добро пожаловать в *Betsense AI Support Bot*!\n"
        "Нажмите кнопку ниже, чтобы связаться с поддержкой 👇",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# -------------------
# Обработка сообщений пользователей
# -------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Пересылаем админу
        await update.message.forward(chat_id=ADMIN_ID)
        await update.message.reply_text("✅ Ваше сообщение отправлено в поддержку!")
    except Exception as e:
        logger.error(f"Ошибка при пересылке сообщения: {e}")
        await update.message.reply_text("❌ Не удалось отправить сообщение в поддержку.")

# -------------------
# Обработка кнопок
# -------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=f"Вы нажали: {query.data}")

# -------------------
# Админские команды
# -------------------
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    if context.args:
        text = " ".join(context.args)
        # Здесь можно добавить рассылку пользователям, если есть список
        await update.message.reply_text(f"Сообщение для рассылки: {text}")
    else:
        await update.message.reply_text("Использование: /broadcast текст_сообщения")

# -------------------
# Главная функция
# -------------------
def main():
    app = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Запуск polling
    app.run_polling()

# -------------------
# Запуск
# -------------------
if __name__ == "__main__":
    main()
