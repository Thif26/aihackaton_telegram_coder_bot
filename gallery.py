import streamlit as st
import os
import json
from datetime import datetime
import base64

def show_gallery():
    st.title("🎨 Галерея сгенерированных проектов")
    
    # Поиск всех сохраненных проектов
    projects = scan_projects()
    
    if not projects:
        st.info("🎭 Пока нет сгенерированных проектов. Создайте первый!")
        return
    
    # Фильтры и поиск
    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input("🔍 Поиск проектов", placeholder="Введите название проекта...")
    with col2:
        project_type = st.selectbox("Тип", ["Все", "Игры", "Портфолио", "Анимации", "Другое"])
    
    # Отфильтровать проекты
    filtered_projects = filter_projects(projects, search_term, project_type)
    
    # Показать статистику
    st.write(f"**📊 Найдено проектов:** {len(filtered_projects)} из {len(projects)}")
    
    # Сетка проектов
    cols = st.columns(3)
    for idx, project in enumerate(filtered_projects):
        with cols[idx % 3]:
            display_project_card(project, idx)

def scan_projects():
    """Сканирует директории на наличие проектов"""
    projects = []
    base_dir = "generated_codes"
    
    # Сканируем Streamlit проекты
    streamlit_dir = os.path.join(base_dir, "streamlit", "sessions")
    if os.path.exists(streamlit_dir):
        for session_dir in os.listdir(streamlit_dir):
            session_path = os.path.join(streamlit_dir, session_dir, "codes")
            if os.path.exists(session_path):
                projects.extend(scan_session_projects(session_path, "streamlit"))
    
    # Сканируем Telegram проекты
    telegram_dir = os.path.join(base_dir, "users")
    if os.path.exists(telegram_dir):
        for user_dir in os.listdir(telegram_dir):
            user_path = os.path.join(telegram_dir, user_dir, "codes")
            if os.path.exists(user_path):
                projects.extend(scan_session_projects(user_path, "telegram"))
    
    return sorted(projects, key=lambda x: x.get('timestamp', ''), reverse=True)

def scan_session_projects(session_path, platform):
    """Сканирует проекты в сессии"""
    projects = []
    for file in os.listdir(session_path):
        if file.endswith('.json'):
            metadata_path = os.path.join(session_path, file)
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Находим соответствующий HTML файл
                html_file = metadata.get('html_file')
                if html_file and os.path.exists(os.path.join(session_path, html_file)):
                    projects.append({
                        'metadata': metadata,
                        'html_path': os.path.join(session_path, html_file),
                        'platform': platform,
                        'timestamp': metadata.get('generated_at', ''),
                        'type': categorize_project(metadata.get('task_description', '')),
                        'task_id': metadata.get('task_id', '')  # Добавляем task_id
                    })
            except Exception as e:
                print(f"Error reading {metadata_path}: {e}")
    
    return projects

def categorize_project(description):
    """Категоризирует проект по описанию"""
    desc_lower = description.lower()
    if any(word in desc_lower for word in ['игр', 'game', 'убеги', 'поймай']):
        return "Игры"
    elif any(word in desc_lower for word in ['портфолио', 'portfolio', 'резюме', 'визитк']):
        return "Портфолио"
    elif any(word in desc_lower for word in ['анимац', 'animation', 'движ', 'moving']):
        return "Анимации"
    else:
        return "Другое"

def filter_projects(projects, search_term, project_type):
    """Фильтрует проекты по поисковому запросу и типу"""
    filtered = projects
    
    if search_term:
        search_term = search_term.lower()
        filtered = [p for p in filtered if search_term in p['metadata'].get('task_description', '').lower()]
    
    if project_type != "Все":
        filtered = [p for p in filtered if p['type'] == project_type]
    
    return filtered

def display_project_card(project, index):
    """Отображает карточку проекта"""
    metadata = project['metadata']
    
    with st.container():
        st.markdown(f"### {metadata.get('task_summary', 'Проект')}")
        
        # Информация о проекте
        st.caption(f"🕐 {format_timestamp(metadata.get('generated_at'))}")
        st.caption(f"📱 {project['platform']} • {project['type']}")
        
        # Предпросмотр (упрощенный - можно улучшить скриншотами)
        with st.expander("👁️ Предпросмотр", expanded=False):
            try:
                with open(project['html_path'], 'r', encoding='utf-8') as f:
                    html_content = f.read()
                st.components.v1.html(html_content, height=300, scrolling=True)
            except Exception as e:
                st.error(f"Ошибка загрузки: {e}")
        
        # Кнопки действий
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📂 Открыть", key=f"open_{index}", use_container_width=True):
                display_project_detail(project)
        with col2:
            with open(project['html_path'], 'r', encoding='utf-8') as f:
                html_content = f.read()
            st.download_button(
                "💾 Скачать",
                html_content,
                file_name=f"{metadata.get('task_id', 'project')}.html",
                mime="text/html",
                key=f"download_{index}",
                use_container_width=True
            )

def display_project_detail(project):
    """Показывает детали проекта в модальном окне"""
    st.session_state.current_project = project

def format_timestamp(timestamp):
    """Форматирует временную метку"""
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return timestamp