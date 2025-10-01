import pandas as pd
import io
from typing import List, Dict

class ExcelParser:
    @staticmethod
    def extract_tasks_from_xlsx(uploaded_file) -> List[Dict]:
        """Парсинг Excel файла из Streamlit upload"""
        try:
            # Чтение файла из streamlit
            df = pd.read_excel(uploaded_file)
            
            # Определяем возможные названия колонок для разных частей описания
            description_columns = [
                ['Хочу', 'Want', 'Wish'],  # Основное желание
                ['Чтобы', 'So that', 'For'],  # Цель/результат
                ['Критерии приемки', 'Acceptance Criteria', 'Criteria'],  # Критерии
                ['Комментарии', 'Comments', 'Comment']  # Дополнительные комментарии
            ]
            
            tasks = []
            for idx, row in df.iterrows():
                # Собираем описание задачи из нескольких частей
                task_parts = []
                want_content = ""  # Отдельно сохраняем содержание "Хочу" для названия
                
                for column_group in description_columns:
                    part_found = False
                    for possible_col in column_group:
                        if possible_col in df.columns:
                            part_value = str(row[possible_col]).strip()
                            # Проверяем, что значение не пустое и не служебное
                            if (part_value and 
                                len(part_value) > 3 and 
                                part_value.lower() not in ['nan', 'none', 'null', 'нет', 'не указано']):
                                
                                # Сохраняем содержание "Хочу" для использования в названии
                                if column_group[0] == 'Хочу':
                                    want_content = part_value
                                
                                # Добавляем заголовок для части описания
                                if column_group[0] == 'Хочу':
                                    task_parts.append(f"Хочу: {part_value}")
                                elif column_group[0] == 'Чтобы':
                                    task_parts.append(f"Чтобы: {part_value}")
                                elif column_group[0] == 'Критерии приемки':
                                    task_parts.append(f"Критерии приемки: {part_value}")
                                elif column_group[0] == 'Комментарии':
                                    task_parts.append(f"Комментарии: {part_value}")
                                
                                part_found = True
                                break
                    
                    # Если конкретная колонка не найдена, пробуем найти по похожим названиям
                    if not part_found:
                        for possible_col in column_group:
                            similar_cols = [col for col in df.columns if possible_col.lower() in col.lower()]
                            if similar_cols:
                                part_value = str(row[similar_cols[0]]).strip()
                                if (part_value and 
                                    len(part_value) > 3 and 
                                    part_value.lower() not in ['nan', 'none', 'null', 'нет', 'не указано']):
                                    
                                    # Сохраняем содержание "Хочу" для использования в названии
                                    if column_group[0] == 'Хочу':
                                        want_content = part_value
                                    
                                    if column_group[0] == 'Хочу':
                                        task_parts.append(f"Хочу: {part_value}")
                                    elif column_group[0] == 'Чтобы':
                                        task_parts.append(f"Чтобы: {part_value}")
                                    elif column_group[0] == 'Критерии приемки':
                                        task_parts.append(f"Критерии приемки: {part_value}")
                                    elif column_group[0] == 'Комментарии':
                                        task_parts.append(f"Комментарии: {part_value}")
                                
                                break
                
                # Объединяем все части в полное описание задачи
                full_description = "\n".join(task_parts)
                
                # Фильтрация пустых описаний
                if full_description and len(full_description.strip()) > 10:
                    # Создаем название задачи на основе содержания "Хочу"
                    if want_content:
                        # Берем первые несколько слов из "Хочу" для названия
                        want_words = want_content.split()[:5]  # Первые 5 слов
                        summary = " ".join(want_words)
                        if len(summary) > 40:  # Обрезаем если слишком длинное
                            summary = summary[:40] + "..."
                    else:
                        # Если "Хочу" нет, используем стандартное название
                        summary = f"Задача {idx + 1}"
                    
                    tasks.append({
                        'id': f"excel_{idx + 1}",
                        'description': full_description,
                        'summary': summary,
                        'type': 'excel',
                        'raw_data': {col: str(row[col]) for col in df.columns if col in row}
                    })
            
            return tasks
            
        except Exception as e:
            raise Exception(f"Ошибка парсинга XLSX: {str(e)}")