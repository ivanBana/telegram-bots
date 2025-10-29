
# --- БЛОК 1: ВСЕ ИМПОРТЫ ---
import logging
import os
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

from config import YT_BOT_TOKEN


# --- БЛОК 2: НАСТРОЙКИ ---

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Лимит размера файла в байтах (Telegram Bot API - 50 MB)
TELEGRAM_LIMIT_BYTES = 50 * 1024 * 1024


# --- БЛОК 3: ОБРАБОТЧИКИ КОМАНД ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я — твой персональный бот для скачивания видео. Я могу загружать ролики с большинства популярных платформ, таких как **YouTube, VK, RuTube** и многих других.\n\n"     
        "**Как это работает:**\n"
        "1. Ты отправляешь мне ссылку на видео.\n"
        "2. Я предлагаю тебе варианты: скачать видео в разном качестве или только аудио (MP3).\n"
        "3. Если размер файла не превышает **50 МБ**, я отправляю его тебе прямо в этот чат.\n\n"
        "Просто вставь ссылку и нажми 'Отправить'!"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=welcome_text,
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает ссылку от пользователя и предлагает варианты для скачивания."""
    chat_id = update.effective_chat.id
    url = update.message.text

    context.user_data['url'] = url

    message = await context.bot.send_message(chat_id=chat_id, text="🔎 Принял ссылку! Ищу доступные форматы...")

    try:
        ydl_opts = {'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        keyboard = []
        # --- Создаем кнопки для видео ---
        for f in info.get('formats', []):
            if (
                f.get('vcodec') != 'none' and f.get('acodec') != 'none'
                and f.get('ext') == 'mp4'
                and f.get('filesize') and f.get('filesize') < TELEGRAM_LIMIT_BYTES
            ):
                label = f"📹 {f['height']}p ({f['filesize'] / 1024 / 1024:.1f} МБ)"
                keyboard.append([InlineKeyboardButton(label, callback_data=f"v:{f['format_id']}")])

        # --- Создаем кнопку для аудио (MP3) ---
        best_audio = next((f for f in info.get('formats', []) if f.get('acodec') != 'none' and f.get('vcodec') == 'none'), None)
        if best_audio and best_audio.get('filesize') and best_audio.get('filesize') < TELEGRAM_LIMIT_BYTES:
            label = f"🎵 MP3 ({best_audio['filesize'] / 1024 / 1024:.1f} МБ)"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"a:{best_audio['format_id']}")])

        if not keyboard:
            await message.edit_text("Не нашел подходящих форматов для скачивания (меньше 50 МБ).")
            return

        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.edit_text(f"Выбери формат для скачивания видео '{info['title']}':", reply_markup=reply_markup)

    except Exception as e:
        await message.edit_text(f"Произошла ошибка при обработке ссылки: {e}")
        logging.error(f"Ошибка обработки ссылки {url}: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    url = context.user_data.get('url')

    if not url:
        await query.edit_message_text("Ошибка: не могу найти оригинальную ссылку. Пожалуйста, отправьте ее заново.")
        return

    await query.edit_message_text("Отлично! Начинаю скачивание...")

    file_type, format_id = callback_data.split(':')
    file_path = "" # Создаем пустую переменную для пути

    try:
        if file_type == 'v': # Если выбрали видео
            file_path = 'video_for_telegram.mp4'
            ydl_opts = {
                # --- !! ВРЕМЕННЫЙ ФИКС ДЛЯ ОШИБКИ 403 !! ---
                'format': format_id,
                'outtmpl': 'video_for_telegram.%(ext)s',
            }
        else: # Если выбрали аудио
            file_path = 'audio_for_telegram.mp3'
            ydl_opts = {
                'format': format_id,
                'outtmpl': 'audio_for_telegram.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await query.edit_message_text("Загрузка завершена! Отправляю файл...")

        with open(file_path, 'rb') as f:
            if file_type == 'v':
                await context.bot.send_video(chat_id=query.message.chat_id, video=f, supports_streaming=True)
            else:
                await context.bot.send_audio(chat_id=query.message.chat.id, audio=f)

        os.remove(file_path)
        await query.edit_message_text("Готово! Можешь присылать следующую ссылку.")

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        await query.edit_message_text(f"Произошла ошибка при скачивании: {e}")
        logging.error(f"Ошибка скачивания для {url} с форматом {format_id}: {e}")


# --- БЛОК 4: ЗАПУСК ---

if __name__ == '__main__':
    # Используем наш токен из "сейфа"
    application = ApplicationBuilder().token(YT_BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Бот v2.2 (чистая установка) запущен...")
    application.run_polling()
