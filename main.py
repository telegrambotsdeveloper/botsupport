import os
import logging
from threading import Thread
from typing import Dict, Set, Optional

from flask import Flask
import telegram
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# -------------------
# Настройка / env
# -------------------
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # обязателен
_admin_env = os.environ.get("ADMIN_ID", "")
try:
    ADMIN_ID: int = int(_admin_env) if _admin_env else 0
except ValueError:
    ADMIN_ID = 0

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан! Установи переменную окружения.")

# -------------------
# Логирование
# -------------------
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# -------------------
# В памяти
# -------------------
forward_map: Dict[int, int] = {}
user_waiting_for_next: Set[int] = set()

# -------------------
# Flask для Render
# -------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))  # Render задаёт PORT автоматически
    flask_app.run(host="0.0.0.0", port=port)

# -------------------
# Telegram Handlers
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("✉️ Написать в поддержку", callback_data="contact_support")]]
    await update.message.reply_text(
        "🤖 *Betsense AI Support Bot*\n\nНажмите кнопку ниже, чтобы отправить сообщение в поддержку.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )

async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    user = update.effective_user
    if ADMIN_ID and ADMIN_ID != user.id:
        await update.message.reply_text("Админ уже зарегистрирован (ADMIN_ID задан в env).")
        return
    ADMIN_ID = user.id
    await update.message.reply_text(f"Готово — вы зарегистрированы как админ. Ваш ID: {ADMIN_ID}")
    logger.info("Admin registered: %s (%s)", user.username, ADMIN_ID)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "contact_support":
        user_waiting_for_next.add(user_id)
        await query.message.reply_text(
            "✍️ Напиши своё сообщение — я передам его в поддержку. (Следующее сообщение будет отправлено.)"
        )

# -------------------
# Пересылка сообщений админу
# -------------------
async def forward_to_admin(msg: telegram.Message, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    try:
        forwarded = await msg.forward(chat_id=ADMIN_ID)
        admin_msg_id = forwarded.message_id
        forward_map[admin_msg_id] = msg.from_user.id
        return admin_msg_id
    except Exception:
        logger.exception("Ошибка при пересылке сообщения админу")
        return None

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    sender_id = msg.from_user.id

    # --- Админский поток ---
    if sender_id == ADMIN_ID:
        # Reply или /reply
        if msg.reply_to_message:
            replied_admin_id = msg.reply_to_message.message_id
            target_user = forward_map.get(replied_admin_id)
            if target_user:
                await context.bot.send_message(chat_id=target_user, text=msg.text or "Сообщение без текста")
                await msg.reply_text("✅ Ответ отправлен пользователю.")
                return
        if msg.text and msg.text.startswith("/reply"):
            parts = msg.text.split(" ", 2)
            if len(parts) >= 3:
                target = int(parts[1])
                text = parts[2]
                await context.bot.send_message(chat_id=target, text=f"📢 Ответ поддержки Betsense AI:\n\n{text}")
                await msg.reply_text("✅ Ответ отправлен пользователю.")
            return
        return

    # --- Пользовательский поток ---
    await forward_to_admin(msg, context)
    await msg.reply_text("✅ Ваше сообщение отправлено в поддержку Betsense AI. Ожидайте ответа.")
    user_waiting_for_next.discard(sender_id)

# -------------------
# Ошибки
# -------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Update caused error: %s", context.error)

# -------------------
# Основной запуск
# -------------------
def run_bot():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register_admin", register_admin))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))
    application.add_error_handler(error_handler)

    logger.info("Бот запущен (run_polling). ADMIN_ID=%s", ADMIN_ID or "<not set>")
    application.run_polling()

if __name__ == "__main__":
    # Flask в отдельном потоке, чтобы Render видел открытый порт
    Thread(target=run_flask).start()
    # Бот в основном потоке
    run_bot()
