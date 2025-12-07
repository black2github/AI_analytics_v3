# app/content_extractor.py

import logging
import re
from typing import List, Optional
from bs4 import BeautifulSoup, Tag, NavigableString
from dataclasses import dataclass
from app.utils.style_utils import is_black_color, has_colored_style

logger = logging.getLogger(__name__)


@dataclass
class ExtractionConfig:
    """Конфигурация/настройки для извлечения контента"""
    include_colored: bool = True  # True - все фрагменты, False - только подтвержденные
    preserve_whitespace: bool = True  # Сохранять пробелы
    normalize_spacing: bool = False  # Отключаем агрессивную нормализацию
    clean_brackets: bool = True
    format_tables: bool = True
    format_lists: bool = True
    format_headers: bool = True


class ContentExtractor:
    """
    Исправленный экстрактор контента с правильной обработкой порядка заголовков таблиц.
    """

    def __init__(self, config: ExtractionConfig):
        self.config = config

    def extract(self, html: str) -> str:
        """Главная точка входа с отладкой HTML"""
        if not html or not html.strip():
            return ""

        from app.history_cleaner import remove_history_sections
        html = remove_history_sections(html)

        soup = BeautifulSoup(html, "html.parser")

        self._process_expand_blocks(soup)

        result_parts = self._process_container(soup)
        result = self._join_parts_preserving_structure(result_parts)

        if self.config.normalize_spacing:
            result = self._apply_minimal_cleanup(result)

        return result

    def _process_table(self, element: Tag, context: str) -> str:
        """
        ИСПРАВЛЕНО: Обработка таблиц с правильным порядком заголовков
        Таблицы внутри ячеек других таблиц конвертируются в HTML
        ИСПРАВЛЕНИЕ: Корректная обработка всех строк из thead независимо от типа ячеек
        """
        if not self.config.format_tables:
            return self._process_text_container(element, context)

        # Если таблица находится внутри ячейки другой таблицы,
        # конвертируем её в HTML вместо Markdown
        if context in ["table_cell", "nested_table_cell"]:
            return self._process_nested_table_to_html(element)

        # Для обычного контекста - создаём Markdown таблицу
        # Собираем строки в правильном порядке
        table_rows = []

        # 1. Обрабатываем ВСЕ строки из thead как заголовки
        # независимо от того, используют они <th> или <td>
        thead = element.find("thead")
        if thead:
            header_rows = thead.find_all("tr", recursive=False)
            for row in header_rows:
                cells = row.find_all(["td", "th"], recursive=False)
                if cells:
                    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Все строки из thead обрабатываем как заголовки
                    row_data = self._process_table_row_cells(cells, context, is_header=True)
                    if row_data:
                        table_rows.append(("header", row_data))

        # 2. ЗАТЕМ обрабатываем тело таблицы из tbody
        tbody = element.find("tbody")
        if tbody:
            body_rows = tbody.find_all("tr", recursive=False)
            for row in body_rows:
                cells = row.find_all(["td", "th"], recursive=False)
                if cells:
                    row_data = self._process_table_row_cells(cells, context, is_header=False)
                    if row_data:
                        table_rows.append(("body", row_data))

        # 3. Если нет явных thead/tbody, берем все tr напрямую
        if not table_rows:
            direct_rows = element.find_all("tr", recursive=False)
            for i, row in enumerate(direct_rows):
                cells = row.find_all(["td", "th"], recursive=False)
                if cells:
                    # Первая строка считается заголовком, если все ячейки - th
                    is_header = (i == 0 and all(cell.name == "th" for cell in cells))
                    row_data = self._process_table_row_cells(cells, context, is_header=is_header)
                    if row_data:
                        row_type = "header" if is_header else "body"
                        table_rows.append((row_type, row_data))

        if not table_rows:
            return ""

        # Формируем таблицу с правильной обработкой множественных заголовков
        table_lines = []
        has_separator = False  # Флаг для добавления разделителя только один раз

        for row_type, row_data in table_rows:
            if row_type == "header":
                # Добавляем строку заголовка
                table_lines.append("| " + " | ".join(row_data) + " |")
                # Добавляем разделитель только после ПЕРВОГО заголовка
                if not has_separator:
                    table_lines.append("|" + "|".join([" --- " for _ in row_data]) + "|")
                    has_separator = True
            elif row_type == "body":
                # Добавляем строки тела таблицы
                table_lines.append("| " + " | ".join(row_data) + " |")

        table_content = "\n".join(table_lines) if table_lines else ""

        if table_content:
            return f"**Таблица:**\n{table_content}"
        return ""

    def _process_table_row_cells(self, cells: List[Tag], context: str, is_header: bool = False) -> List[str]:
        """
        НОВЫЙ МЕТОД: Обработка ячеек строки таблицы
        """
        row_data = []

        for cell in cells:
            if not self._should_include_element(cell):
                if not self.config.include_colored:
                    black_content = self._extract_black_elements_from_colored_container(cell, context)
                    if black_content:
                        cell_text = self._format_table_cell_content(black_content, cell)
                    else:
                        cell_text = ""
                else:
                    continue
            else:
                cell_content = self._process_table_cell(cell, "table_cell")
                cell_text = self._format_table_cell_content(cell_content, cell)

            row_data.append(cell_text)

        return row_data

    def _format_table_cell_content(self, content: str, cell: Tag) -> str:
        """
        НОВЫЙ МЕТОД: Форматирование содержимого ячейки с HTML атрибутами
        """
        if not content:
            content = ""

        # Добавляем HTML атрибуты для объединенных ячеек
        html_attrs = []
        if cell.get("rowspan") and int(cell.get("rowspan", 1)) > 1:
            html_attrs.append(f'rowspan="{cell["rowspan"]}"')
        if cell.get("colspan") and int(cell.get("colspan", 1)) > 1:
            html_attrs.append(f'colspan="{cell["colspan"]}"')

        if html_attrs:
            attrs_str = " ".join(html_attrs)
            return f'<td {attrs_str}>{content}</td>' if content else f'<td {attrs_str}></td>'
        else:
            return content

    # Остальные методы остаются без изменений (копируем из предыдущей версии)
    def _process_element(self, element, context: str = "default") -> Optional[str]:
        """Универсальная рекурсивная обработка элемента"""
        if isinstance(element, NavigableString):
            return self._process_text_node(str(element), context)

        if not isinstance(element, Tag):
            return None

        # ИСПРАВЛЕНО: Проверяем игнорируемые элементы ПЕРВЫМИ (до цветовой фильтрации)
        if self._is_ignored_element(element):
            return None

        # ДОБАВЛЕНО: Обработка <br> тегов
        if element.name == "br":
            return "\n"

        # Проверяем, должен ли элемент быть включен (цветовая фильтрация)
        if not self._should_include_element(element):
            if not self.config.include_colored:
                return self._extract_black_elements_from_colored_container(element, context)
            return None

        # Заголовки
        if element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            return self._process_header(element, context)

        # Таблицы
        if element.name == "table":
            return self._process_table(element, context)

        # Списки
        if element.name in ["ul", "ol"]:
            return self._process_list(element, context)

        # Ссылки
        if element.name in ["a", "ac:link"]:
            return self._process_link(element, context)

        # Время
        if element.name == "time" and element.get("datetime"):
            return element["datetime"]

        # Параграфы с добавлением переводов строк
        if element.name == "p":
            return self._process_paragraph(element, context)

        # div/span
        if element.name in ["div", "span"]:
            return self._process_text_container(element, context)

        # Confluence элементы
        if element.name in ["ac:rich-text-body", "ac:layout", "ac:layout-section", "ac:layout-cell"]:
            return self._process_confluence_container(element, context)

        # Ячейки таблицы
        if element.name in ["td", "th"]:
            return self._process_table_cell(element, context)

        # Элементы списка
        if element.name == "li":
            return self._process_list_item(element, context)

        # По умолчанию - обрабатываем как контейнер
        return self._process_text_container(element, context)

    def _process_children(self, element: Tag, context: str) -> str:
        """
        ИСПРАВЛЕНО: Рекурсивная обработка дочерних элементов с правильной обработкой пробелов
        """
        result_parts = []

        for child in element.children:
            if isinstance(child, NavigableString):
                text = str(child)
                # ИСПРАВЛЕНО: Обрабатываем ВСЕ текстовые узлы, включая пробелы
                processed_text = self._process_text_node(text, context)
                result_parts.append(processed_text)
            elif isinstance(child, Tag):
                # ИСПРАВЛЕНО: Проверяем игнорируемые элементы ДО обработки
                if not self._is_ignored_element(child):
                    child_content = self._process_element(child, context)
                    if child_content is not None:
                        result_parts.append(child_content)
                # Если элемент игнорируемый (<s>) - просто пропускаем его

        # Соединяем БЕЗ добавления пробелов
        result = "".join(result_parts)

        # Применяем только очистку треугольных скобок если нужно
        if self.config.clean_brackets:
            result = self._clean_triangular_brackets(result)

        return result

    def _extract_black_elements_from_colored_container(self, element: Tag, context: str) -> str:
        """
        ИСПРАВЛЕНО: НЕ добавляем текстовые узлы из цветных контейнеров
        """
        if not self.config.include_colored:
            approved_parts = []

            for child in element.children:
                if isinstance(child, NavigableString):
                    # ИСПРАВЛЕНО: НЕ добавляем текстовые узлы автоматически
                    # Они будут добавлены только если находятся в черном дочернем элементе
                    continue
                elif isinstance(child, Tag):
                    # Проверяем игнорируемые элементы ПЕРВЫМИ
                    if self._is_ignored_element(child):
                        continue

                    # Проверяем черные цвета напрямую
                    child_style = child.get("style", "").lower()
                    child_is_black = False

                    if "color" in child_style:
                        color_match = re.search(r'color\s*:\s*([^;]+)', child_style)
                        if color_match:
                            color_value = color_match.group(1).strip()
                            child_is_black = is_black_color(color_value)

                    if child_is_black:
                        # ИСПРАВЛЕНО: Черный дочерний элемент - извлекаем БЕЗ цветовой фильтрации
                        child_text = self._process_children_without_color_filter(child, context)
                        if child_text:
                            approved_parts.append(child_text)
                    elif has_colored_style(child):
                        # Цветной дочерний элемент - рекурсивно ищем в нем черные части
                        child_text = self._extract_black_elements_from_colored_container(child, context)
                        if child_text:
                            approved_parts.append(child_text)
                    else:
                        # Элемент без цвета - обрабатываем как обычно
                        if not self._is_ignored_element(child):
                            child_text = self._process_element(child, context)
                            if child_text:
                                approved_parts.append(child_text)

            return "".join(approved_parts)

        return ""

    def _should_include_element(self, element: Tag) -> bool:
        """
        ИСПРАВЛЕНО: Ссылки получают специальный пропуск для анализа соседей
        """
        if self.config.include_colored:
            return True

        # Ссылки всегда пропускаем для анализа соседей в _process_link
        if element.name in ['a', 'ac:link']:
            return True

        # Для остальных элементов применяем цветовую фильтрацию
        if has_colored_style(element):
            return False

        if self._is_in_colored_ancestor_chain(element):
            return False

        return True

    def _process_text_node(self, text: str, context: str) -> str:
        """
        ИСПРАВЛЕНО: Обработка текстового узла БЕЗ потери пробелов
        """
        # Заменяем неразрывные пробелы на обычные
        text = text.replace('\u00a0', ' ')

        # Если включена минимальная нормализация, применяем только базовые правила
        if self.config.normalize_spacing:
            # Только критичные случаи - табы на пробелы
            text = text.replace('\t', ' ')

        return text

    def _is_ignored_element(self, element: Tag) -> bool:
        """
        ИСПРАВЛЕНО: Проверяет, должен ли элемент игнорироваться
        """
        if not isinstance(element, Tag):
            return False

        # Зачеркнутый текст
        if element.name == "s":
            return True

        # Jira макросы
        if element.name == "ac:structured-macro" and element.get("ac:name") == "jira":
            return True

        if (element.name == "ac:parameter" and element.parent and
                element.parent.name == "ac:structured-macro" and
                element.parent.get("ac:name") == "jira"):
            return True

        return False

    # ОСТАЛЬНЫЕ МЕТОДЫ БЕЗ ИЗМЕНЕНИЙ (копируем из предыдущей версии)
    def _join_parts_preserving_structure(self, parts: List[str]) -> str:
        """Соединяет части с сохранением структуры"""
        if not parts:
            return ""

        non_empty_parts = [part for part in parts if part]

        if not non_empty_parts:
            return ""

        result_parts = []

        for i, part in enumerate(non_empty_parts):
            if i == 0:
                result_parts.append(part)
            else:
                prev_part = non_empty_parts[i - 1]
                current_part = part

                if (prev_part.endswith('\n') or current_part.startswith('\n')):
                    result_parts.append(current_part)
                elif (self._is_block_element(prev_part) or self._is_block_element(current_part)):
                    result_parts.append('\n\n' + current_part)
                else:
                    result_parts.append(current_part)

        return "".join(result_parts)

    def _is_block_element(self, content: str) -> bool:
        """Проверяет, является ли содержимое блочным элементом"""
        if not content:
            return False

        content_start = content.lstrip()
        return (content_start.startswith('#') or  # Заголовки
                content_start.startswith('|') or  # Таблицы
                content_start.startswith('**Таблица:**') or  # Наши таблицы
                content_start.startswith('-') or  # Списки
                content_start.startswith('*') or  # Списки
                content_start.startswith('+') or  # Списки
                re.match(r'^\d+\.', content_start))  # Нумерованные списки

    def _process_container(self, container) -> List[str]:
        """
        Рекурсивная обработка контейнера
        """
        result_parts = []

        # Обрабатываем ВСЕ дочерние элементы, включая NavigableString
        for i, child in enumerate(container.children):
            if isinstance(child, NavigableString):
                # Обрабатываем текстовые узлы (включая пробелы)
                text = str(child)
                if text:  # Не пропускаем пробелы!
                    processed_text = self._process_text_node(text, "default")
                    result_parts.append(processed_text)
            elif isinstance(child, Tag):

                # Проверяем, должен ли элемент быть включен
                should_include = self._should_include_element(child)

                if not should_include:
                    if not self.config.include_colored:
                        black_content = self._extract_black_elements_from_colored_container(child, "default")
                        if black_content:
                            result_parts.append(black_content)
                else:
                    processed_content = self._process_element(child, context="default")
                    if processed_content is not None:
                        result_parts.append(processed_content)

        return result_parts

    def _process_paragraph(self, element: Tag, context: str) -> str:
        """Обработка параграфов с добавлением переводов строк"""
        content = self._process_children(element, context)

        if not content:
            return ""

        # ИСПРАВЛЕНИЕ: Добавляем перевод строки для всех контекстов
        if context in ["table_cell", "nested_table_cell"]:
            if not content.endswith('\n'):
                content += '\n'
        else:
            # Для обычного контекста тоже добавляем перевод строки
            if not content.endswith('\n'):
                content += '\n'

        return content

    def _process_list(self, element: Tag, context: str, indent_level: int = 0) -> str:
        """Обработка списков с правильными переводами строк"""
        if not self.config.format_lists:
            return self._process_text_container(element, context)

        list_items = []
        indent = "    " * indent_level

        if element.name == "ul":
            markers = ["-", "*", "+"]
            marker = markers[indent_level % len(markers)]
        else:
            marker = None

        item_counter = 1

        for li in element.find_all("li", recursive=False):
            if not self._should_include_element(li):
                if not self.config.include_colored:
                    black_content = self._extract_black_elements_from_colored_container(li, context)
                    if black_content:
                        if element.name == "ul":
                            list_items.append(f"{indent}{marker} {black_content}")
                        else:
                            list_items.append(f"{indent}{item_counter}. {black_content}")
                            item_counter += 1
                continue

            item_content = self._process_list_item_content(li, context, indent_level)

            # ИСПРАВЛЕНО: Проверяем, что содержимое не пустое после trim
            if item_content and item_content.strip():
                if element.name == "ul":
                    list_items.append(f"{indent}{marker} {item_content}")
                else:
                    list_items.append(f"{indent}{item_counter}. {item_content}")
                    item_counter += 1

            nested_lists = li.find_all(["ul", "ol"], recursive=False)
            for nested_list in nested_lists:
                nested_content = self._process_list(nested_list, context, indent_level + 1)
                if nested_content:
                    list_items.append(nested_content)

        result = "\n".join(list_items)

        if result and context in ["table_cell", "nested_table_cell"]:
            result += "\n"

        return result

    def _process_list_item_content(self, li: Tag, context: str, indent_level: int) -> str:
        """Обработка содержимого элемента списка с правильными переводами"""
        content_parts = []

        for child in li.children:
            if isinstance(child, NavigableString):
                text = str(child)
                processed_text = self._process_text_node(text, context)
                content_parts.append(processed_text)
            elif isinstance(child, Tag):
                if child.name in ["ul", "ol"]:
                    continue
                else:
                    if self._should_include_element(child):
                        child_content = self._process_element(child, context)
                        if child_content is not None:
                            content_parts.append(child_content)
                    elif not self.config.include_colored:
                        black_content = self._extract_black_elements_from_colored_container(child, context)
                        if black_content:
                            content_parts.append(black_content)

        result = "".join(content_parts)
        result = result.rstrip('\n')

        return result

    def _apply_minimal_cleanup(self, content: str) -> str:
        """Применяет только минимальную очистку контента"""
        if not content:
            return content

        content = content.replace('\u00a0', ' ')

        if self.config.normalize_spacing:
            content = content.replace('\t', ' ')
            content = re.sub(r' {4,}', ' ', content)

        if self.config.clean_brackets:
            content = self._clean_triangular_brackets(content)

        return content

    def _clean_triangular_brackets(self, content: str) -> str:
        """Очистка содержимого треугольных скобок"""
        content = re.sub(r'<\s*([^<>]*?)\s*>', lambda m: f'<{self._clean_bracket_content(m.group(1))}>', content)
        content = re.sub(r'<\s*>', '<>', content)
        return content

    def _clean_bracket_content(self, content: str) -> str:
        """Умная очистка содержимого треугольных скобок"""
        if not content:
            return ''

        content = content.strip()
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'"\s+', '"', content)
        content = re.sub(r'\s+"', '"', content)
        content = re.sub(r'(\w)"', r'\1 "', content)
        content = re.sub(r'\[\s+', '[', content)
        content = re.sub(r'\s+\]', ']', content)

        return content

    def _is_in_colored_ancestor_chain(self, element: Tag) -> bool:
        """Проверяет, есть ли цветные предки у элемента"""
        if self.config.include_colored:
            return False

        current = element.parent
        while current and isinstance(current, Tag):
            if current.name == "ac:rich-text-body":
                break
            if has_colored_style(current):
                return True
            current = current.parent
        return False

    def _process_text_container(self, element: Tag, context: str) -> str:
        """Обработка текстовых контейнеров (div, span)"""
        if element.name == "div":
            inner_headers = element.find_all(["h1", "h2", "h3", "h4", "h5", "h6"], recursive=False)
            if inner_headers:
                return self._process_confluence_container(element, context)

        return self._process_children(element, context)

    def _process_confluence_container(self, element: Tag, context: str) -> str:
        """Обработка Confluence контейнеров"""
        nested_parts = self._process_container(element)
        return self._join_parts_preserving_structure(nested_parts)

    def _process_link(self, element: Tag, context: str) -> str:
        """
        Анализ соседей применяется везде одинаково
        """
        # В режиме "только подтвержденные" всегда анализируем соседей
        if not self.config.include_colored:
            if not self._analyze_link_neighbors(element):
                return ""

        ri_page = element.find("ri:page")
        if ri_page and ri_page.get("ri:content-title"):
            link_text = f'[{ri_page["ri:content-title"]}]'
        elif element.get_text():
            link_text = f'[{element.get_text()}]'
        else:
            link_text = ""

        return link_text

    def _analyze_link_neighbors(self, link_element: Tag) -> bool:
        """
        Анализ соседних блоков ссылки для определения её статуса
        """
        if not link_element.parent:
            return True

        parent = link_element.parent
        all_children = list(parent.children)

        try:
            link_index = all_children.index(link_element)
        except ValueError:
            return True

        left_status = self._get_neighbor_block_status(all_children, link_index, -1)
        right_status = self._get_neighbor_block_status(all_children, link_index, 1)

        # Применяем правила анализа
        if left_status is None and right_status is None:
            return True
        elif left_status is None:
            left_status = right_status
        elif right_status is None:
            right_status = left_status

        # Если оба соседних блока цветные - ссылка исключается
        result = not (left_status and right_status)

        return result

    def _get_neighbor_block_status(self, children: list, start_index: int, direction: int) -> Optional[bool]:
        """
        Получает статус соседнего блока, пропуская незначимые пробелы
        """
        step = direction
        for i in range(start_index + step, len(children) if direction > 0 else -1, step):
            if direction < 0 and i < 0:
                break

            child = children[i]

            # ИСПРАВЛЕНИЕ: Пропускаем незначимые текстовые узлы
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if not text:  # Пустой текст (пробелы, переводы строк) - пропускаем
                    continue
                # Значимый текст - анализируем
                status = False  # Текстовые узлы без стиля = подтвержденные
                return status
            else:
                status = self._get_text_block_color_status(child)

                if status is not None:
                    return status

        return None

    def _get_text_block_color_status(self, element) -> Optional[bool]:
        """Определяет статус текстового блока"""
        if isinstance(element, NavigableString):
            text = str(element)
            return False if text else None

        if isinstance(element, Tag):
            if element.name in ["br", "ac:structured-macro"]:
                return None

            text_content = element.get_text()
            if not text_content:
                return None

            return has_colored_style(element)

        return None

    # Остальные методы таблиц (копируем без изменений)
    def _process_header(self, element: Tag, context: str) -> str:
        """Обработка заголовков с префиксами"""
        if not self.config.format_headers:
            return self._process_text_container(element, context)

        level = int(element.name[1])
        prefix = "#" * level
        content = self._process_children(element, context)

        if content:
            return f"{prefix} {content}"
        return ""

    def _process_table_cell(self, element: Tag, context: str) -> str:
        """
        ИСПРАВЛЕНО: Обработка ячейки таблицы - исключает двойную обработку вложенных таблиц
        """
        nested_table = element.find("table")
        if nested_table:
            # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Если есть вложенная таблица, сразу возвращаем результат
            # и НЕ продолжаем дальнейшую обработку через structural_elements
            return self._process_cell_with_nested_table(element, nested_table, context)

        structural_elements = element.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "div", "p"],
                                               recursive=False)

        if len(structural_elements) > 0:
            cell_parts = []

            for child in element.children:
                if isinstance(child, NavigableString):
                    text = str(child)
                    if text:
                        text = text.replace('\u00a0', ' ')
                        cell_parts.append(text)
                elif isinstance(child, Tag):
                    child_content = self._process_element(child, "table_cell")
                    if child_content:
                        cell_parts.append(child_content)

            if cell_parts:
                result = "".join(cell_parts)

                if self.config.clean_brackets:
                    result = self._clean_triangular_brackets(result)

                return result
            else:
                return self._process_children(element, "table_cell")
        else:
            return self._process_children(element, "table_cell")

    def _process_cell_with_nested_table(self, cell: Tag, nested_table: Tag, context: str) -> str:
        """
        ИСПРАВЛЕНО: Обработка ячейки с вложенной таблицей
        Извлекает весь контент до и после таблицы, включая контент из контейнеров
        """
        result_parts = []

        # ИСПРАВЛЕНИЕ: Собираем весь контент до таблицы, включая из контейнеров
        text_before = self._extract_content_before_table(cell, nested_table, context)
        if text_before:
            result_parts.append(text_before)

        # Обрабатываем саму вложенную таблицу
        nested_html = self._process_nested_table_to_html(nested_table)
        if nested_html:
            result_parts.append(f"**Таблица:** {nested_html}")

        # ИСПРАВЛЕНИЕ: Собираем весь контент после таблицы
        text_after = self._extract_content_after_table(cell, nested_table, context)
        if text_after:
            result_parts.append(text_after)

        return " ".join(result_parts)

    def _extract_content_before_table(self, cell: Tag, target_table: Tag, context: str) -> str:
        """
        НОВЫЙ МЕТОД: Извлекает весь контент ДО таблицы, включая из контейнеров
        """
        result_parts = []

        def extract_until_table(element, target):
            """Рекурсивно извлекает контент до таблицы"""
            for child in element.children:
                # Если нашли целевую таблицу - останавливаемся
                if child == target:
                    return True

                if isinstance(child, NavigableString):
                    text = str(child)
                    if text:
                        result_parts.append(text)
                elif isinstance(child, Tag):
                    # Если это таблица (но не наша целевая) - пропускаем
                    if child.name == "table":
                        continue

                    # Если элемент содержит целевую таблицу - рекурсивно обрабатываем
                    if child.find(lambda t: t == target):
                        found = extract_until_table(child, target)
                        if found:
                            return True
                    else:
                        # Элемент не содержит таблицу - обрабатываем полностью
                        content = self._process_element(child, context)
                        if content:
                            result_parts.append(content)

            return False

        extract_until_table(cell, target_table)
        return "".join(result_parts)

    def _extract_content_after_table(self, cell: Tag, target_table: Tag, context: str) -> str:
        """
        НОВЫЙ МЕТОД: Извлекает весь контент ПОСЛЕ таблицы
        """
        result_parts = []
        found_table = False

        def extract_after_table(element, target):
            """Рекурсивно извлекает контент после таблицы"""
            nonlocal found_table

            for child in element.children:
                # Отмечаем, что нашли целевую таблицу
                if child == target:
                    found_table = True
                    continue

                # Если ещё не нашли таблицу
                if not found_table:
                    # Если элемент содержит целевую таблицу - рекурсивно ищем
                    if isinstance(child, Tag) and child.find(lambda t: t == target):
                        extract_after_table(child, target)
                    continue

                # Уже после таблицы - собираем контент
                if isinstance(child, NavigableString):
                    text = str(child)
                    if text:
                        result_parts.append(text)
                elif isinstance(child, Tag):
                    # Если это другая таблица - пропускаем
                    if child.name == "table":
                        continue

                    content = self._process_element(child, context)
                    if content:
                        result_parts.append(content)

        extract_after_table(cell, target_table)
        return "".join(result_parts)

    def _process_nested_table_to_html(self, table: Tag) -> str:
        """
        ИСПРАВЛЕНО: Преобразование вложенной таблицы в HTML с обработкой глубокой вложенности
        """
        rows = table.find_all("tr", recursive=False)
        if not rows:
            tbody = table.find("tbody")
            thead = table.find("thead")
            if tbody:
                rows.extend(tbody.find_all("tr", recursive=False))
            if thead:
                rows.extend(thead.find_all("tr", recursive=False))

        if not rows:
            return ""

        html_parts = ["<table>"]

        for row in rows:
            cells = row.find_all(["td", "th"], recursive=False)
            row_parts = ["<tr>"]

            for cell in cells:
                tag_name = "th" if cell.name == "th" else "td"

                attrs = []
                if cell.get("rowspan") and int(cell.get("rowspan", 1)) > 1:
                    attrs.append(f'rowspan="{cell["rowspan"]}"')
                if cell.get("colspan") and int(cell.get("colspan", 1)) > 1:
                    attrs.append(f'colspan="{cell["colspan"]}"')

                attrs_str = " " + " ".join(attrs) if attrs else ""

                # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Обрабатываем содержимое ячейки специальным методом
                # который конвертирует вложенные таблицы в HTML вместо Markdown
                cell_content = self._process_nested_table_cell_content(cell)
                row_parts.append(f"<{tag_name}{attrs_str}>{cell_content}</{tag_name}>")

            row_parts.append("</tr>")
            html_parts.append("".join(row_parts))

        html_parts.append("</table>")
        return "".join(html_parts)

    def _process_nested_table_cell_content(self, cell: Tag) -> str:
        """
        ИСПРАВЛЕНО: Обработка содержимого ячейки вложенной таблицы.
        Конвертирует вложенные таблицы в HTML, а не в Markdown.
        ДОБАВЛЕНА обработка заголовков h1-h6
        """
        result_parts = []

        for child in cell.children:
            if isinstance(child, NavigableString):
                text = str(child)
                if text:
                    text = text.replace('\u00a0', ' ')
                    result_parts.append(text)
            elif isinstance(child, Tag):
                if self._is_ignored_element(child):
                    continue

                # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Применяем цветовую фильтрацию
                should_include = self._should_include_element(child)
                if not should_include:
                    if not self.config.include_colored:
                        black_content = self._extract_black_elements_from_colored_container(child, "nested_table_cell")
                        if black_content:
                            result_parts.append(black_content)
                    continue

                # Элемент прошел цветовую фильтрацию - обрабатываем
                if child.name == "table":
                    # Таблицу конвертируем в HTML рекурсивно
                    nested_html = self._process_nested_table_to_html(child)
                    if nested_html:
                        result_parts.append(nested_html)
                elif child.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                    # ДОБАВЛЕНО: Обработка заголовков
                    if self.config.format_headers:
                        level = int(child.name[1])
                        prefix = "#" * level
                        content = self._process_nested_table_cell_content(child)
                        if content:
                            result_parts.append(f"{prefix} {content}\n")
                    else:
                        content = self._process_nested_table_cell_content(child)
                        if content:
                            result_parts.append(content)
                            if not content.endswith('\n'):
                                result_parts.append('\n')
                elif child.name in ["a", "ac:link"]:
                    link_content = self._process_link(child, "nested_table_cell")
                    if link_content:
                        result_parts.append(link_content)
                elif child.name in ["ul", "ol"]:
                    # Списки обрабатываем через _process_list
                    list_content = self._process_list(child, "nested_table_cell")
                    if list_content:
                        result_parts.append(list_content)
                elif child.name == "br":
                    result_parts.append("\n")
                elif child.name == "p":
                    # Обрабатываем параграфы внутри ячеек
                    p_content = self._process_nested_table_cell_content(child)
                    if p_content:
                        result_parts.append(p_content)
                        if not p_content.endswith('\n'):
                            result_parts.append('\n')
                else:
                    # Для остальных элементов рекурсивно обрабатываем содержимое
                    child_content = self._process_nested_table_cell_content(child)
                    if child_content:
                        result_parts.append(child_content)

        return "".join(result_parts)

    def _process_list_item(self, element: Tag, context: str) -> str:
        """Обработка элемента списка"""
        return self._process_children(element, context)

    def _process_expand_blocks(self, soup: BeautifulSoup):
        """Обработка expand блоков Confluence"""
        for expand in soup.find_all("ac:structured-macro", {"ac:name": "expand"}):
            rich_text_body = expand.find("ac:rich-text-body")
            if rich_text_body:
                expand.replace_with(rich_text_body)

    def _process_children_without_color_filter(self, element: Tag, context: str) -> str:
        """
        Обработка дочерних элементов БЕЗ цветовой фильтрации.
        Используется когда мы уже внутри подтвержденного (черного) элемента.
        """
        result_parts = []

        for child in element.children:
            if isinstance(child, NavigableString):
                text = str(child)
                if text:
                    processed_text = self._process_text_node(text, context)
                    result_parts.append(processed_text)
            elif isinstance(child, Tag):
                # ВАЖНО: НЕ применяем цветовую фильтрацию, но проверяем игнорируемые
                if not self._is_ignored_element(child):
                    child_content = self._process_element_without_color_filter(child, context)
                    if child_content is not None:
                        result_parts.append(child_content)

        result = "".join(result_parts)

        if self.config.clean_brackets:
            result = self._clean_triangular_brackets(result)

        return result

    def _process_element_without_color_filter(self, element, context: str = "default") -> Optional[str]:
        """
        НОВЫЙ МЕТОД: Обработка элемента БЕЗ цветовой фильтрации.
        """
        if isinstance(element, NavigableString):
            return self._process_text_node(str(element), context)

        if not isinstance(element, Tag):
            return None

        # Проверяем только игнорируемые элементы
        if self._is_ignored_element(element):
            return None

        if element.name == "br":
            return "\n"

        # Обрабатываем элементы БЕЗ цветовых проверок
        if element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            return self._process_header_without_color_filter(element, context)
        elif element.name in ["a", "ac:link"]:
            return self._process_link(element, context)
        elif element.name == "p":
            return self._process_paragraph_without_color_filter(element, context)
        else:
            # Для всех остальных элементов - просто обрабатываем детей
            return self._process_children_without_color_filter(element, context)

    def _process_header_without_color_filter(self, element: Tag, context: str) -> str:
        """Обработка заголовков БЕЗ цветовой фильтрации"""
        if not self.config.format_headers:
            return self._process_children_without_color_filter(element, context)

        level = int(element.name[1])
        prefix = "#" * level
        content = self._process_children_without_color_filter(element, context)

        if content:
            return f"{prefix} {content}"
        return ""

    def _process_paragraph_without_color_filter(self, element: Tag, context: str) -> str:
        """Обработка параграфов БЕЗ цветовой фильтрации"""
        content = self._process_children_without_color_filter(element, context)

        if not content:
            return ""

        # Добавляем перевод строки для всех контекстов
        if context in ["table_cell", "nested_table_cell"]:
            if not content.endswith('\n'):
                content += '\n'
        else:
            # Для обычного контекста тоже добавляем перевод строки
            if not content.endswith('\n'):
                content += '\n'

        return content


# Фабричные функции остаются теми же
def create_all_fragments_extractor() -> ContentExtractor:
    """Создает экстрактор для всех фрагментов с сохранением пробелов"""
    config = ExtractionConfig(
        include_colored=True,
        preserve_whitespace=True,
        normalize_spacing=False
    )
    return ContentExtractor(config)


def create_approved_fragments_extractor() -> ContentExtractor:
    """Создает экстрактор для подтвержденных фрагментов с сохранением пробелов"""
    config = ExtractionConfig(
        include_colored=False,
        preserve_whitespace=True,
        normalize_spacing=False
    )
    return ContentExtractor(config)