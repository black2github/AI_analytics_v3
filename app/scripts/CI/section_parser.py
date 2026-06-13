# app/scripts/CI/section_parser.py
#
# Шаг 1 генератора карточек: разбор мигрированного .md документа требований
# на frontmatter + именованные разделы.
#
# Поддерживает два способа оформления раздела, реально встречающихся в файлах:
#   1. H1-заголовок:        "# Атрибутный состав сущности"
#   2. Жирный inline-текст: "**Атрибутный состав сущности:**" (как в шаблонах)
#
# H2/H3 и прочие подзаголовки НЕ считаются границами раздела — они часть
# содержимого текущего раздела верхнего уровня. Это соответствует структуре
# шаблона требований Эко, где значимые разделы всегда на верхнем уровне.

import re
import logging
from typing import Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

logger = logging.getLogger(__name__)

# Граница раздела #1 — H1-заголовок: строка, начинающаяся с одного '#' и пробела.
# Важно: ровно один '#', не '##' — поэтому в шаблоне (?!#).
_H1_RE = re.compile(r"^\#(?!\#)\s+(?P<title>.+?)\s*$")

# Граница раздела #2 — жирный inline-заголовок вида "**Название:**" в начале строки.
# Двоеточие внутри ** обязательно (так оформлены разделы в шаблонах dataModel).
# Допускаем хвост после "**" — в шаблоне за "**Описание сущности:**" сразу идёт текст.
_BOLD_HEADER_RE = re.compile(r"^\*\*(?P<title>[^*]+?):\*\*(?P<rest>.*)$")

# Маркер "информативного" служебного раздела шаблона — не контент, а инструкция
# аналитику. Такие разделы генератор карточек должен игнорировать.
_INFORMATIVE_RE = re.compile(r"информативн", re.IGNORECASE)


def split_frontmatter(text: str) -> Tuple[Dict, str]:
    """Отделяет YAML-frontmatter от тела документа.

    Возвращает (frontmatter_dict, body). Если frontmatter отсутствует или не
    парсится — возвращает ({}, исходный_текст).
    """
    if not text.startswith("---"):
        return {}, text

    # Разбиваем по разделителям '---'. Первый '---' в начале, второй закрывает FM.
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    fm_raw, body = parts[1], parts[2]

    meta: Dict = {}
    if yaml is not None:
        try:
            meta = yaml.safe_load(fm_raw) or {}
        except yaml.YAMLError as e:
            logger.warning("[split_frontmatter] YAML parse error: %s", e)
            meta = {}

    # Ведущие пустые строки тела убираем, но не трогаем значимое содержимое.
    return meta, body.lstrip("\n")


def _normalize_title(title: str) -> str:
    """Нормализует заголовок раздела для сопоставления: lower + схлопывание пробелов."""
    return re.sub(r"\s+", " ", title.strip()).lower()


class Section:
    """Один раздел документа верхнего уровня."""

    __slots__ = ("title", "title_norm", "content", "informative", "kind")

    def __init__(self, title: str, kind: str):
        self.title = title.strip()
        self.title_norm = _normalize_title(title)
        self.content: List[str] = []          # строки содержимого раздела
        self.informative = bool(_INFORMATIVE_RE.search(title))
        self.kind = kind                       # "h1" | "bold" — как был размечен

    @property
    def body(self) -> str:
        return "\n".join(self.content).strip("\n")

    def __repr__(self) -> str:
        flag = " [informative]" if self.informative else ""
        return f"<Section {self.kind}:'{self.title}'{flag} {len(self.body)} chars>"


def parse_sections(body: str) -> List[Section]:
    """Разбивает тело документа на разделы верхнего уровня.

    Структуру документа несёт ОДИН из двух способов разметки, не оба сразу:
      • Если в документе есть хотя бы один H1-заголовок — разделы верхнего уровня
        задаются именно H1, а жирный inline ("**...:**") трактуется как внутренний
        подзаголовок и остаётся в содержимом раздела (НЕ разрывает его).
      • Если H1 нет совсем — роль разделов берёт на себя жирный inline-заголовок
        (так оформлены шаблоны, например dataModel).

    Это правило ("структура держится либо на H1, либо на жирном, но не на смеси")
    подтверждено на реальных файлах: документы с H1 используют жирный текст только
    как подзаголовки внутри H1-разделов.

    Содержимое до первого заголовка сохраняется псевдо-разделом kind="preamble",
    если оно непустое.
    """
    # Определяем режим разметки: есть ли H1 в документе.
    has_h1 = any(_H1_RE.match(line) for line in body.splitlines())

    sections: List[Section] = []
    current: Optional[Section] = None
    preamble: List[str] = []

    for line in body.splitlines():
        h1 = _H1_RE.match(line)
        if h1:
            current = Section(h1.group("title"), kind="h1")
            sections.append(current)
            continue

        # Жирный inline считается границей раздела ТОЛЬКО когда в документе нет H1.
        if not has_h1:
            bold = _BOLD_HEADER_RE.match(line)
            if bold:
                current = Section(bold.group("title"), kind="bold")
                sections.append(current)
                rest = bold.group("rest").strip()
                if rest:
                    current.content.append(rest)
                continue

        if current is None:
            preamble.append(line)
        else:
            current.content.append(line)

    # Непустая преамбула сохраняется отдельным разделом в начало.
    if any(l.strip() for l in preamble):
        pre = Section("", kind="preamble")
        pre.content = preamble
        sections.insert(0, pre)

    return sections


def parse_document(text: str) -> Tuple[Dict, List[Section]]:
    """Полный разбор документа: frontmatter + список разделов."""
    meta, body = split_frontmatter(text)
    sections = parse_sections(body)
    return meta, sections


def find_sections_by_synonyms(
    sections: List[Section],
    synonyms: List[str],
) -> List[Section]:
    """Возвращает разделы, чей нормализованный заголовок совпадает с одним из
    синонимов (тоже нормализованных). Информативные служебные разделы пропускаются.

    Совпадение — по точному равенству нормализованных строк. Это сознательно
    строго: 'описание эф' совпадёт с 'Описание ЭФ', но не с 'Описание ЭФ Клиента'.
    Управление вариативностью — через список синонимов, не через нечёткость.
    """
    wanted = {_normalize_title(s) for s in synonyms}
    result = []
    for sec in sections:
        if sec.informative:
            continue
        if sec.title_norm in wanted:
            result.append(sec)
    return result