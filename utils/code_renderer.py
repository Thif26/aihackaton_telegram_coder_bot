import re
from typing import Optional

class CodeRenderer:
    def prepare_html(self, raw_code: str) -> str:
        """Подготовка HTML для рендеринга с улучшенной обработкой"""
        
        if not raw_code:
            return self._get_fallback_html()
        
        # Очищаем код от возможных артефактов
        cleaned_code = self._clean_html_code(raw_code)
        
        # Проверяем, есть ли полная HTML структура
        has_doctype = '<!DOCTYPE' in cleaned_code.upper()
        has_html = '<html' in cleaned_code.lower()
        has_body = '<body' in cleaned_code.lower()
        
        if has_doctype and has_html and has_body:
            # Это полный HTML документ
            return cleaned_code
        else:
            # Добавляем базовую структуру
            return self._wrap_in_html_template(cleaned_code)
    
    def _clean_html_code(self, code: str) -> str:
        """Очистка HTML кода от common issues"""
        # Удаляем лишние backticks
        code = re.sub(r'^```html\s*|\s*```$', '', code, flags=re.IGNORECASE)
        code = re.sub(r'^```\s*|\s*```$', '', code)
        
        # Удаляем markdown заголовки
        code = re.sub(r'^#+\s*.+$', '', code, flags=re.MULTILINE)
        
        return code.strip()
    
    def _wrap_in_html_template(self, content: str) -> str:
        """Обертывание контента в полную HTML структуру"""
        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>AI Generated Code</title>
            <style>
                /* Базовые стили для обеспечения читаемости */
                body {{
                    margin: 0;
                    padding: 20px;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    box-sizing: border-box;
                }}
                * {{
                    box-sizing: border-box;
                }}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """
    
    def _get_fallback_html(self) -> str:
        """HTML для случая, когда код не сгенерировался"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Ошибка генерации</title>
            <style>
                body { 
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    background: #f0f0f0;
                    font-family: Arial, sans-serif;
                }
                .error { 
                    background: white;
                    padding: 2rem;
                    border-radius: 10px;
                    text-align: center;
                }
            </style>
        </head>
        <body>
            <div class="error">
                <h2>❌ Не удалось сгенерировать код</h2>
                <p>Попробуйте перегенерировать или изменить описание задачи</p>
            </div>
        </body>
        </html>
        """
    
    def validate_html(self, html: str) -> bool:
        """Базовая валидация HTML"""
        return bool(html and len(html) > 50)  # Простая проверка на минимальную длину