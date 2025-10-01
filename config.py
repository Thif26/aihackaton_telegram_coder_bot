import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# API ключи
bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')  # Новый ключ для OpenRouter
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "mistralai/mistral-small-3.2-24b-instruct:free"  # Horizon Alpha модель
PEXELS_API_KEY  = "mroGYlKSXFeJAbyY63elvILeCWKOOOPlL20m5eqtqerzD8xbObLVy9p2"
# Настройки заголовков для OpenRouter (для рейтингов на openrouter.ai)
OPENROUTER_REFERER = "https://github.com/your-username/chronobot"  # Замените на ваш URL
OPENROUTER_TITLE = "ChronoBot - Historical Video Generator"  # Название вашего проекта
