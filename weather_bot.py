import requests
import telegram
import asyncio # Добавил asyncio

CITY = "Moscow,RU" # Можно поменять на свой город, например "Saint Petersburg,RU"

async def main(): # Сделал функцию асинхронной
    print("Запуск скрипта погоды...")
    # 1. Получаем погоду
    weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={WEATHER_API_KEY}&units=metric&lang=ru"

    try:
        response = requests.get(weather_url)
        response.raise_for_status()
        data = response.json()

        # 2. Форматируем красивое сообщение
        temp = data['main']['temp']
        feels_like = data['main']['feels_like']
        description = data['weather'][0]['description'].capitalize()
        wind = data['wind']['speed']

        text = f"🌦 **Погода (Москва)**\n\n"
        text += f"**Сейчас:** {temp:.1f}°C (ощущается как {feels_like:.1f}°C)\n"
        text += f"**На небе:** {description}\n"
        text += f"**Ветер:** {wind:.1f} м/с"

        # 3. Отправляем в Telegram
        bot = telegram.Bot(token=WEATHER_BOT_TOKEN)
        # !! ГЛАВНОЕ ИСПРАВЛЕНИЕ - ДОБАВИЛ 'await' !!
        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode='Markdown')

        print(f"Сообщение о погоде успешно отправлено в {CHANNEL_ID}")

    except requests.exceptions.HTTPError as e:
        print(f"Ошибка HTTP при запросе к API погоды: {e}")
        print(f"Ответ сервера: {e.response.text}")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")

if __name__ == "__main__":
    # Запускаем асинхронную функцию
    asyncio.run(main()
