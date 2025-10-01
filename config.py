import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# API ключи
bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY') 
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "mistralai/mistral-small-3.2-24b-instruct:free"  
OPENROUTER_REFERER = "https://github.com/your-username/chronobot" 

