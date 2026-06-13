# app/scripts/CI/card_link_resolver.py

# (проход 2) — отвечает за «куда ведут ссылки»: единственное место, где живёт логика сохранить/перенаправить/расплющить,
# и единственное, что зависит от манифеста.

# Шаг 5 генератора карточек: ПРОХОД 2 — разрешение ссылок в карточках.
#
# (проход 2) Запускается ПОСЛЕ прохода 1 (генерация карточек + построение манифеста), когда
# манифест сервиса уже известен целиком. Единственное место, где живёт логика
# разрешения ссылок — что сохранить, что перенаправить, что расплющить.
#
# Четыре класса ссылок (см. "Архитектура-межсервисных-ссылок-DocAsCode-PoC"):
#   1. Внешний URL (http://, https://)        → сохранить как есть
#   2. {{сервис:Имя}}                          → сохранить как есть (межсервисная)
#   3. Цель ЕСТЬ в манифесте (публична)        → перенаправить на её карточку/url
#   4. Цель НЕ в манифесте / confluence://      → расплющить в текст
#
# Принцип адресации ЕДИНЫЙ с проектом: doc_id цели вычисляется из относительного
# пути ссылки так же, как doc_id строится в migrate_confluence_tree (путь от корня,
# прямые слеши, без расширения).

import logging
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# --- Регэкспы ссылок (перенесены из card_generator, с фиксом вложенных скобок) ---

# Markdown-ссылка [текст](цель). Текст может содержать экранированные \[ \] и
# вложенные [ ] (как в "[\[КК_ЛК\] Заявка...]"): нежадный захват до "](".
_MD_LINK_RE = re.compile(r"\[((?:\\.|[^\]]|\](?!\())*?)\]\(([^)]+)\)")

# HTML-ссылка <a href="цель">текст</a>.
_HTML_LINK_RE = re.compile(r'<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)

# Абсолютный http(s)-URL — внешняя ссылка (класс 1).
_ABSOLUTE_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# Межсервисная ссылка {{сервис:Имя}} (класс 2). Внутри карточки может встретиться
# уже резолвенная межсервисная ссылка — её не трогаем.
_INTERSERVICE_RE = re.compile(r"\{\{[^}]+\}\}")

# Артефакты нерезолвенных ссылок (класс 4) — точно расплющиваются.
_NONRESOLVABLE_SCHEMES = ("confluence://", "confluence-download://", "confluence-attachment://")


@dataclass
class ResolveStats:
    """Диагностика прохода по одной карточке."""
    kept_external: int = 0
    kept_interservice: int = 0
    redirected: int = 0
    flattened: int = 0
    details: List[str] = field(default_factory=list)


def _norm_doc_id(s: str) -> str:
    """Нормализует doc_id/путь для сравнения: убирает .md, прямые слеши."""
    s = s.strip().replace("\\", "/")
    if s.endswith(".md"):
        s = s[:-3]
    return s


def _resolve_target_doc_id(source_doc_id: str, rel_target: str) -> Optional[str]:
    """Вычисляет doc_id цели из относительного пути ссылки.

    Единообразно с конвенцией doc_id (путь от корня, прямые слеши, без расширения):
    берём директорию source_doc_id, применяем относительный путь ссылки,
    нормализуем '..' и './'. Возвращает doc_id цели или None, если путь не
    относительный (а, например, схема confluence://).

    Пример:
      source_doc_id = "cc/A/B/Лимит"
      rel_target    = "../[КК_ЛК]-Заявка.md"
      → "cc/A/[КК_ЛК]-Заявка"
    """
    t = rel_target.strip().replace("\\", "/")

    # Не относительный путь к файлу — не наш случай (внешние URL и схемы
    # обрабатываются отдельно до вызова этой функции).
    if _ABSOLUTE_URL_RE.match(t) or "://" in t:
        return None

    t = t[:-3] if t.endswith(".md") else t

    # Директория источника = doc_id без последнего сегмента (имя файла).
    source_dir = PurePosixPath(source_doc_id).parent
    try:
        combined = (source_dir / t)
        # PurePosixPath не схлопывает '..' сам — делаем это вручную.
        resolved_parts: List[str] = []
        for part in combined.parts:
            if part == "..":
                if resolved_parts:
                    resolved_parts.pop()
            elif part in (".", ""):
                continue
            else:
                resolved_parts.append(part)
        return "/".join(resolved_parts)
    except Exception as e:
        logger.debug("[_resolve_target_doc_id] не удалось разрешить '%s' от '%s': %s",
                     rel_target, source_doc_id, e)
        return None


class ManifestIndex:
    """Индекс манифеста для быстрого поиска цели по doc_id.

    Манифест передаётся как список записей (dict с ключами name, kind, doc_id, url).
    Может объединять несколько манифестов (свой сервис + внешние из dbo-registry).
    """

    def __init__(self, entries: List[Dict]):
        self._by_doc_id: Dict[str, Dict] = {}
        for e in entries:
            did = _norm_doc_id(e.get("doc_id", ""))
            if did:
                self._by_doc_id[did] = e

    def lookup_by_doc_id(self, doc_id: str) -> Optional[Dict]:
        return self._by_doc_id.get(_norm_doc_id(doc_id))


def _classify_and_resolve(
    link_text: str,
    target: str,
    source_doc_id: str,
    manifest: ManifestIndex,
    stats: ResolveStats,
) -> Tuple[str, bool]:
    """Определяет класс ссылки и возвращает (новая_цель_или_текст, is_link).

    is_link=True  → результат это цель ссылки (ссылку сохраняем/перенаправляем).
    is_link=False → результат это текст (ссылку расплющиваем).
    """
    t = target.strip()

    # Класс 1: внешний URL — сохраняем.
    if _ABSOLUTE_URL_RE.match(t):
        stats.kept_external += 1
        return target, True

    # Класс 4a: нерезолвенные схемы confluence:// — расплющиваем.
    if any(t.startswith(scheme) for scheme in _NONRESOLVABLE_SCHEMES):
        stats.flattened += 1
        return link_text, False

    # Класс 3: относительная ссылка на файл — пытаемся найти цель в манифесте.
    target_doc_id = _resolve_target_doc_id(source_doc_id, t)
    if target_doc_id:
        entry = manifest.lookup_by_doc_id(target_doc_id)
        if entry:
            # Цель публична — перенаправляем на её url из манифеста.
            stats.redirected += 1
            stats.details.append(f"→ {entry['name']} ({entry['url']})")
            return entry["url"], True
        # Класс 4b: цель не в манифесте (непубличный элемент) — расплющиваем.
        stats.flattened += 1
        return link_text, False

    # Не смогли разобрать как относительный путь — безопасно расплющиваем.
    stats.flattened += 1
    return link_text, False


def resolve_links_in_card(
    card_text: str,
    source_doc_id: str,
    manifest: ManifestIndex,
) -> Tuple[str, ResolveStats]:
    """Разрешает все ссылки в тексте карточки по четырём классам.

    {{...}} (класс 2) сохраняются нетронутыми. Markdown- и HTML-ссылки
    классифицируются и либо сохраняются, либо перенаправляются, либо
    расплющиваются.
    """
    stats = ResolveStats()

    # Класс 2: считаем {{...}} (они проходят насквозь — re.sub их не трогает).
    stats.kept_interservice = len(_INTERSERVICE_RE.findall(card_text))

    def _md_repl(m: re.Match) -> str:
        link_text, target = m.group(1), m.group(2)
        new_target, is_link = _classify_and_resolve(
            link_text, target, source_doc_id, manifest, stats
        )
        return f"[{link_text}]({new_target})" if is_link else link_text

    def _html_repl(m: re.Match) -> str:
        target, link_text = m.group(1), m.group(2)
        new_target, is_link = _classify_and_resolve(
            link_text, target, source_doc_id, manifest, stats
        )
        return f'<a href="{new_target}">{link_text}</a>' if is_link else link_text

    text = _MD_LINK_RE.sub(_md_repl, card_text)
    text = _HTML_LINK_RE.sub(_html_repl, text)
    return text, stats