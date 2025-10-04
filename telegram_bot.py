
import os
import logging
import tempfile
import json
import csv
from datetime import datetime
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Импорт утилит
try:
    from utils.excel_parser import ExcelParser
    from utils.ai_client import AIClient
    from utils.code_renderer import CodeRenderer
except ImportError:
    # Для случая, когда запускаем из корня проекта
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from utils.excel_parser import ExcelParser
    from utils.ai_client import AIClient
    from utils.code_renderer import CodeRenderer

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        
        # Создаем директории для сохранения файлов
        self.setup_directories()
        
        # Инициализация утилит
        try:
            self.ai_client = AIClient()
            self.excel_parser = ExcelParser()
            self.code_renderer = CodeRenderer()
            logger.info("Утилиты успешно инициализированы")
        except Exception as e:
            logger.error(f"Ошибка инициализации утилит: {e}")
            raise
        
        # Хранилище данных пользователей
        self.user_data: Dict[int, Dict] = {}
        
        # Регистрация обработчиков
        self.setup_handlers()
    
    def setup_directories(self):
        """Создание необходимых директорий для сохранения файлов"""
        self.base_save_dir = "generated_codes"
        self.users_dir = os.path.join(self.base_save_dir, "users")
        self.logs_dir = os.path.join(self.base_save_dir, "logs")
        
        os.makedirs(self.users_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        
        logger.info(f"Директории созданы: {self.base_save_dir}")
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        # Обработчики callback кнопок - ДОЛЖЕН БЫТЬ ПЕРВЫМ!
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Базовые команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("clear", self.clear_command))
        
        # Обработчики сообщений
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
        logger.info("Обработчики команд настроены")
    
    def get_user_data(self, user_id: int) -> Dict:
        """Получение данных пользователя"""
        if user_id not in self.user_data:
            self.user_data[user_id] = {
                'excel_tasks': [],
                'text_tasks': [],
                'generated_codes': {},
                'html_contents': {},
                'current_task': None,
                'state': 'idle',
                'last_message_id': None,
                'task_documents': {},
                'keyboard_message_id': None,
                'last_keyboard_text': None,
                'last_keyboard_markup': None,
                'previous_messages': []  # Храним ID предыдущих сообщений для удаления
            }
        return self.user_data[user_id]
    
    async def cleanup_previous_messages(self, context: ContextTypes.DEFAULT_TYPE, user_id: int, keep_keyboard: bool = False):
        """Удаление предыдущих сообщений бота"""
        user_data = self.get_user_data(user_id)
        
        messages_to_delete = []
        
        # Добавляем все предыдущие сообщения кроме клавиатуры (если нужно сохранить)
        for msg_id in user_data.get('previous_messages', []):
            if keep_keyboard and msg_id == user_data.get('keyboard_message_id'):
                continue
            messages_to_delete.append(msg_id)
        
        # Удаляем сообщения
        for msg_id in messages_to_delete:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=msg_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")
        
        # Обновляем список предыдущих сообщений
        if keep_keyboard and user_data.get('keyboard_message_id'):
            user_data['previous_messages'] = [user_data['keyboard_message_id']]
        else:
            user_data['previous_messages'] = []
            user_data['keyboard_message_id'] = None
    
    def save_user_info(self, user_id: int, username: str, first_name: str, last_name: str = ""):
        """Сохранение информации о пользователе"""
        user_file = os.path.join(self.users_dir, f"user_{user_id}.json")
        user_info = {
            'user_id': user_id,
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'first_seen': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat()
        }
        
        # Если файл уже существует, обновляем только last_activity
        if os.path.exists(user_file):
            with open(user_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                user_info['first_seen'] = existing_data.get('first_seen', user_info['first_seen'])
        
        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(user_info, f, ensure_ascii=False, indent=2)
    
    def log_activity(self, user_id: int, action: str, task_id: str = "", task_description: str = ""):
        """Логирование активности пользователя"""
        log_file = os.path.join(self.logs_dir, f"activity_{datetime.now().strftime('%Y-%m-%d')}.csv")
        file_exists = os.path.isfile(log_file)
        
        with open(log_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['timestamp', 'user_id', 'action', 'task_id', 'task_description'])
            
            writer.writerow([
                datetime.now().isoformat(),
                user_id,
                action,
                task_id,
                task_description[:100]  # Ограничиваем длину описания
            ])
    
    def save_generated_code(self, user_id: int, task: Dict, html_content: str, generated_code: str):
        """Сохранение сгенерированного кода в файл"""
        user_codes_dir = os.path.join(self.users_dir, f"user_{user_id}", "codes")
        os.makedirs(user_codes_dir, exist_ok=True)
        
        # Сохраняем HTML файл
        html_filename = f"task_{task['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        html_filepath = os.path.join(user_codes_dir, html_filename)
        
        with open(html_filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Сохраняем метаданные
        metadata = {
            'task_id': task['id'],
            'task_description': task.get('description', ''),
            'task_summary': task.get('summary', ''),
            'task_type': task.get('type', 'unknown'),
            'generated_at': datetime.now().isoformat(),
            'html_file': html_filename,
            'user_id': user_id
        }
        
        metadata_filename = f"task_{task['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        metadata_filepath = os.path.join(user_codes_dir, metadata_filename)
        
        with open(metadata_filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Код сохранен для пользователя {user_id}, задача {task['id']}")
        return html_filepath, metadata_filepath
    
    async def update_keyboard_message(self, context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str = None, reply_markup=None):
        """Обновляет или создает сообщение с постоянной клавиатурой"""
        user_data = self.get_user_data(user_id)
        
        # Если текст не указан, используем стандартный
        if text is None:
            text = "💡 Выберите действие:"
        
        # Проверяем, изменились ли текст или клавиатура
        current_text = user_data.get('last_keyboard_text')
        current_markup = user_data.get('last_keyboard_markup')
        
        # Сравниваем текст и разметку
        text_changed = current_text != text
        markup_changed = str(current_markup) != str(reply_markup) if current_markup else True
        
        # Если у нас уже есть сообщение с клавиатурой и что-то изменилось, обновляем его
        if user_data.get('keyboard_message_id') and (text_changed or markup_changed):
            try:
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user_data['keyboard_message_id'],
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                # Сохраняем текущее состояние
                user_data['last_keyboard_text'] = text
                user_data['last_keyboard_markup'] = reply_markup
                return
            except Exception as e:
                # Игнорируем ошибку "Message is not modified"
                if "Message is not modified" in str(e):
                    logger.debug("Сообщение с клавиатурой не изменилось, пропускаем обновление")
                    return
                logger.warning(f"Не удалось обновить сообщение с клавиатурой: {e}")
                # Если не удалось обновить, создаем новое
        
        # Если сообщения нет или не удалось обновить, создаем новое
        message = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Сохраняем ID сообщения с клавиатурой и текущее состояние
        user_data['keyboard_message_id'] = message.message_id
        user_data['last_keyboard_text'] = text
        user_data['last_keyboard_markup'] = reply_markup
        
        # Добавляем в список для возможного удаления
        user_data['previous_messages'].append(message.message_id)
    
    async def send_temporary_message(self, context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str, parse_mode=None):
        """Отправляет временное сообщение без клавиатуры"""
        message = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=parse_mode
        )
        
        # Сохраняем ID для возможного удаления
        user_data = self.get_user_data(user_id)
        user_data['previous_messages'].append(message.message_id)
        
        return message
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user = update.effective_user
        
        # Очищаем предыдущие сообщения
        await self.cleanup_previous_messages(context, user_id)
        
        # Сохраняем информацию о пользователе
        self.save_user_info(
            user_id=user_id,
            username=user.username or "",
            first_name=user.first_name or "",
            last_name=user.last_name or ""
        )
        
        # Логируем действие
        self.log_activity(user_id, "start_bot")
        
        user_data = self.get_user_data(user_id)
        
        welcome_text = """
🚀 **Добро пожаловать в AI Code Generator Bot!**

Я помогу вам создавать крутые интерактивные проекты:

🎯 **Готовые примеры:**
• 🐱 Сайт-портфолио для IT-кота
• 🗺️ Интерактивная карта сокровищ  
• 🎮 Игра: Убеги от тимлида"
• 😂 Генератор мемов на дейлик

**Как использовать:**
1. Выберите пример ниже или опишите свою идее
2. Получите готовый HTML/CSS/JS код
3. Скачайте файл и используйте!

**Просто напишите описание или выберите пример:**
        """
        
        # Отправляем приветственное сообщение
        await self.send_temporary_message(
            context, user_id, welcome_text, 
            parse_mode='Markdown'
        )
        
        # Обновляем клавиатуру с примерами
        await self.update_examples_keyboard(context, user_id)
        
        logger.info(f"Пользователь {user_id} запустил бота")
    
    async def update_examples_keyboard(self, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        """Обновляет клавиатуру с примерами"""
        keyboard = [
            [InlineKeyboardButton("🐱 Портфолио кота", callback_data="example_cat")],
            [InlineKeyboardButton("🗺️ Карта сокровищ", callback_data="example_treasure")],
            [InlineKeyboardButton("🎮 Убеги от динозавра", callback_data="example_dinosaur")],
            [InlineKeyboardButton("😂 Генератор мемов", callback_data="example_memes")],
            [InlineKeyboardButton("📝 Свой вариант", callback_data="text_input")],
            [InlineKeyboardButton("📖 Справка", callback_data="help")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self.update_keyboard_message(
            context, user_id,
            "🎯 Выберите пример или действие:",
            reply_markup=reply_markup
        )
    
    async def update_main_keyboard(self, context: ContextTypes.DEFAULT_TYPE, user_id: int, task: Dict = None):
        """Обновляет основную клавиатуру управления"""
        user_data = self.get_user_data(user_id)
        
        keyboard = []
        
        # Если есть текущая задача, добавляем кнопки для работы с ней
        if task and task['id'] in user_data['generated_codes']:
            keyboard.append([InlineKeyboardButton("🔄 Перегенерировать код", callback_data="regenerate")])
        
        # Кнопки для навигации по задачам
        switch_buttons = []
        
        # Добавляем кнопки для переключения между задачами
        for i, excel_task in enumerate(user_data['excel_tasks']):
            if excel_task['id'] in user_data['generated_codes']:
                switch_buttons.append(
                    InlineKeyboardButton(
                        f"📊 {excel_task['summary'][:15]}...", 
                        callback_data=f"switch_task_excel_{i}"
                    )
                )
        
        for i, text_task in enumerate(user_data['text_tasks']):
            if text_task['id'] in user_data['generated_codes']:
                switch_buttons.append(
                    InlineKeyboardButton(
                        f"📝 {text_task['summary'][:15]}...", 
                        callback_data=f"switch_task_text_{i}"
                    )
                )
        
        # Добавляем кнопки переключения (максимум 2 в ряд)
        if switch_buttons:
            keyboard.append([InlineKeyboardButton("🔀 Переключиться на задачу:", callback_data="no_action")])
            for i in range(0, len(switch_buttons), 2):
                row = switch_buttons[i:i+2]
                keyboard.append(row)
        
        # Основные кнопки управления
        keyboard.extend([
            [InlineKeyboardButton("📋 Показать все задачи", callback_data="task_list")],
            [
                InlineKeyboardButton("📝 Новая задача", callback_data="new_task"),
                InlineKeyboardButton("📖 Справка", callback_data="help")
            ],
            [InlineKeyboardButton("🗑️ Очистить историю", callback_data="clear")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Текст для клавиатуры
        if task:
            text = f"📋 **Текущая задача:** {task['summary']}\n\n💡 Выберите действие:"
        else:
            total_tasks = len(user_data['excel_tasks']) + len(user_data['text_tasks'])
            generated_tasks = len(user_data['generated_codes'])
            text = f"📊 **Статистика:** {generated_tasks}/{total_tasks} задач сгенерировано\n\n💡 Выберите действие:"
        
        await self.update_keyboard_message(
            context, user_id,
            text,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        user_id = update.effective_user.id
        
        # Очищаем предыдущие сообщения, но сохраняем клавиатуру
        await self.cleanup_previous_messages(context, user_id, keep_keyboard=True)
        
        # Логируем действие
        self.log_activity(user_id, "help_command")
        
        help_text = """
📖 **Справка по использованию бота**

**Формат Excel файла:**
Файл должен содержать колонки:
- "Хочу" - основное описание
- "Чтобы" - цель/результат  
- "Критерии приемки" - требования
- "Комментарии" - дополнительные замечания

**Текстовые запросы:**
Просто опишите что нужно создать. Пример:
"Создай модальное окно с затемнением фоном и анимацией появления"

**Управление задачами:**
- Используйте кнопки для переключения между задачами
- Каждая новая задача добавляется в список
- Можно вернуться к любой предыдущей задаче

Для начала работы отправьте текст задачи или Excel файл!
        """
        
        await self.send_temporary_message(
            context, user_id, help_text, 
            parse_mode='Markdown'
        )
        
        # Обновляем клавиатуру
        user_data = self.get_user_data(user_id)
        await self.update_main_keyboard(context, user_id, user_data.get('current_task'))
    
    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /clear"""
        user_id = update.effective_user.id
        
        # Очищаем предыдущие сообщения
        await self.cleanup_previous_messages(context, user_id)
        
        # Логируем действие
        self.log_activity(user_id, "clear_history")
        
        self.user_data[user_id] = {
            'excel_tasks': [],
            'text_tasks': [],
            'generated_codes': {},
            'html_contents': {},
            'current_task': None,
            'state': 'idle',
            'last_message_id': None,
            'task_documents': {},
            'keyboard_message_id': None,
            'last_keyboard_text': None,
            'last_keyboard_markup': None,
            'previous_messages': []
        }
        
        await self.send_temporary_message(
            context, user_id, 
            "✅ История задач очищена!"
        )
        
        # Возвращаем клавиатуру с примерами
        await self.update_examples_keyboard(context, user_id)
        
        logger.info(f"Пользователь {user_id} очистил историю")
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка загрузки Excel файлов"""
        user_id = update.effective_user.id
        user_data = self.get_user_data(user_id)
        
        # Очищаем предыдущие сообщения, но сохраняем клавиатуру
        await self.cleanup_previous_messages(context, user_id, keep_keyboard=True)
        
        # Логируем действие
        self.log_activity(user_id, "upload_excel")
        
        document = update.message.document
        file_extension = document.file_name.split('.')[-1].lower()
        
        if file_extension != 'xlsx':
            await self.send_temporary_message(
                context, user_id, 
                "❌ Пожалуйста, загрузите файл в формате .xlsx"
            )
            return
        
        # Скачивание файла
        file = await context.bot.get_file(document.file_id)
        file_path = f"temp_{user_id}_{document.file_name}"
        await file.download_to_drive(file_path)
        
        try:
            # Парсинг Excel
            with open(file_path, 'rb') as f:
                tasks = self.excel_parser.extract_tasks_from_xlsx(f)
            
            if tasks:
                user_data['excel_tasks'] = tasks
                user_data['state'] = 'excel_loaded'
                
                await self.send_temporary_message(
                    context, user_id,
                    f"✅ Найдено задач: {len(tasks)}\n\nВыберите задачу для генерации кода:"
                )
                
                # Обновляем клавиатуру для выбора задач
                keyboard = []
                for i, task in enumerate(tasks):
                    keyboard.append([
                        InlineKeyboardButton(
                            f"{task['id']}. {task['summary']}", 
                            callback_data=f"excel_task_{i}"
                        )
                    ])
                
                keyboard.append([InlineKeyboardButton("📝 Текстовый ввод", callback_data="text_input")])
                keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await self.update_keyboard_message(
                    context, user_id,
                    "📋 Выберите задачу из Excel:",
                    reply_markup=reply_markup
                )
                
                logger.info(f"Пользователь {user_id} загрузил Excel с {len(tasks)} задачами")
            else:
                await self.send_temporary_message(
                    context, user_id,
                    "❌ Не найдено подходящих задач в файле"
                )
                
        except Exception as e:
            logger.error(f"Error processing Excel file: {e}")
            await self.send_temporary_message(
                context, user_id,
                f"❌ Ошибка обработки файла: {str(e)}"
            )
        finally:
            # Удаляем временный файл
            if os.path.exists(file_path):
                os.remove(file_path)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений - НЕ УДАЛЯЕМ КЛАВИАТУРУ"""
        user_id = update.effective_user.id
        user_data = self.get_user_data(user_id)
        text = update.message.text
        
        # Очищаем предыдущие сообщения, но СОХРАНЯЕМ КЛАВИАТУРУ
        await self.cleanup_previous_messages(context, user_id, keep_keyboard=True)
        
        # Логируем действие
        self.log_activity(user_id, "text_input", task_description=text[:50])
        
        # Если пользователь в состоянии выбора задачи из Excel
        if user_data['state'] == 'excel_loaded' and text.isdigit():
            task_index = int(text) - 1
            if 0 <= task_index < len(user_data['excel_tasks']):
                task = user_data['excel_tasks'][task_index]
                await self.generate_and_send_code(update, context, task)
                return
        
        # Обычный текстовый запрос
        task_id = f"text_{len(user_data['text_tasks']) + 1}"
        task = {
            'id': task_id,
            'description': text,
            'summary': text[:40] + "..." if len(text) > 40 else text,
            'type': 'text'
        }
        
        user_data['text_tasks'].append(task)
        await self.generate_and_send_code(update, context, task)
        
        logger.info(f"Пользователь {user_id} отправил текстовый запрос: {text[:50]}...")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка callback от inline кнопок"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        user_data = self.get_user_data(user_id)
        callback_data = query.data
        
        # Очищаем предыдущие сообщения, но сохраняем клавиатуру
        await self.cleanup_previous_messages(context, user_id, keep_keyboard=True)
        
        # Логируем действие
        self.log_activity(user_id, f"callback_{callback_data}")
        
        logger.info(f"Получен callback: {callback_data} от пользователя {user_id}")
        
        try:
            if callback_data.startswith('excel_task_'):
                # Выбор задачи из Excel
                task_index = int(callback_data.split('_')[2])
                if task_index < len(user_data['excel_tasks']):
                    task = user_data['excel_tasks'][task_index]
                    await self.generate_and_send_code(update, context, task)
            
            elif callback_data == 'text_input':
                # Переход к текстовому вводу - НЕ УДАЛЯЕМ КЛАВИАТУРУ
                user_data['state'] = 'idle'
                await self.send_temporary_message(
                    context, user_id,
                    "📝 Введите описание задачи:"
                )
                # Обновляем клавиатуру для текстового ввода
                await self.update_main_keyboard(context, user_id)
            
            elif callback_data == 'regenerate':
                # Перегенерация кода
                if user_data['current_task']:
                    await self.generate_and_send_code(update, context, user_data['current_task'], regenerate=True)
                else:
                    await self.send_temporary_message(
                        context, user_id,
                        "❌ Нет текущей задачи для перегенерации"
                    )
            
            elif callback_data.startswith('switch_task_'):
                # Переключение на другую задачу
                parts = callback_data.split('_')
                if len(parts) >= 4:
                    task_type = parts[2]
                    task_index = int(parts[3])
                    
                    if task_type == 'excel' and task_index < len(user_data['excel_tasks']):
                        task = user_data['excel_tasks'][task_index]
                    elif task_type == 'text' and task_index < len(user_data['text_tasks']):
                        task = user_data['text_tasks'][task_index]
                    else:
                        await self.send_temporary_message(
                            context, user_id,
                            "❌ Задача не найдена"
                        )
                        return
                    
                    await self.switch_to_task(update, context, task)
            
            elif callback_data == 'task_list':
                # Показать список задач
                await self.show_task_list(user_id, context)
            
            elif callback_data == 'help':
                # Показ справки
                await self.send_help_message(user_id, context)
            
            elif callback_data == 'clear':
                # Очистка истории
                await self.clear_user_data(user_id, context)
            
            elif callback_data == 'new_task':
                # Новая задача - НЕ УДАЛЯЕМ КЛАВИАТУРУ
                user_data['state'] = 'idle'
                await self.send_temporary_message(
                    context, user_id,
                    "📝 Введите описание новой задачи:"
                )
                # Обновляем клавиатуру для новой задачи
                await self.update_main_keyboard(context, user_id)
            
            elif callback_data == 'back_to_main':
                # Возврат к главной клавиатуре
                await self.update_main_keyboard(context, user_id)
            
            elif callback_data == 'no_action':
                # Пустое действие
                pass
            
            elif callback_data.startswith('example_'):
                example_type = callback_data.split('_')[1]
                examples = {
                    'cat': "Создай креативное сайт-портфолио для кота, который ищет работу фронтенд-разработчиком. Включи анимации, интерактивные элементы и чувство юмора.",
                    'treasure': "Создай интерактивную карту сокровищ с анимацией клада, анимированным компасом и эффектами при наведении на острова.",
                    'dinosaur': "Создай простую игру 'Убеги от динозавра' с анимированным персонажем, препятствиями и счетчиком очков.",
                    'memes': "Создай генератор мемов с движущимися элементами, возможностью добавления текста и анимированными кнопками."
                }
                
                if example_type in examples:
                    task_id = f"example_{len(user_data['text_tasks']) + 1}"
                    task = {
                        'id': task_id,
                        'description': examples[example_type],
                        'summary': f"Пример: {example_type}",
                        'type': 'example'
                    }
                    
                    user_data['text_tasks'].append(task)
                    await self.generate_and_send_code(update, context, task)
                    
            else:
                logger.warning(f"Неизвестный callback: {callback_data}")
                await self.send_temporary_message(
                    context, user_id,
                    "❌ Неизвестная команда"
                )
                
        except Exception as e:
            logger.error(f"Ошибка обработки callback: {e}")
            await self.send_temporary_message(
                context, user_id,
                "❌ Ошибка обработки запроса"
            )
    
    async def show_task_list(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список всех задач"""
        user_data = self.get_user_data(user_id)
        
        if not user_data['excel_tasks'] and not user_data['text_tasks']:
            await self.send_temporary_message(
                context, user_id,
                "📭 У вас пока нет задач. Отправьте текстовое описание или Excel файл."
            )
            return
        
        text = "📋 **Список ваших задач:**\n\n"
        
        # Задачи из Excel
        if user_data['excel_tasks']:
            text += "📊 **Задачи из Excel:**\n"
            for i, task in enumerate(user_data['excel_tasks']):
                status = "✅" if task['id'] in user_data['generated_codes'] else "⏳"
                text += f"{status} {task['id']}. {task['summary']}\n"
        
        # Текстовые задачи
        if user_data['text_tasks']:
            text += "\n📝 **Текстовые задачи:**\n"
            for i, task in enumerate(user_data['text_tasks']):
                status = "✅" if task['id'] in user_data['generated_codes'] else "⏳"
                text += f"{status} {task['summary']}\n"
        
        await self.send_temporary_message(
            context, user_id,
            text,
            parse_mode='Markdown'
        )
        
        # Обновляем основную клавиатуру
        await self.update_main_keyboard(context, user_id, user_data.get('current_task'))
    
    async def send_help_message(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Отправка сообщения со справкой"""
        help_text = """
📖 **Справка по использованию бота**

**Формат Excel файла:**
Файл должен содержать колонки:
- "Хочу" - основное описание
- "Чтобы" - цель/результат  
- "Критерии приемки" - требования
- "Комментарии" - дополнительные notes

**Текстовые запросы:**
Просто опишите что нужно создать.

**Управление:**
- 🔄 Перегенерировать - создать новый код для текущей задачи
- 📋 Список задач - показать все задачи и переключиться между ними
- 📝 Новая задача - ввести новое текстовое описание
- 📖 Справка - показать эту справку
- 🗑️ Очистить - удалить историю задач
        """
        await self.send_temporary_message(
            context, user_id,
            help_text,
            parse_mode='Markdown'
        )
        
        # Обновляем основную клавиатуру
        user_data = self.get_user_data(user_id)
        await self.update_main_keyboard(context, user_id, user_data.get('current_task'))
    
    async def clear_user_data(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Очистка данных пользователя"""
        self.user_data[user_id] = {
            'excel_tasks': [],
            'text_tasks': [],
            'generated_codes': {},
            'html_contents': {},
            'current_task': None,
            'state': 'idle',
            'last_message_id': None,
            'task_documents': {},
            'keyboard_message_id': None,
            'last_keyboard_text': None,
            'last_keyboard_markup': None,
            'previous_messages': []
        }
        await self.send_temporary_message(
            context, user_id,
            "✅ История задач очищена!"
        )
        
        # Возвращаем клавиатуру с примерами
        await self.update_examples_keyboard(context, user_id)
        
        logger.info(f"Пользователь {user_id} очистил историю")
    
    async def generate_and_send_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE, task: Dict, regenerate: bool = False):
        """Генерация и отправка кода"""
        user_id = update.effective_user.id if update.message else update.callback_query.from_user.id
        user_data = self.get_user_data(user_id)
        
        # Очищаем предыдущие сообщения, но сохраняем клавиатуру
        await self.cleanup_previous_messages(context, user_id, keep_keyboard=True)
        
        # Получаем информацию о пользователе для сохранения
        user = update.effective_user if update.message else update.callback_query.from_user
        
        # Логируем действие
        action = "regenerate_code" if regenerate else "generate_code"
        self.log_activity(user_id, action, task['id'], task.get('description', ''))
        
        # Проверяем, не генерировали ли уже код для этой задачи
        if not regenerate and task['id'] in user_data['generated_codes']:
            await self.switch_to_task(update, context, task)
            return
        
        # Отправляем сообщение о начале генерации
        message = await context.bot.send_message(
            chat_id=user_id,
            text=f"🔄 Генерируем код для: {task['summary']}..."
        )
        user_data['previous_messages'].append(message.message_id)
        
        try:
            # Генерация кода
            generated_code = self.ai_client.generate_code(task['description'])
            
            if generated_code:
                html_content = self.code_renderer.prepare_html(generated_code)
                
                # Сохраняем код в файлы
                html_filepath, metadata_filepath = self.save_generated_code(
                    user_id, task, html_content, generated_code
                )
                
                # Сохраняем код в память
                user_data['generated_codes'][task['id']] = generated_code
                user_data['html_contents'][task['id']] = html_content
                user_data['current_task'] = task
                user_data['state'] = 'code_generated'
                
                # Создаем временный HTML файл для отправки
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                    f.write(html_content)
                    temp_file_path = f.name
                
                # Удаляем сообщение о генерации
                try:
                    await context.bot.delete_message(chat_id=user_id, message_id=message.message_id)
                    user_data['previous_messages'].remove(message.message_id)
                except Exception as e:
                    logger.debug(f"Не удалось удалить сообщение о генерации: {e}")
                
                # Отправляем файл
                with open(temp_file_path, 'rb') as f:
                    doc_message = await context.bot.send_document(
                        chat_id=user_id,
                        document=InputFile(f, filename=f"task_{task['id']}_code.html"),
                        caption=f"✅ Код сгенерирован для: {task['summary']}"
                    )
                
                # Сохраняем ID документа для задачи
                user_data['task_documents'][task['id']] = doc_message.message_id
                user_data['previous_messages'].append(doc_message.message_id)
                
                # Обновляем клавиатуру управления
                await self.update_main_keyboard(context, user_id, task)
                
                logger.info(f"Код сгенерирован для задачи {task['id']} пользователя {user_id}")
            else:
                await context.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=message.message_id,
                    text="❌ Не удалось сгенерировать код. Попробуйте изменить описание задачи."
                )
                
        except Exception as e:
            logger.error(f"Error generating code: {e}")
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=message.message_id,
                text=f"❌ Ошибка генерации кода: {str(e)}"
            )
        finally:
            # Удаляем временный файл
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    
    async def switch_to_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE, task: Dict):
        """Переключение на существующую задачу с повторной отправкой файла"""
        user_id = update.callback_query.from_user.id if update.callback_query else update.effective_user.id
        user_data = self.get_user_data(user_id)
        
        # Очищаем предыдущие сообщения, но сохраняем клавиатуру
        await self.cleanup_previous_messages(context, user_id, keep_keyboard=True)
        
        # Логируем действие
        self.log_activity(user_id, "switch_task", task['id'], task.get('description', ''))
        
        if task['id'] not in user_data['generated_codes']:
            await self.send_temporary_message(
                context, user_id,
                "❌ Код для этой задачи еще не сгенерирован"
            )
            return
        
        user_data['current_task'] = task
        
        # Получаем сохраненный HTML контент
        html_content = user_data['html_contents'][task['id']]
        
        # Создаем временный HTML файл для отправки
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html_content)
            temp_file_path = f.name
        
        try:
            # Отправляем файл заново
            with open(temp_file_path, 'rb') as f:
                doc_message = await context.bot.send_document(
                    chat_id=user_id,
                    document=InputFile(f, filename=f"task_{task['id']}_code.html"),
                    caption=f"📂 Активная задача: {task['summary']}"
                )
            
            # Сохраняем ID документа для задачи
            user_data['task_documents'][task['id']] = doc_message.message_id
            user_data['previous_messages'].append(doc_message.message_id)
            
            # Обновляем клавиатуру управления
            await self.update_main_keyboard(context, user_id, task)
            
            logger.info(f"Пользователь {user_id} переключился на задачу {task['id']}")
        except Exception as e:
            logger.error(f"Ошибка при отправке файла: {e}")
            await self.send_temporary_message(
                context, user_id,
                f"❌ Ошибка при отправке файла: {str(e)}"
            )
        finally:
            # Удаляем временный файл
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

def run_bot(token: str):
    """Запуск Telegram бота"""
    bot = TelegramBot(token)
    print("🤖 Telegram бот запущен...")
    bot.application.run_polling()

if __name__ == "__main__":
    # Для прямого запуска telegram_bot.py   
    from dotenv import load_dotenv
    load_dotenv()
        
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        print("💡 Создайте файл .env с TELEGRAM_BOT_TOKEN=your_token")
        exit(1)
    
    run_bot(BOT_TOKEN)
