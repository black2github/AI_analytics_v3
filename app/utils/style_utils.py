# app/style_utils.py

import re
from typing import Optional
from bs4 import Tag

def has_colored_style(element: Tag) -> bool:
    """
    Проверяет, имеет ли элемент цветной стиль.
    Возвращает True, если имеет цвет, отличный от черного.
    """
    if not isinstance(element, Tag):
        return False

    style = element.get("style", "").lower()
    if not style or "color" not in style:
        return False

    color_match = re.search(r'color\s*:\s*([^;]+)', style)
    if not color_match:
        return False

    color_value = color_match.group(1).strip()

    is_black = is_black_color(color_value)

    return not is_black  # True если НЕ черный (т.е. цветной)


# Набор стандартных комбинаций цветов редактора Confluence, воспринимаемых глазом
# как чёрный. НЕ переписывать (собран на реальных данных); расширять — согласовывать
# отдельно (ТЗ п. 4.3 / п. 11.5). Сравнение см. в is_black_color: буквальное ИЛИ
# нормализованное, поэтому набор покрывает и другие написания тех же цветов.
black_colors = {
    'black', '#000', '#000000',
    'rgb(0,0,0)', 'rgb(0, 0, 0)',
    'rgb(8,8,8)', 'rgb(8, 8, 8)',
    'rgb(32,33,34)', 'rgb(32, 33, 34)',
    'rgba(0,0,0,1)', 'rgba(0, 0, 0, 1)',
    'rgb(51,51,0)', 'rgb(51, 51, 0)',
    'rgb(0,51,0)', 'rgb(0, 51, 0)',
    'rgb(0,51,102)', 'rgb(0, 51, 102)',
    'rgb(51,51,51)', 'rgb(51, 51, 51)',
    'rgb(23,43,77)', 'rgb(23, 43, 77)'
}

# Минимальный словарь именованных цветов CSS, встречающихся в разметке Confluence.
# Нужен нормализации (ТЗ п. 4.3: «поддержать black и другие именованные»).
_NAMED_COLORS = {
    'black': '#000000',
    'white': '#ffffff',
    'red': '#ff0000',
    'green': '#008000',
    'blue': '#0000ff',
    'gray': '#808080',
    'grey': '#808080',
    'silver': '#c0c0c0',
    'maroon': '#800000',
    'olive': '#808000',
    'lime': '#00ff00',
    'aqua': '#00ffff',
    'teal': '#008080',
    'navy': '#000080',
    'fuchsia': '#ff00ff',
    'magenta': '#ff00ff',
    'purple': '#800080',
    'orange': '#ffa500',
    'yellow': '#ffff00',
}


def normalize_color(color_value: str) -> Optional[str]:
    """Приводит любое представление цвета к каноническому виду ``#rrggbb`` (ТЗ п. 4.3).

    Поддерживает: именованные цвета, ``#rgb``, ``#rrggbb``, ``rgb(...)``, ``rgba(...)``
    (альфа игнорируется), произвольные пробелы и любой регистр. Возвращает нормализованную
    строку в нижнем регистре или ``None``, если значение распознать не удалось.
    """
    if not color_value:
        return None

    value = color_value.strip().lower()

    # Именованный цвет.
    if value in _NAMED_COLORS:
        return _NAMED_COLORS[value]

    # Hex-форма: #rgb или #rrggbb.
    m = re.fullmatch(r'#([0-9a-f]{3}|[0-9a-f]{6})', value)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = ''.join(ch * 2 for ch in h)  # #abc -> #aabbcc
        return '#' + h

    # rgb()/rgba() — извлекаем первые три числовых компонента, альфу отбрасываем.
    m = re.fullmatch(r'rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*'
                     r'(?:,\s*[0-9.]+\s*)?\)', value)
    if m:
        try:
            r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        except ValueError:
            return None
        if any(c > 255 for c in (r, g, b)):
            return None
        return '#{:02x}{:02x}{:02x}'.format(r, g, b)

    return None


# Нормализованные формы чёрного — считаются один раз (ТЗ п. 4.3: сравнение после
# нормализации ОБЕИХ сторон).
_BLACK_NORMALIZED = {n for n in (normalize_color(c) for c in black_colors) if n}


# Нефункциональные цвета интерфейса Confluence/Atlassian — НЕ разметка требований, а стили
# ссылок/фона. При миграции цвета их не считаем правкой (не порождают маркер/UNKNOWN),
# трактуем как «не требование». Расширять по мере обнаружения на реальных данных.
IGNORED_COLORS = {
    'rgb(0,82,204)', 'rgb(0, 82, 204)',   # #0052cc — синий цвет гиперссылок Atlassian
    'rgb(244,245,247)', 'rgb(244, 245, 247)',  # #f4f5f7 — светло-серый фон/подложка (N10)
}
_IGNORED_NORMALIZED = {n for n in (normalize_color(c) for c in IGNORED_COLORS) if n}


def is_ignored_color(color_value: str) -> bool:
    """True для нефункциональных UI-цветов (ссылки/фон): их не трактуем как правку требования.

    Сравнение по нормализованной форме (как для чёрного). Пустое/нераспознанное значение — False.
    """
    if not color_value:
        return False
    value = color_value.strip().lower()
    if value in IGNORED_COLORS:
        return True
    norm = normalize_color(value)
    return norm is not None and norm in _IGNORED_NORMALIZED


def is_black_color(color_value: str) -> bool:
    """
    Проверяет, является ли цвет черным.

    Сравнение — буквальное (историческое поведение) ИЛИ по нормализованной форме
    (ТЗ п. 4.3): это только РАСШИРЯЕТ множество «чёрного» (разные написания одного и
    того же цвета, напр. rgb(51,51,51) и #333333), но никогда его не сужает.
    """
    value = color_value.strip().lower()

    # 1. Буквальное совпадение — прежнее поведение, никогда не теряется.
    if value in black_colors:
        return True

    # 2. Нормализованное совпадение — новые написания уже-чёрных цветов.
    norm = normalize_color(value)
    return norm is not None and norm in _BLACK_NORMALIZED
