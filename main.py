import os
import logging
from typing import Dict, Set, Optional

import telegram
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
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
# mapping: admin_message_id -> user_id (для ответа админа reply)
forward_map: Dict[int, int] = {}
# если пользователь нажал inline-кнопку, следующее его сообщение будет помечено и отправлено
user_waiting_for_next: Set[int] = set()

# -------------------
# Команды
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("✉️ Написать в поддержку", callback_data="contact_support")],
    ]
    await update.message.reply_text(
        "🤖 *Betsense AI Support Bot*\n\n"
        "Нажмите кнопку ниже, чтобы отправить сообщение в поддержку.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )

# Регистрация админа (если ADMIN_ID не задан через env)
async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_ID
    user = update.effective_user
    if ADMIN_ID and ADMIN_ID != user.id:
        await update.message.reply_text("Админ уже зарегистрирован (ADMIN_ID задан в env).")
        return
    ADMIN_ID = user.id
    await update.message.reply_text(f"Готово — вы зарегистрированы как админ. Ваш ID: {ADMIN_ID}")
    logger.info("Admin registered: %s (%s)", user.username, ADMIN_ID)

# -------------------
# Callback (inline button)
# -------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "contact_support":
        user_waiting_for_next.add(user_id)
        # отправляем приватный ответ в чат с пользователем
        await query.message.reply_text("✍️ Напиши своё сообщение — я передам его в поддержку. (Следующее сообщение будет отправлено.)")

# -------------------
# Вспомогательная функция: переслать/скопировать сообщение админу и запомнить mapping
# -------------------
async def forward_to_admin(msg: telegram.Message, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """
    Попробовать forward; если не выходит — попробовать copy_message; вернуть message_id сообщения у админа (или None).
    """
    try:
        forwarded = await msg.forward(chat_id=ADMIN_ID)
        admin_msg_id = forwarded.message_id
        logger.info("forwarded msg_id %s -> admin_msg_id %s", msg.message_id, admin_msg_id)
        return admin_msg_id
    except telegram.error.BadRequest as e:
        logger.warning("Forward failed (%s). Trying copy_message...", e)
        try:
            copied = await context.bot.copy_message(
                chat_id=ADMIN_ID,
                from_chat_id=msg.chat.id,
                message_id=msg.message_id
            )
            admin_msg_id = copied.message_id
            logger.info("copied msg_id %s -> admin_msg_id %s", msg.message_id, admin_msg_id)
            return admin_msg_id
        except Exception as e2:
            logger.exception("Copy failed: %s", e2)
            # fallback: отправим админу текстовое уведомление с ID пользователя
            username = msg.from_user.username or f"{msg.from_user.first_name or ''} {msg.from_user.last_name or ''}"
            text = f"📩 Новое сообщение от {username} (ID: {msg.from_user.id}):\n\n"
            if msg.text:
                text += msg.text
            else:
                text += "[не удалось переслать вложение — сообщение содержит медиа/файл]"
            try:
                sent = await context.bot.send_message(chat_id=ADMIN_ID, text=text)
                return sent.message_id
            except Exception:
                logger.exception("Не удалось отправить fallback админу.")
                return None
    except Exception:
        logger.exception("Unexpected error while forwarding")
        return None

# -------------------
# Основной обработчик сообщений
# -------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    sender_id = msg.from_user.id

    # --- Админский поток: ответы админу на пересланные сообщения (Reply) или команда /reply
    if sender_id == ADMIN_ID:
        # 1) Если админ ответил на пересланное сообщение (Reply) -> используем mapping
        if msg.reply_to_message:
            replied_admin_id = msg.reply_to_message.message_id
            target_user = forward_map.get(replied_admin_id)
            if target_user:
                await send_admin_reply_to_user(msg, target_user, context)
                return
            # возможно админ ответил на ID-уведомление -> попытаемся извлечь ID из текста
            # fallthrough -> проверка /reply ниже
        # 2) /reply user_id текст
        if msg.text and msg.text.startswith("/reply"):
            parts = msg.text.split(" ", 2)
            if len(parts) < 3:
                await msg.reply_text("Использование: /reply USER_ID текст_ответа")
                return
            try:
                target = int(parts[1])
                text = parts[2]
                await context.bot.send_message(chat_id=target, text=f"📢 Ответ поддержки Betsense AI:\n\n{text}")
                await msg.reply_text("✅ Ответ отправлен пользователю.")
            except Exception as e:
                logger.exception("Ошибка /reply: %s", e)
                await msg.reply_text("❌ Не удалось отправить сообщение. Проверь ID.")
            return

        # Немного помощи админу
        await msg.reply_text("ℹ️ Ответьте *на пересланное сообщение* пользователя, чтобы отправить ответ ему. "
                             "Или используйте: /reply USER_ID текст", parse_mode="Markdown")
        return

    # --- Пользовательский поток: любое сообщение от пользователя пересылаем админу
    # Если пользователь нажал inline кнопку — пометим и пересылаем следующее сообщение (но здесь мы отправляем всегда)
    try:
        admin_msg_id = await forward_to_admin(msg, context)
        if admin_msg_id:
            forward_map[admin_msg_id] = sender_id
    except Exception:
        logger.exception("Ошибка при пересылке сообщения админу")

    # Дополнительно отправим админу айди пользователя (чтобы было видно прямо текстом)
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🆔 ID пользователя: {sender_id}")
    except Exception:
        logger.debug("Не удалось отправить ID админу (возможно, бот не может писать админ-аккаунту)")

    # Подтверждение пользователю
    try:
        await msg.reply_text("✅ Ваше сообщение отправлено в поддержку Betsense AI. Ожидайте ответа.")
    except Exception:
        logger.exception("Не удалось подтвердить пользователю отправку")

    # Снять ожидание, если он нажал кнопку
    user_waiting_for_next.discard(sender_id)


# -------------------
# Отправка ответа админа пользователю (поддерживает текст/фото/документы/голос/видео/стикер)
# -------------------
async def send_admin_reply_to_user(admin_msg: telegram.Message, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        if admin_msg.text:
            await context.bot.send_message(chat_id=user_id, text=f"📢 Ответ поддержки Betsense AI:\n\n{admin_msg.text}")
            await admin_msg.reply_text("✅ Ответ отправлен пользователю.")
            return

        # медиа-обработка
        if admin_msg.photo:
            await context.bot.send_photo(chat_id=user_id, photo=admin_msg.photo[-1].file_id, caption=admin_msg.caption or "")
        elif admin_msg.document:
            await context.bot.send_document(chat_id=user_id, document=admin_msg.document.file_id, caption=admin_msg.caption or "")
        elif admin_msg.voice:
            await context.bot.send_voice(chat_id=user_id, voice=admin_msg.voice.file_id, caption=admin_msg.caption or "")
        elif admin_msg.video:
            await context.bot.send_video(chat_id=user_id, video=admin_msg.video.file_id, caption=admin_msg.caption or "")
        elif admin_msg.sticker:
            await context.bot.send_sticker(chat_id=user_id, sticker=admin_msg.sticker.file_id)
        elif admin_msg.animation:
            await context.bot.send_animation(chat_id=user_id, animation=admin_msg.animation.file_id, caption=admin_msg.caption or "")
        else:
            # для других типов — попробуем переслать напрямую (forward)
            await admin_msg.forward(chat_id=user_id)

        await admin_msg.reply_text("✅ Ответ отправлен пользователю.")
    except telegram.error.BadRequest as e:
        logger.exception("BadRequest при отправке ответа пользователю: %s", e)
        await admin_msg.reply_text("❌ Не удалось отправить ответ — возможно пользователь не начинал диалог с ботом.")
    except Exception:
        logger.exception("Ошибка при отправке ответа пользователю")
        await admin_msg.reply_text("❌ Произошла ошибка при отправке ответа.")

# -------------------
# Обработчик ошибок
# -------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Update caused error: %s", context.error)

# -------------------
# Запуск
# -------------------
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register_admin", register_admin))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    app.add_error_handler(error_handler)

    logger.info("Бот запущен (run_polling). ADMIN_ID=%s", ADMIN_ID or "<not set>")
    app.run_polling()

if __name__ == "__main__":
    main()
