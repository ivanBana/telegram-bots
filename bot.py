# --- БЛОК 1: ВСЕ ИМПОРТЫ ---
import logging
import os
import time  
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
logging.basicConfig( format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
TELEGRAM_LIMIT_BYTES = 50 * 1024 * 1024


# --- БЛОК 3: ОБРАБОТЧИКИ КОМАНД ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я — твой персональный бот для скачивания видео. Я могу загружать ролики с большинства популярных платформ.\n\n"
        "**Как это работает:**\n"
        "1. Ты отправляешь мне ссылку на видео.\n"
        "2. Я предлагаю тебе варианты: скачать видео в разном качестве или только аудио (MP3).\n"
        "3. Если размер файла не превышает **50 МБ**, я отправляю его тебе прямо в этот чат.\n\n"
        "**ВАЖНО:** Скачивание с YouTube/VK может быть нестабильно из-за проблем у хостинга.\n\n"
        "Просто вставь ссылку и нажми 'Отправить'!"
    )
    await context.bot.send_message( chat_id=update.effective_chat.id, text=welcome_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    url = update.message.text
    context.user_data['url'] = url
    message = await context.bot.send_message(chat_id=chat_id, text="🔎 Принял ссылку! Ищу доступные форматы...")

    try:
        ydl_opts = { 'quiet': True, 'force_ipv4': True, 'no_check_certificate': True }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        keyboard = []
        formats = info.get('formats', [])
        
        # Сначала ищем идеальные mp4
        for f in formats:
            if (f.get('vcodec') != 'none' and f.get('acodec') != 'none' and
                f.get('ext') == 'mp4' and f.get('filesize') and
                f.get('filesize') < TELEGRAM_LIMIT_BYTES):
                label = f"📹 {f.get('height', '?')}p MP4 ({f['filesize'] / 1024 / 1024:.1f} МБ)"
                keyboard.append([InlineKeyboardButton(label, callback_data=f"v:{f['format_id']}")])

        if not keyboard:
             for f in formats:
                if (f.get('vcodec') != 'none' and f.get('acodec') != 'none' and
                    f.get('filesize') and f.get('filesize') < TELEGRAM_LIMIT_BYTES):
                    label = f"📹 {f.get('height', '?')}p {f.get('ext','?')} ({f['filesize'] / 1024 / 1024:.1f} МБ)"
                    keyboard.append([InlineKeyboardButton(label, callback_data=f"v:{f['format_id']}+merge_mp4")])

        best_audio = next((f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none'), None)
        if best_audio and best_audio.get('filesize') and best_audio.get('filesize') < TELEGRAM_LIMIT_BYTES:
            label = f"🎵 MP3 ({best_audio['filesize'] / 1024 / 1024:.1f} МБ)"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"a:{best_audio['format_id']}")])

        if not keyboard:
            error_text = "Не нашел подходящих форматов (< 50 МБ)."
            if "youtube.com" in url or "youtu.be" in url or "vk.com" in url:
                 error_text += "\n\n(Скачивание с YouTube/VK временно недоступно из-за проблем у хостинга)."
            elif "tiktok.com" in url:
                 error_text += "\n\n(TikTok блокирует IP-адрес сервера)."
            await message.edit_text(error_text)
            return

        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.edit_text(f"Выбери формат для скачивания видео '{info.get('title', 'Без названия')}':", reply_markup=reply_markup)

    except Exception as e:
        error_text = f"Произошла ошибка при обработке ссылки: {e}"
        if "youtube.com" in url or "youtu.be" in url or "vk.com" in url:
             error_text += "\n\n(Скачивание с YouTube/VK временно недоступно из-за проблем у хостинга)."
        elif "tiktok.com" in url:
             error_text += "\n\n(TikTok блокирует IP-адрес сервера)."
        elif isinstance(e, yt_dlp.utils.DownloadError):
             error_text = f"Не удалось получить информацию с сайта. Возможно, ссылка неверна или сайт не поддерживается."
        await message.edit_text(error_text)
        logging.error(f"Ошибка обработки ссылки {url}: {e}")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки."""
    query = update.callback_query
    await query.answer()
    
    # 1. Создаём уникальную базу для имени файла
    user_id = query.effective_user.id
    timestamp = int(time.time())
    unique_filename_base = f"{user_id}_{timestamp}"

    callback_data = query.data
    url = context.user_data.get('url')

    if not url:
        await query.edit_message_text("Ошибка: не могу найти оригинальную ссылку. Пожалуйста, отправьте ее заново.")
        return

    await query.edit_message_text("Отлично! Начинаю скачивание...")

    merge_needed = False
    if callback_data.endswith('+merge_mp4'):
        merge_needed = True
        callback_data = callback_data.replace('+merge_mp4', '') 

    file_type, format_id = callback_data.split(':')
    file_path = "" 

    try:
        if file_type == 'v': 
            # Используем уникальное имя
            file_path = f'{unique_filename_base}.mp4' 
            ydl_opts = {
                'format': format_id, 
                'outtmpl': f'{unique_filename_base}.%(ext)s', # Используем уникальное имя
                'force_ipv4': True,
                'no_check_certificate': True,
            }
            if merge_needed:
                 ydl_opts['merge_output_format'] = 'mp4'

        else: # Аудио
            # Используем уникальное имя
            file_path = f'{unique_filename_base}.mp3'
            ydl_opts = {
                'format': format_id,
                'outtmpl': f'{unique_filename_base}.%(ext)s', # Используем уникальное имя
                'force_ipv4': True,
                'no_check_certificate': True,
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
            # Умное определение имени файла (на всякий случай)
            downloaded_file = ydl.prepare_filename(ydl.extract_info(url, download=False))
            
            if file_type == 'v':
                if merge_needed and not downloaded_file.endswith('.mp4'):
                     potential_mp4_path = downloaded_file.rsplit('.', 1)[0] + '.mp4'
                     if os.path.exists(potential_mp4_path):
                         file_path = potential_mp4_path
                     elif os.path.exists(f'{unique_filename_base}.mp4'):
                         file_path = f'{unique_filename_base}.mp4'
                     else: 
                         file_path = downloaded_file
                elif os.path.exists(f'{unique_filename_base}.mp4'):
                    file_path = f'{unique_filename_base}.mp4'
                else:
                    file_path = downloaded_file.rsplit('.', 1)[0] + '.mp4'
            
            elif file_type == 'a': 
                 file_path = downloaded_file.replace('.webm', '.mp3').replace('.m4a', '.mp3')
                 # Если имя всё равно не то, берём наше
                 if not os.path.exists(file_path):
                     file_path = f'{unique_filename_base}.mp3'


        await query.edit_message_text("Загрузка завершена! Отправляю файл...")
        with open(file_path, 'rb') as f:
            if file_type == 'v':
                await context.bot.send_video(chat_id=query.message.chat_id, video=f, supports_streaming=True)
            else:
                await context.bot.send_audio(chat_id=query.message.chat_id, audio=f)

        if os.path.exists(file_path): os.remove(file_path) 
        await query.edit_message_text("Готово! Можешь присылать следующую ссылку.")

    except Exception as e:
        # Удаляем мусорные файлы, если они остались
        if os.path.exists(f'{unique_filename_base}.mp4'): os.remove(f'{unique_filename_base}.mp4')
        if os.path.exists(f'{unique_filename_base}.mp3'): os.remove(f'{unique_filename_base}.mp3')
        
        await query.edit_message_text(f"Произошла ошибка при скачивании: {e}")
        logging.error(f"Ошибка скачивания для {url} с форматом {format_id}: {e}")


# --- БЛОК 4: ЗАПУСК ---
if __name__ == '__main__':
    application = ApplicationBuilder().token(YT_BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Бот v1.5 запущен...")
    application.run_polling()

"""
---
Dedicatum D. U
---
"""
