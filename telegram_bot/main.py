import asyncio
import os
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Chat
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, MessageHandler, filters, ContextTypes, CommandHandler
import yaml
from pdf_processor import process_pdf, load_prompts, save_prompts, reset_prompts, parse_and_cache_pdf, generate_all_resumes, create_pdf, get_pdf_output_path

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ADMINS_FILE = 'admins.yaml'
DOWNLOADS_DIR = os.path.join(os.getcwd(), "downloads")

def load_admins():
    try:
        with open(ADMINS_FILE, 'r', encoding='utf-8') as f:
            admins = yaml.safe_load(f) or []
            admins = [int(a) for a in admins]
            return admins
    except Exception as e:
        logger.error(f"Ошибка при загрузке admins.yaml: {e}")
        return []

def save_admins(admins):
    with open(ADMINS_FILE, 'w', encoding='utf-8') as f:
        yaml.safe_dump(admins, f)

def is_admin(user_id):
    admins = load_admins()
    return user_id in admins

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    isadmin = is_admin(user_id)
    keyboard = [["Создать досье"]]
    if isadmin:
        keyboard[0].append("Команды")
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    text = "Выберите действие или отправьте PDF файл для обработки."
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif hasattr(update, "callback_query") and update.callback_query and update.callback_query.message:
        await update.callback_query.message.reply_text(text, reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if document.mime_type != 'application/pdf':
        await update.message.reply_text("Пожалуйста, отправь PDF файл.")
        return
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
    try:
        pdf_data = parse_and_cache_pdf(input_path)
        context.user_data['pdf_data'] = pdf_data
        prof_resume, talents_resume, final_resume = generate_all_resumes(pdf_data)
        context.user_data['edit_pdf'] = {
            'input_path': input_path,
            'prof_resume': prof_resume,
            'talents_resume': talents_resume,
            'final_resume': final_resume
        }
        output_path = get_pdf_output_path(pdf_data['user_name'])
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        create_pdf(output_path, pdf_data, prof_resume, talents_resume, final_resume)
        logger.info(f"Содержимое папки downloads перед отправкой: {os.listdir(downloads_dir)}")
        logger.info(f"Путь к файлу для отправки: {output_path}")
        logger.info(f"Файл существует? {os.path.exists(output_path)}")
        if not os.path.exists(output_path):
            logger.error(f"PDF не был создан: {output_path}")
            await update.message.reply_text("Ошибка: PDF не был создан.")
            return
        with open(output_path, 'rb') as output_file:
            await update.message.reply_document(document=output_file)
        user_id = update.effective_user.id
        if is_admin(user_id):
            await show_edit_menu(update, context)
        if update.message.chat.type == Chat.PRIVATE:
            await show_main_menu(update, context)
    except Exception as e:
        logger.exception("Ошибка при обработке файла")
        await update.message.reply_text("Произошла ошибка при обработке файла.")
    # Не удаляем исходный файл, чтобы можно было пересоздавать PDF при редактировании

async def show_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать профессиональные склонности", callback_data='edit_prof_resume')],
        [InlineKeyboardButton("✏️ Редактировать скрытые таланты", callback_data='edit_talents_resume')],
        [InlineKeyboardButton("✏️ Редактировать финальный вывод", callback_data='edit_final_resume')],
        [InlineKeyboardButton("✅ ОК (редактировать не надо)", callback_data='edit_ok')]
    ]
    await update.message.reply_text(
        "Выберите раздел для редактирования или нажмите ОК:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def edit_resume_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer(f"Вашему ID {user_id} запрещён доступ. Только для администратора.", show_alert=True)
        return
    section = None
    if query.data == 'edit_prof_resume':
        section = 'prof_resume'
    elif query.data == 'edit_talents_resume':
        section = 'talents_resume'
    elif query.data == 'edit_final_resume':
        section = 'final_resume'
    elif query.data == 'edit_ok':
        # Удаляем PDF после завершения редактирования
        edit_pdf = context.user_data.get('edit_pdf')
        if edit_pdf and 'input_path' in edit_pdf:
            output_path = os.path.join(os.getcwd(), "downloads", f"{os.path.basename(edit_pdf['input_path']).replace('.pdf', '_out.pdf')}")
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
                    logger.info(f"PDF удалён после завершения редактирования: {output_path}")
            except Exception as e:
                logger.warning(f'Не удалось удалить PDF: {output_path}, ошибка: {e}')
        context.user_data.pop('edit_pdf', None)
        context.user_data.pop('edit_section', None)
        await query.message.reply_text("Редактирование завершено.")
        if query.message.chat.type == Chat.PRIVATE:
            await show_main_menu(update, context)
        await query.answer()
        return
    if section:
        context.user_data['edit_section'] = section
        await query.message.reply_text(f"Отправьте новый текст для раздела '{section}':")
    await query.answer()

async def prompts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(f"Вашему ID {user_id} запрещён доступ. Только для администратора.")
        return
    prompts = load_prompts()
    for key, value in prompts.items():
        text = f"*{key}*:\n{value['template']}"
        # Разбиваем длинные промпты на части по 4000 символов
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000])

async def setprompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(f"Вашему ID {user_id} запрещён доступ. Только для администратора.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Используйте: /setprompt <section>")
        return
    section = context.args[0]
    prompts = load_prompts()
    if section not in prompts:
        await update.message.reply_text(f"Секция '{section}' не найдена.")
        return
    await update.message.reply_text(f"Отправьте новый текст промпта для секции '{section}':")
    context.user_data['setprompt_section'] = section

def get_admin_help_text():
    return (
        "\U0001F6E0 Доступные команды:\n\n"
        "/prompts — показать текущие промпты\n"
        "/setprompt <section> — изменить промпт\n"
        "/resetprompt <section> — сбросить промпт к дефолту\n"
        "\nДля редактирования/сброса промтов используйте <section>: prof_resume — профессиональные склонности, talents_resume — скрытые таланты, final_resume — итоговый вывод \n\n"
        "/cleanfolder — удалить старые и временные файлы досье (ручная очистка)\n\n"
        "/admins — список администраторов\n"
        "/addadmin <user_id> — добавить администратора\n"
        "/removeadmin <user_id> — удалить администратора\n\n"
        "\nДля добавления/удаления администратора используйте user_id, который можно узнать через /myid."
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if text == "Создать досье":
        await update.message.reply_text("Пожалуйста, отправьте PDF файл для обработки.")
        return
    if text == "Команды" and is_admin(user_id):
        await update.message.reply_text(get_admin_help_text())
        return
    edit_pdf = context.user_data.get('edit_pdf')
    section = context.user_data.get('edit_section')
    if edit_pdf and section:
        new_text = update.message.text
        edit_pdf[section] = new_text
        from pdf_processor import create_pdf, get_pdf_output_path
        pdf_data = context.user_data.get('pdf_data')
        output_path = get_pdf_output_path(pdf_data['user_name'])
        create_pdf(output_path, pdf_data, edit_pdf.get('prof_resume'), edit_pdf.get('talents_resume'), edit_pdf.get('final_resume'))
        with open(output_path, 'rb') as output_file:
            if not os.path.exists(output_path):
                await update.message.reply_text("Ошибка: файл не найден для отправки.")
                return
            await update.message.reply_document(document=output_file)
        await update.message.reply_text(f"Раздел '{section}' обновлён и PDF пересоздан.")
        context.user_data.pop('edit_section', None)
        await show_edit_menu(update, context)
        return
    if not is_admin(user_id):
        await update.message.reply_text(f"Вашему ID {user_id} запрещён доступ. Только для администратора.")
        return
    section = context.user_data.get('setprompt_section')
    if section:
        new_text = update.message.text
        prompts = load_prompts()
        prompts[section]['template'] = new_text
        save_prompts(prompts)
        await update.message.reply_text(f"Промпт для секции '{section}' обновлён.")
        context.user_data.pop('setprompt_section', None)
        if update.message.chat.type == Chat.PRIVATE:
            await show_main_menu(update, context)
        return

async def resetprompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(f"Вашему ID {user_id} запрещён доступ. Только для администратора.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Используйте: /resetprompt <section>")
        return
    section = context.args[0]
    default_prompts = reset_prompts()
    if section not in default_prompts:
        await update.message.reply_text(f"Секция '{section}' не найдена в дефолтных промптах.")
        return
    prompts = load_prompts()
    prompts[section]['template'] = default_prompts[section]['template']
    save_prompts(prompts)
    await update.message.reply_text(f"Промпт для секции '{section}' сброшен к значению по умолчанию.")

async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"/admins вызван пользователем {user_id}")
    if not is_admin(user_id):
        await update.message.reply_text(f"Вашему ID {user_id} запрещён доступ. Только для администратора.")
        return
    admins = load_admins()
    text = 'Список администраторов:\n'
    for admin_id in admins:
        try:
            chat = await context.bot.get_chat(admin_id)
            name = chat.full_name or chat.username or str(admin_id)
            username = f"@{chat.username}" if chat.username else ""
        except Exception:
            name = str(admin_id)
            username = ""
        text += f"- {name} (ID: {admin_id}) {username}\n"
    await update.message.reply_text(text)

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ваш user_id: {update.effective_user.id}")

async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(f"Вашему ID {user_id} запрещён доступ. Только для администратора.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Используйте: /addadmin <user_id>")
        return
    try:
        new_admin = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")
        return
    admins = load_admins()
    if new_admin in admins:
        await update.message.reply_text("Этот пользователь уже администратор.")
        return
    admins.append(new_admin)
    save_admins(admins)
    await update.message.reply_text(f"Пользователь {new_admin} добавлен в администраторы.")

async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"/removeadmin вызван пользователем {user_id}")
    if not is_admin(user_id):
        await update.message.reply_text(f"Вашему ID {user_id} запрещён доступ. Только для администратора.")
        return
    if not context.args:
        await update.message.reply_text("Укажите user_id для удаления.")
        return
    try:
        remove_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("user_id должен быть числом.")
        return
    admins = load_admins()
    logger.info(f"Текущий список админов до удаления: {admins}")
    if remove_id not in admins:
        await update.message.reply_text(f"Пользователь {remove_id} не найден в списке администраторов.")
        return
    admins = [a for a in admins if a != remove_id]
    save_admins(admins)
    logger.info(f"Список админов после удаления: {admins}")
    await update.message.reply_text(f"Пользователь {remove_id} удалён из администраторов.")

async def adminpanel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(f"Вашему ID {user_id} запрещён доступ. Только для администратора.")
        return
    keyboard = [[InlineKeyboardButton("Настройки/Команды", callback_data='admin_help')]]
    await update.message.reply_text("Панель администратора:", reply_markup=InlineKeyboardMarkup(keyboard))

async def cleanfolder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text(f"Вашему ID {user_id} запрещён доступ. Только для администратора.")
        return
    deleted = clean_old_files(force=True)
    await update.message.reply_text(f"Удалено файлов: {deleted}")
    logger.info(f"/cleanfolder: удалено файлов {deleted} по запросу {user_id}")

def clean_old_files(force=False):
    now = time.time()
    deleted = 0
    if not os.path.exists(DOWNLOADS_DIR):
        return 0
    for fname in os.listdir(DOWNLOADS_DIR):
        fpath = os.path.join(DOWNLOADS_DIR, fname)
        if os.path.isfile(fpath):
            mtime = os.path.getmtime(fpath)
            if force or (now - mtime > 24*3600):
                try:
                    os.remove(fpath)
                    deleted += 1
                except Exception as e:
                    logger.warning(f"Не удалось удалить {fpath}: {e}")
    return deleted

async def admin_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    logger.info(f"admin_help_callback вызван пользователем {user_id}")
    if not is_admin(user_id):
        await query.answer(f"Вашему ID {user_id} запрещён доступ. Только для администратора.", show_alert=True)
        return
    await query.answer()  # Закрыть спиннер
    await query.message.reply_text(get_admin_help_text())

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не задан!")
        raise Exception("TELEGRAM_BOT_TOKEN не задан!")
    else:
        logger.info("Получен токен: %s...", token[:2])

    application = ApplicationBuilder().token(token).build()
    application.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    # Сначала обработчики с pattern!
    application.add_handler(CallbackQueryHandler(admin_help_callback, pattern="^admin_help$"))
    application.add_handler(CallbackQueryHandler(edit_resume_callback, pattern='^edit_'))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("prompts", prompts_command))
    application.add_handler(CommandHandler("setprompt", setprompt_command))
    application.add_handler(CommandHandler("resetprompt", resetprompt_command))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CommandHandler("admins", admins_command))
    application.add_handler(CommandHandler("addadmin", addadmin_command))
    application.add_handler(CommandHandler("removeadmin", removeadmin_command))
    application.add_handler(CommandHandler("adminpanel", adminpanel_command))
    application.add_handler(CommandHandler("cleanfolder", cleanfolder_command))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_text))
    application.run_polling(close_loop=False)

    # Запуск периодической очистки
    import threading
    def periodic_clean():
        while True:
            deleted = clean_old_files()
            if deleted:
                logger.info(f"Периодическая очистка: удалено файлов {deleted}")
            time.sleep(24*3600)  # Гарантируем, что очистка не чаще раза в сутки
    threading.Thread(target=periodic_clean, daemon=True).start()

if __name__ == "__main__":
    main()
