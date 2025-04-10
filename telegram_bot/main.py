import asyncio
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, MessageHandler, filters, ContextTypes, CommandHandler

from pdf_processor import process_pdf  # Функция для обработки PDF
# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_msg = (
        f"Привет, {user.first_name}!\n"
        "Нажми кнопку ниже, чтобы создать досье."
    )
    # Создаем инлайн-кнопку
    keyboard = [[InlineKeyboardButton("Создать досье", callback_data='create_dossier')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if document.mime_type != 'application/pdf':
        await update.message.reply_text("Пожалуйста, отправь PDF файл.")
        return

    # Скачиваем файл во временную директорию
    downloads_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    input_path = os.path.join(downloads_dir, f"{document.file_id}.pdf")

    try:
        file = await document.get_file()
        await file.download_to_drive(custom_path=input_path)
    except Exception as e:
        logger.exception("Ошибка при скачивании файла")
        await update.message.reply_text("Произошла ошибка при скачивании файла.")
        return

    await update.message.reply_text("Обрабатываю файл, пожалуйста, подожди...")

    output_path = None
    try:
        # process_pdf — синхронная функция, поэтому запускаем её в отдельном потоке
        loop = asyncio.get_running_loop()
        output_path = await loop.run_in_executor(None, process_pdf, input_path)
        await update.message.reply_text("Готово! Отправляю обработанный файл.")
        # Отправляем файл
        with open(output_path, 'rb') as output_file:
            await update.message.reply_document(document=output_file)
    except Exception as e:
        logger.exception("Ошибка при обработке файла")
        await update.message.reply_text("Произошла ошибка при обработке файла.")
    finally:
        # Удаляем временные файлы, если они существуют
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
            if output_path and os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            logger.warning("Не удалось удалить временные файлы: %s", e)

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'create_dossier':
        await query.message.reply_text("Пожалуйста, отправьте PDF файл для обработки.")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не задан!")
        raise Exception("TELEGRAM_BOT_TOKEN не задан!")
    else:
        logger.info("Получен токен: %s...", token[:2])

    application = ApplicationBuilder().token(token).build()
    application.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(CommandHandler("start", start))
    application.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
