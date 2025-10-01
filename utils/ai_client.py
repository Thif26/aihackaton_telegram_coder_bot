import requests
import os
import logging
from typing import Optional
import json

logger = logging.getLogger(__name__)

class AIClient:
    def __init__(self):
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "mistralai/mistral-small-3.2-24b-instruct:free"
        self.api_key = self._get_api_key()
    
    def _get_api_key(self):
        """Получение API ключа из переменных окружения"""
        api_key = os.getenv('OPENROUTER_API_KEY')
        
        if not api_key:
            logger.error("OPENROUTER_API_KEY не найден в переменных окружения")
            raise ValueError(
                "OPENROUTER_API_KEY не настроен. "
                "Добавьте ключ в переменные окружения или создайте файл .env"
            )
        
        logger.info("API ключ успешно загружен")
        return api_key

    def generate_code(self, task_description: str) -> Optional[str]:
        """Генерация кода через OpenRouter API"""
        
        if not self.api_key:
            logger.error("API ключ не настроен")
            return None
        
        prompt = f"""
        Ты опытный фронтенд-разработчик. Сгенерируй чистый, валидный HTML/CSS/JS код.
        
        ТЗ: {task_description}
        
        Требования к коду:
        - Современный HTML5 с семантической разметкой
        - CSS3 с Flexbox/Grid, адаптивный дизайн
        - Минимальный JavaScript только по необходимости
        - Красивый современный UI
        - Mobile-friendly верстка
        
        Верни ТОЛЬКО готовый HTML файл с CSS внутри <style> и JS внутри <script>.
        Не добавляй пояснения, комментарии или markdown разметку.
        """
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com",
            "X-Title": "AI Code Generator"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 4000,
            "temperature": 0.7,
            "top_p": 0.9,
        }
        
        try:
            logger.info("Отправляем запрос к AI...")
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=120)
            
            logger.info(f"Статус ответа: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info("Ответ получен успешно")
                
                if 'choices' in result and len(result['choices']) > 0:
                    content = result['choices'][0]['message']['content']
                    logger.info(f"Длина ответа: {len(content)} символов")
                    
                    # Очистка вывода
                    cleaned_code = self._clean_ai_output(content)
                    return cleaned_code
                else:
                    logger.error("Неожиданный формат ответа от API")
                    logger.debug(f"Полный ответ: {json.dumps(result, indent=2)}")
                    return None
                    
            else:
                error_msg = f"Ошибка API: {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - {response.text}"
                
                logger.error(error_msg)
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Таймаут запроса к AI API (120 секунд)")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Ошибка соединения с API")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return None
    
    def _clean_ai_output(self, text: str) -> str:
        """Очистка вывода AI от лишних элементов"""
        if not text:
            return ""
            
        # Удаляем markdown коды
        if '```html' in text:
            text = text.split('```html')[1].split('```')[0]
        elif '```' in text:
            parts = text.split('```')
            if len(parts) >= 2:
                text = parts[1]  # Берем содержимое между первыми ```
        
        # Удаляем пояснения до начала кода
        lines = text.split('\n')
        code_lines = []
        code_started = False
        
        for line in lines:
            # Ищем начало HTML кода
            if any(tag in line.lower() for tag in ['<!doctype', '<html', '<!DOCTYPE']):
                code_started = True
            
            if code_started or line.strip().startswith('<'):
                code_lines.append(line)
        
        result = '\n'.join(code_lines).strip()
        
        # Если после очистки пусто, возвращаем оригинал
        return result if result else text