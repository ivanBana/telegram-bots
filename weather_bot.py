import logging
import requests
import google.generativeai as genai
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# Импортируем ключи из config.py
try:
    from config import WEATHER_BOT_TOKEN, WEATHER_API_KEY, GEMINI_API_KEY
except ImportError:
    print("Ошибка: не могу найти файл config.py!")
    print("Создай config.py и добавь в него: WEATHER_BOT_TOKEN, WEATHER_API_KEY, GEMINI_API_KEY")
    exit()

# --- БЛОК 1: НАСТРОЙКИ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Конфигурируем Gemini сразу при старте
try:
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Вставляем рабочую модель из списка
    gemini_model = genai.GenerativeModel('models/gemini-2.5-flash') 
    
    logging.info(f"Gemini API успешно сконфигурирован с моделью {gemini_model.model_name}.")
except Exception as e:
    logging.error(f"Ошибка конфигурации Gemini API: {e}")
    gemini_model = None

# --- БЛОК 2: ЛОГИКА GEMINI И ПОГОДЫ ---

def get_gemini_forecast(weather_data_json: dict) -> str:
    """
    Берет сырые данные о погоде (JSON) и генерирует живой прогноз.
    """
    if not gemini_model:
        logging.warning("Модель Gemini недоступна. Возвращаем стандартный ответ.")
        return None

    logging.info("Отправка запроса в Gemini...")
    
    prompt = (
        "Ты — дружелюбный и немного остроумный AI-синоптик, который отвечает пользователю в личном чате."
        "Твоя задача — написать короткий (3-4 предложения) и живой прогноз погоды на русском языке."
        "Не используй Markdown или форматирование."
        "Основывайся на этих СЫРЫХ ДАННЫХ в формате JSON от OpenWeatherMap:\n"
        f"{weather_data_json}\n\n"
        "Твой прогноз (например: 'Привет! В этом городе сегодня...'):"
    )

    try:
        response = gemini_model.generate_content(prompt)
        logging.info("Ответ от Gemini получен.")
        return response.text
    except Exception as e:
        logging.error(f"Ошибка при обращении к Gemini API: {e}")
        return None 

# --- БЛОК 3: ОБРАБОТЧИКИ КОМАНД TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я — твой персональный AI-синоптик.\n"
        "Просто напиши мне название любого города (например, 'Лондон' или 'Токио'), "
        "а я запрошу данные о погоде и попрошу Gemini дать живой комментарий."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city_name = update.message.text
    chat_id = update.effective_chat.id

    message = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔎 Ищу погоду для города: '{city_name}'..."
    )

    # 1. Получаем погоду
    weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=ru"

    try:
        response = requests.get(weather_url)
        response.raise_for_status() 
        data = response.json()

        await message.edit_text("✅ Погода найдена! Отправляю запрос в Gemini для анализа...")

        # 2. Получаем "умный" прогноз от Gemini
        gemini_text = get_gemini_forecast(data)

        if gemini_text:
            final_text = f"**{data['name']}** 🌦\n\n{gemini_text}"
        else:
            logging.warning("Gemini не ответил, используем старый шаблон.")
            temp = data['main']['temp']
            feels_like = data['main']['feels_like']
            description = data['weather'][0]['description'].capitalize()
            
            final_text = (
                f"**{data['name']} (стандартный отчет)** 🌦\n\n"
                f"**Сейчас:** {temp:.1f}°C (ощущается как {feels_like:.1f}°C)\n"
                f"**На небе:** {description}"
            )
        
        await message.edit_text(final_text, parse_mode='Markdown')

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            await message.edit_text(f"Упс! 😥 Не могу найти город с названием '{city_name}'. Попробуй написать его по-английски или проверь орфографию.")
        else:
            await message.edit_text(f"Ошибка при запросе к API погоды: {e}")
    except Exception as e:
        await message.edit_text(f"Произошла непредвиденная ошибка: {e}")


# --- БЛОК 4: ЗАПУСК ---
if __name__ == '__main__':
    if not all([WEATHER_BOT_TOKEN, WEATHER_API_KEY, GEMINI_API_KEY]):
        logging.critical("КЛЮЧИ API НЕ НАЙДЕНЫ в config.py!")
        exit()

    application = ApplicationBuilder().token(WEATHER_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("AI-Синоптик (v1.0) запущен...")
    application.run_polling()
