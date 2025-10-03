import streamlit as st
import pandas as pd
import tempfile
import os
import json
import csv
from datetime import datetime
from typing import Dict
from utils.excel_parser import ExcelParser
from utils.ai_client import AIClient
from utils.code_renderer import CodeRenderer

# Настройка страницы для мобильных устройств
st.set_page_config(
    page_title="AI Code Generator",
    page_icon="🚀",
    layout="centered",
    initial_sidebar_state="collapsed",
    menu_items=None
)

# Скрываем дефолтные элементы Streamlit
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
div[data-testid="stSidebarUserContent"] {
    padding: 1rem;
}
.css-1d391kg {padding: 1rem;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# Создание директорий для сохранения файлов
def setup_directories():
    """Создание необходимых директорий для сохранения файлов"""
    base_save_dir = "generated_codes"
    streamlit_dir = os.path.join(base_save_dir, "streamlit")
    logs_dir = os.path.join(streamlit_dir, "logs")
    sessions_dir = os.path.join(streamlit_dir, "sessions")
    users_dir = os.path.join(streamlit_dir, "users")
    
    os.makedirs(streamlit_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(sessions_dir, exist_ok=True)
    os.makedirs(users_dir, exist_ok=True)
    
    return streamlit_dir, logs_dir, sessions_dir, users_dir

STREAMLIT_DIR, LOGS_DIR, SESSIONS_DIR, USERS_DIR = setup_directories()

def get_user_id():
    """Получение или создание ID пользователя"""
    if 'user_id' not in st.session_state:
        # Пробуем получить из cookies или создаем новый
        try:
            # Используем комбинацию браузерных fingerprint для создания стабильного ID
            user_agent = st.query_params.get("user_agent", "unknown")
            # Создаем хэш на основе user agent и времени (как простой способ)
            import hashlib
            user_hash = hashlib.md5(f"{user_agent}_{datetime.now().strftime('%Y%m')}".encode()).hexdigest()[:8]
            st.session_state.user_id = f"user_{user_hash}"
        except:
            st.session_state.user_id = f"user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return st.session_state.user_id

def get_session_id():
    """Получение уникального идентификатора сессии"""
    if 'session_id' not in st.session_state:
        st.session_state.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    return st.session_state.session_id

def save_user_state():
    """Сохранение состояния пользователя"""
    user_id = get_user_id()
    user_state_file = os.path.join(USERS_DIR, f"{user_id}_state.json")
    
    state_to_save = {
        'user_id': user_id,
        'excel_tasks': st.session_state.get('excel_tasks', []),
        'text_tasks': st.session_state.get('text_tasks', []),
        'generated_codes': st.session_state.get('generated_codes', {}),
        'html_contents': st.session_state.get('html_contents', {}),
        'saved_files': st.session_state.get('saved_files', {}),
        'last_saved': datetime.now().isoformat()
    }
    
    try:
        with open(user_state_file, 'w', encoding='utf-8') as f:
            json.dump(state_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Ошибка сохранения состояния: {e}")

def load_user_state():
    """Загрузка состояния пользователя"""
    user_id = get_user_id()
    user_state_file = os.path.join(USERS_DIR, f"{user_id}_state.json")
    
    if os.path.exists(user_state_file):
        try:
            with open(user_state_file, 'r', encoding='utf-8') as f:
                saved_state = json.load(f)
            
            # Восстанавливаем состояние
            st.session_state.excel_tasks = saved_state.get('excel_tasks', [])
            st.session_state.text_tasks = saved_state.get('text_tasks', [])
            st.session_state.generated_codes = saved_state.get('generated_codes', {})
            st.session_state.html_contents = saved_state.get('html_contents', {})
            st.session_state.saved_files = saved_state.get('saved_files', {})
            
            # Обновляем информацию о последнем сохранении
            st.session_state.last_state_load = saved_state.get('last_saved', 'unknown')
            
            return True
        except Exception as e:
            st.error(f"Ошибка загрузки состояния: {e}")
            return False
    return False

def load_tasks_from_files():
    """Загрузка задач из сохраненных файлов для переключения на них"""
    user_id = get_user_id()
    user_codes_dir = os.path.join(USERS_DIR, user_id, "codes")
    
    if not os.path.exists(user_codes_dir):
        return
    
    loaded_tasks = []
    
    # Ищем все JSON файлы с метаданными
    for filename in os.listdir(user_codes_dir):
        if filename.endswith('.json'):
            try:
                with open(os.path.join(user_codes_dir, filename), 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Создаем задачу из метаданных
                task = {
                    'id': metadata.get('task_id', filename),
                    'description': metadata.get('task_description', ''),
                    'summary': metadata.get('task_summary', ''),
                    'type': metadata.get('task_type', 'file'),
                    'generated_at': metadata.get('generated_at', ''),
                    'html_file': metadata.get('html_file', ''),
                    'metadata_file': filename
                }
                
                # Добавляем в список загруженных задач
                loaded_tasks.append(task)
                
                # Загружаем HTML содержимое если нужно
                html_file_path = os.path.join(user_codes_dir, task['html_file'])
                if os.path.exists(html_file_path) and task['id'] not in st.session_state.html_contents:
                    with open(html_file_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    st.session_state.html_contents[task['id']] = html_content
                
                # ПРОВЕРЯЕМ, есть ли уже сохраненный код в других файлах
                # Загружаем HTML файл и сохраняем его как код (если нужно)
                if os.path.exists(html_file_path) and task['id'] not in st.session_state.generated_codes:
                    with open(html_file_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    # Сохраняем оригинальный HTML как код
                    st.session_state.generated_codes[task['id']] = html_content
                
            except Exception as e:
                print(f"Ошибка загрузки файла {filename}: {e}")
    
    return loaded_tasks

def save_generated_code(session_id: str, task: Dict, html_content: str, generated_code: str):
    """Сохранение сгенерированного кода в файл"""
    user_id = get_user_id()
    user_codes_dir = os.path.join(USERS_DIR, user_id, "codes")
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
        'user_id': user_id,
        'session_id': session_id,
        'platform': 'streamlit'
    }
    
    metadata_filename = f"task_{task['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    metadata_filepath = os.path.join(user_codes_dir, metadata_filename)
    
    with open(metadata_filepath, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    # Сохраняем состояние пользователя
    save_user_state()
    
    return html_filepath, metadata_filepath

def log_activity(session_id: str, action: str, task_id: str = "", task_description: str = ""):
    """Логирование активности в Streamlit"""
    user_id = get_user_id()
    log_file = os.path.join(LOGS_DIR, f"streamlit_activity_{datetime.now().strftime('%Y-%m-%d')}.csv")
    file_exists = os.path.isfile(log_file)
    
    with open(log_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['timestamp', 'user_id', 'session_id', 'action', 'task_id', 'task_description', 'platform'])
        
        writer.writerow([
            datetime.now().isoformat(),
            user_id,
            session_id,
            action,
            task_id,
            task_description[:100],  # Ограничиваем длину описания
            'streamlit'
        ])

# Инициализация утилит
@st.cache_resource
def load_ai_client():
    return AIClient()

@st.cache_resource
def load_code_renderer():
    return CodeRenderer()

def main():
    # URL изображений с GitHub
    header_image_path = "https://raw.githubusercontent.com/Thif26/aihackaton_telegram_coder_bot/main/images/Header.png"
    logo_image_path = "https://raw.githubusercontent.com/Thif26/aihackaton_telegram_coder_bot/main/images/logo.jpg"
    
    # Верхняя картинка на всю ширину экрана
    st.markdown(
        f"""
        <div style="width: 100%; margin: 0 auto; text-align: center;">
            <img src="{header_image_path}" 
                 style="width: 100%; max-width: 100%; height: auto; border-radius: 10px; margin-bottom: 1rem;">
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    st.title("🚀 AI Code Generator")
    
    # Получаем ID пользователя и сессии
    user_id = get_user_id()
    session_id = get_session_id()
    
    # Логируем запуск приложения
    log_activity(session_id, "start_app")
    
    # Инициализация сессии с загрузкой состояния
    if 'excel_tasks' not in st.session_state:
        st.session_state.excel_tasks = []
    if 'text_tasks' not in st.session_state:
        st.session_state.text_tasks = []
    if 'file_tasks' not in st.session_state:
        st.session_state.file_tasks = []
    if 'current_task' not in st.session_state:
        st.session_state.current_task = None
    if 'generated_codes' not in st.session_state:
        st.session_state.generated_codes = {}
    if 'html_contents' not in st.session_state:
        st.session_state.html_contents = {}
    if 'saved_files' not in st.session_state:
        st.session_state.saved_files = {}
    
    # Загружаем состояние пользователя при первом запуске
#    if 'state_loaded' not in st.session_state:
#        if load_user_state():
#            st.success("✅ Загружена история из предыдущих сессий!")
        
        # Загружаем задачи из файлов для переключения
#        file_tasks = load_tasks_from_files()
#        if file_tasks:
#            st.session_state.file_tasks = file_tasks
#            st.success(f"✅ Загружено {len(file_tasks)} задач из файлов для переключения!")
#        
#        st.session_state.state_loaded = True
    
    # Мобильная навигация
    if st.session_state.current_task and st.session_state.current_task['id'] in st.session_state.generated_codes:
        display_results(session_id, user_id)
    else:
        show_input_section(session_id, user_id)
    
    # Кнопка настроек в углу
    with st.container():
        col1, col2, col3 = st.columns([1, 1, 510])
        with col3:
            if st.button("**⬇⬇⬇ Подробнее ⬇⬇⬇**", use_container_width=True):
                st.session_state.show_settings = not st.session_state.get('show_settings', False)
        
        if st.session_state.get('show_settings', False):
            show_settings(session_id, user_id)
    
# Нижняя картинка по центру среднего размера
    st.markdown(
        f"""
        <div style="width: 100%; margin: 2rem auto; text-align: center;">
            <img src="{logo_image_path}" 
                 style="width: 100%; max-width: 300px; height: auto; border-radius: 10px;">
        </div>
        """, 
        unsafe_allow_html=True
    )

#def display_task_history(session_id):
#    """Отображение истории задач внизу страницы"""
#    # Показываем задачи из файлов для переключения
#    if st.session_state.file_tasks:
#        st.markdown("---")
#        st.markdown("### 📚 История задач")
#        display_task_tiles(st.session_state.file_tasks, session_id, "file")


def show_input_section(session_id, user_id):
    st.markdown("Загрузите .xlsx файл или введите описание задачи")
    
    # Выбор метода ввода
    input_method = st.radio(
        "Способ ввода:",
        ["Файл Excel", "Текстовое описание"],
        horizontal=True,
        label_visibility="collapsed",
        index=1
    )
    
    if input_method == "Файл Excel":
        handle_file_upload_mobile(session_id)
    else:
        handle_text_input_mobile(session_id)

def handle_file_upload_mobile(session_id):
    """Оптимизированная загрузка файлов для мобильных"""
    uploaded_file = st.file_uploader(
        "Загрузите .xlsx файл",
        type=['xlsx'],
        help="Файл должен содержать колонку 'Описание задачи'",
        key="excel_uploader"
    )
    
    # Логируем загрузку файла
    if uploaded_file:
        log_activity(session_id, "upload_excel", task_description=uploaded_file.name)
    
    # Показываем историю задач в виде плиток
    if st.session_state.excel_tasks:
        st.markdown("---")
        st.markdown("**📚 Загруженные задачи из Excel:**")
        
        # Создаем плитки для задач из Excel
        display_task_tiles(st.session_state.excel_tasks, session_id, "excel")
    
    if uploaded_file:
        try:
            # Проверяем, не загружали ли уже этот файл
            file_hash = hash(uploaded_file.getvalue())
            if 'last_file_hash' not in st.session_state or st.session_state.last_file_hash != file_hash:
                excel_parser = ExcelParser()
                tasks = excel_parser.extract_tasks_from_xlsx(uploaded_file)
                
                if tasks:
                    st.session_state.excel_tasks = tasks
                    st.session_state.last_file_hash = file_hash
                    
                    # Сохраняем состояние после загрузки файла
                    save_user_state()
                    
                    st.success(f"✅ Найдено задач: {len(tasks)}")
                    
                    # Логируем успешную загрузку
                    log_activity(session_id, "excel_processed", task_description=f"Found {len(tasks)} tasks")
                else:
                    st.error("❌ Не найдено подходящих задач в файле")
                    log_activity(session_id, "excel_empty")
                    
        except Exception as e:
            st.error(f"❌ Ошибка обработки файла: {str(e)}")
            log_activity(session_id, "excel_error", task_description=str(e))

def handle_text_input_mobile(session_id):
    """Оптимизированный текстовый ввод для мобильных"""
    # Показываем задачи из файлов для переключения
    if st.session_state.file_tasks:
        st.markdown("---")
        st.markdown("**📚 История задач:**")
        display_task_tiles(st.session_state.file_tasks, session_id, "file")
    
    # Кнопки с готовыми примерами
    st.markdown("**🎯 Готовые примеры:**")

    # Создаем плитки для примеров - используем фиксированные ключи чтобы избежать дублирования
    example_cols = st.columns(2)
    
    with example_cols[0]:
        if st.button("🐱 Портфолио для кота\nв IT", 
                    use_container_width=True, 
                    key="cat_portfolio_unique",
                    help="Создай креативное сайт-портфолио для кота"):
            example_description = "Создай креативное сайт-портфолио для кота, который ищет работу фронтенд-разработчиком в Яндексе. Включи анимации, интерактивные элементы и чувство юмора."
            create_task_from_example(session_id, example_description, "Портфолио для кота в IT")
        
        if st.button("🗺️ Карта на которой расписано где курьеры прячут вкусные отменёнки", 
                    use_container_width=True, 
                    key="treasure_map_unique",
                    help="Интерактивная карта с анимацией"):
            example_description = "Создай интерактивную карту сокровищ с анимацией клада, анимированным компасом и эффектами при наведении на острова."
            create_task_from_example(session_id, example_description, "Карта сокровищ курьеров")
        
        if st.button("🎮 Игра: Убеги от тимлида", 
                    use_container_width=True, 
                    key="dinosaur_game_unique",
                    help="Простая игра с прыжками и препятствиями"):
            example_description = "Создай простую игру 'Убеги от тимлида' с анимированным персонажем, препятствиями и счетчиком очков. В котором персонаж должен прыгать по нажатию пользователем и уклоняться от препядствий"
            create_task_from_example(session_id, example_description, "Убеги от тимлида")
    
    with example_cols[1]:
        if st.button("😂 Генератор мемов\nна дейлик", 
                    use_container_width=True, 
                    key="meme_generator_unique",
                    help="Генератор мемов с анимированными кнопками"):
            example_description = "Создай генератор мемов с движущимися элементами, с функциональной возможностью добавления текста и анимированными кнопками."
            create_task_from_example(session_id, example_description, "Генератор мемов")
        
        if st.button("🪬 Тайные знания древних яндексоидов **УЗНАТЬ БОЛЬШЕ**", 
                    use_container_width=True, 
                    key="qwfqfqw_unique",
                    help="Шутливый сайт о древних Яндексоидах"):
            example_description = "Создай сайт на котором на шутливый манер рассказывается история о том, как древние Яндексоиды прилетели на планету Земля чтобы подарить людям сервис доставки еды и лучшую поисковую систему."
            create_task_from_example(session_id, example_description, "Тайные знания древних яндексоидов")
        
        if st.button("📊 Аналитика\nдоставки", 
                    use_container_width=True, 
                    key="analytics_dashboard_unique",
                    help="Дашборд для анализа доставки"):
            example_description = "Создай интерактивный дашборд для анализа статистики доставки с графиками, фильтрами и анимированными переходами."
            create_task_from_example(session_id, example_description, "Аналитика доставки")
    
    st.markdown("---")
    st.markdown("**💡 Или придумайте свой вариант:**")
    
    # Используем session_state для хранения введенного текста
    if 'text_input' not in st.session_state:
        st.session_state.text_input = ""
    
    task_description = st.text_area(
        "Опишите задачу:",
        value=st.session_state.text_input,
        placeholder="Например: Создай сайт-портфолио для кота, который ищет работу в IT...",
        height=100,
        key="text_input_area"
    )
    
    # Обновляем session_state при изменении текста
    st.session_state.text_input = task_description
    
    if st.button("🚀 Сгенерировать код", type="primary", use_container_width=True, key="generate_from_text"):
        if task_description.strip():
            create_task_from_text(session_id, task_description)
        else:
            st.warning("⚠️ Введите описание задачи")

def create_task_from_example(session_id, description, summary):
    """Создает задачу из примера и запускает генерацию"""
    # Проверяем, нет ли уже такой задачи в истории
    existing_task = next((t for t in st.session_state.text_tasks if t['description'] == description), None)
    
    if existing_task:
        # Если задача уже существует, переключаемся на нее
        st.session_state.current_task = existing_task
        st.success(f"✅ Переключились на существующую задачу: {summary}")
        st.rerun()
        return
    
    # Создаем новую задачу
    task_id = f"text_{len(st.session_state.text_tasks) + 1}"
    task = {
        'id': task_id,
        'description': description,
        'summary': summary,
        'type': 'text'
    }
    
    # Добавляем в историю текстовых задач
    st.session_state.text_tasks.append(task)
    
    # Логируем использование примера
    log_activity(session_id, "use_example", task_id, summary)
    
    generate_code(session_id, task)

def create_task_from_text(session_id, task_description):
    """Создает задачу из пользовательского текста и запускает генерацию"""
    # Проверяем, нет ли уже такой задачи в истории
    existing_task = next((t for t in st.session_state.text_tasks if t['description'] == task_description), None)
    
    if existing_task:
        # Если задача уже существует, переключаемся на нее
        st.session_state.current_task = existing_task
        st.success(f"✅ Переключились на существующую задачу: {existing_task['summary']}")
        st.rerun()
        return
    
    # Создаем новую задачу
    task_id = f"text_{len(st.session_state.text_tasks) + 1}"
    task = {
        'id': task_id,
        'description': task_description,
        'summary': task_description[:50] + "..." if len(task_description) > 50 else task_description,
        'type': 'text'
    }
    
    # Добавляем в историю текстовых задач
    st.session_state.text_tasks.append(task)
    
    generate_code(session_id, task)

def display_task_tiles(tasks, session_id, task_type):
    """Отображение задач в виде плиток с превью"""
    if not tasks:
        return
    
    # Разбиваем задачи на ряды по 2 плитки в каждом
    for i in range(0, len(tasks), 2):
        cols = st.columns(2)
        
        for j in range(2):
            if i + j < len(tasks):
                task = tasks[i + j]
                with cols[j]:
                    # Добавляем контекст к индексу для большей уникальности
                    context_index = f"{task_type}_{i + j}"
                    render_task_tile(task, session_id, task_type, context_index)

def render_task_tile(task, session_id, task_type, index):
    """Рендеринг одной плитки задачи с кликабельностью"""
    # Статус задачи
    has_generated_code = task['id'] in st.session_state.generated_codes
    status = "✅" if has_generated_code else "⏳"
    
    # Получаем HTML превью если есть сгенерированный код
    preview_html = ""
    if has_generated_code:
        preview_html = st.session_state.html_contents.get(task['id'], "")

    # Создаем контейнер для плитки
    with st.container():
        # Используем columns для создания кликабельной области
        col1, col2 = st.columns([4, 1])
        
        with col1:
            # Основная кликабельная область
            # Уникальный ключ с учетом типа задачи, ID и индекса
            unique_key = f"main_tile_{task_type}_{task['id']}_{index}_{hash(task['summary'])}"
            if st.button(
                f"**{task['summary']}**\n\n"
                f"{status} {task['id']} • {task_type}",
                key=unique_key,
                use_container_width=True,
                help="Нажмите чтобы открыть эту задачу"
            ):
                switch_to_task(session_id, task)
        
        with col2:
            # Кнопка обновления с уникальным ключом
            regen_key = f"regenerate_{task_type}_{task['id']}_{index}_{hash(task['summary'])}"
            if st.button(
                "🔄",
                key=regen_key,
                use_container_width=True,
                help="Перегенерировать код" if task_type != 'file' else "Недоступно для файлов"
            ):
                if task_type != 'file':
                    generate_code(session_id, task)
                else:
                    st.warning("Для задач из файлов перегенерация недоступна")

        # Разделитель между плитками
        st.markdown("---")
        
def generate_code(session_id, task):
    """Генерация кода для задачи"""
    ai_client = load_ai_client()
    code_renderer = load_code_renderer()
    
    # Логируем начало генерации
    log_activity(session_id, "generate_code_start", task['id'], task.get('description', ''))
    
    with st.spinner("🔄 Генерируем код с помощью AI..."):
        try:
            generated_code = ai_client.generate_code(task['description'])
            
            if generated_code:
                html_content = code_renderer.prepare_html(generated_code)
                
                # Сохраняем код в файлы
                html_filepath, metadata_filepath = save_generated_code(
                    session_id, task, html_content, generated_code
                )
                
                # ПРАВИЛЬНОЕ сохранение кода в словарь - сохраняем сам код, а не True
                st.session_state.generated_codes[task['id']] = generated_code
                st.session_state.html_contents[task['id']] = html_content
                st.session_state.current_task = task
                st.session_state.show_settings = False
                
                # Сохраняем информацию о файлах
                st.session_state.saved_files[task['id']] = {
                    'html_file': html_filepath,
                    'metadata_file': metadata_filepath
                }
                
                # Логируем успешную генерацию
                log_activity(session_id, "generate_code_success", task['id'], task.get('description', ''))
                
                st.success("✅ Код успешно сгенерирован и сохранен!")
                st.rerun()
            else:
                st.error("❌ Не удалось сгенерировать код")
                log_activity(session_id, "generate_code_failed", task['id'], task.get('description', ''))
                
        except Exception as e:
            st.error(f"❌ Ошибка генерации: {str(e)}")
            log_activity(session_id, "generate_code_error", task['id'], str(e))

def switch_to_task(session_id, task):
    """Переключение на существующую задачу без генерации"""
    st.session_state.current_task = task
    st.session_state.show_settings = False
    
    # Логируем переключение
    log_activity(session_id, "switch_task", task['id'], task.get('description', ''))
    
    st.success(f"✅ Переключились на задачу: {task['summary']}")
    st.rerun()

def display_results(session_id, user_id):
    """Оптимизированное отображение результатов для мобильных"""
    task = st.session_state.current_task
    
    # Получаем сохраненный код для текущей задачи
    generated_code = st.session_state.generated_codes.get(task['id'])
    html_content = st.session_state.html_contents.get(task['id'])
    
    if not generated_code or not html_content:
        st.error("❌ Код для этой задачи не найден")
        clear_session()
        return
    
    st.subheader(f"Задача: {task['summary']}")
    
    st.markdown("---")
    
    # Компактные кнопки управления
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    with col1:
        if st.button("🔄 Перегенерировать", use_container_width=True):
            generate_code(session_id, task)
    with col2:
        st.download_button(
            label="💾 Скачать HTML",
            data=html_content,
            file_name=f"task_{task['id']}_code.html",
            mime="text/html",
            use_container_width=True
        )
    with col3:
        if st.button("📝 Новая задача", use_container_width=True):
            clear_session()
            st.rerun()
    with col4:
        if st.button("📊", use_container_width=True, help="Статистика"):
            st.session_state.show_stats = not st.session_state.get('show_stats', False)
    
    # Показ статистики
    if st.session_state.get('show_stats', False):
        show_statistics(session_id, user_id)
    
    # Вертикальное расположение вместо колонок
    st.markdown("### 👁️ Предпросмотр")
    st.components.v1.html(html_content, height=1000, scrolling=True)
    
    st.markdown("### 📝 Код")
    with st.expander("Показать код"):
        # Проверяем, является ли значение строкой кода, а не True
        if isinstance(generated_code, str):
            st.code(generated_code, language='html')
        else:
            st.error("Код недоступен для отображения")


def show_statistics(session_id, user_id):
    """Показать статистику по сессии"""
    st.markdown("---")
    st.markdown("### 📊 Статистика сессии")
    
    total_tasks = len(st.session_state.excel_tasks) + len(st.session_state.text_tasks) + len(st.session_state.file_tasks)
    generated_tasks = len(st.session_state.generated_codes)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Всего задач", total_tasks)
    with col2:
        st.metric("Сгенерировано", generated_tasks)
    with col3:
        st.metric("ID пользователя", user_id[:8] + "...")
    
    # Информация о сохраненных файлах
    if st.session_state.saved_files:
        st.markdown("**💾 Сохраненные файлы:**")
        for task_id, files in st.session_state.saved_files.items():
            st.write(f"- Задача {task_id}: {os.path.basename(files['html_file'])}")

def show_settings(session_id, user_id):
    """Настройки в компактном виде"""
    st.markdown("---")
    st.markdown("### 🔧 Настройки")
    
    # Статистика
    total_tasks = len(st.session_state.excel_tasks) + len(st.session_state.text_tasks) + len(st.session_state.file_tasks)
    generated_tasks = len(st.session_state.generated_codes)
    st.write(f"**📊 Статистика:** Всего задач: {total_tasks}, Сгенерировано: {generated_tasks}")
    
    if st.button("🔄 Проверить подключение к API", use_container_width=True):
        test_api_connection(session_id)
    
    # Очистка истории
    if st.button("🗑️ Очистить историю задач", use_container_width=True):
        clear_history(session_id)
    
    # Краткая инструкция
    with st.expander("📋 Краткая инструкция"):
        st.markdown("""
        1. **Выберите решение задач через выгрузку Excel или по текстовому описанию**
        2. **Нажмите кнопку** `Сгенерировать код`
                    
        **💡 Особенности:**
        - Код сохраняется для каждой задачи
        - Можно переключаться между задачами без повторной генерации
        - Для перегенерации используйте кнопку 🔄
        - Все файлы сохраняются автоматически
        - История сохраняется между сессиями
        - Задачи из файлов доступны только для просмотра
        """)

def test_api_connection(session_id):
    """Тестирование подключения"""
    ai_client = load_ai_client()
    
    # Логируем тестирование
    log_activity(session_id, "test_api_connection")
    
    with st.spinner("Проверяем подключение..."):
        test_result = ai_client.generate_code("Создай заголовок 'Hello World'")
        
        if test_result:
            st.success("✅ Подключение к OpenRouter API работает!")
            log_activity(session_id, "test_api_success")
        else:
            st.error("❌ Ошибка подключения к API. Проверьте API ключ.")
            log_activity(session_id, "test_api_failed")

def clear_session():
    """Очистка текущей сессии (но не истории)"""
    keys_to_clear = ['current_task', 'show_settings', 'show_stats']
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

def clear_history(session_id):
    """Очистка всей истории задач и кодов"""
    # Логируем очистку
    log_activity(session_id, "clear_history")
    
    st.session_state.excel_tasks = []
    st.session_state.text_tasks = []
    st.session_state.file_tasks = []
    st.session_state.generated_codes = {}
    st.session_state.html_contents = {}
    st.session_state.saved_files = {}
    
    if 'last_file_hash' in st.session_state:
        del st.session_state.last_file_hash
    
    clear_session()
    
    # Сохраняем пустое состояние
    save_user_state()
    
    st.success("✅ История задач очищена!")
    st.rerun()

if __name__ == "__main__":
    main()
