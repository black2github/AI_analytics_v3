# app/scripts/CI/card_generator.py

# (проход 1) — отвечает только за «что публично»: отбор разделов, сборка карточки, frontmatter.
# Ничего не знает о ссылках. Детерминирован, тестируется на одном документе.

# Шаг 3 генератора карточек: сборка публичной markdown-карточки из мигрированного
# документа требований.
#
# Карточка — это урезанная публичная проекция документа: только разрешённые
# (публичные) разделы согласно card_sections.json, плюс служебный frontmatter,
# помечающий файл как зеркало (его нельзя править руками — он перегенерируется).
#
# Вход:  путь к .md документу + загруженная конфигурация card_sections.json
# Выход: текст карточки (.md) либо None, если карточка для типа не генерируется
#        или публичных разделов не нашлось.
#
# Зависит от section_parser (Шаг 1).

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from section_parser import parse_document, find_sections_by_synonyms, Section

logger = logging.getLogger(__name__)


# Поля исходного frontmatter, переносимые в карточку как есть. Остальное
# (owner, author, jira_id, история и т.п.) в публичную карточку не идёт.
_CARRIED_FRONTMATTER_FIELDS = (
    "doc_id",
    "title",
    "requirement_type",
    "service_code",
)


@dataclass
class CardResult:
    """Результат попытки сгенерировать карточку для одного документа."""
    source_path: str
    requirement_type: Optional[str] = None
    generated: bool = False
    card_text: Optional[str] = None
    sections_used: List[str] = field(default_factory=list)
    resolve_target: Optional[str] = None        # card | swagger
    # Диагностика для журнала (то, что поможет аналитику починить документ):
    warnings: List[str] = field(default_factory=list)
    skipped_reason: Optional[str] = None        # почему карточка не создана


def load_card_config(path: str) -> Dict:
    """Загружает card_sections.json."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Поля исходного frontmatter, переносимые в карточку как есть. Остальное
# (owner, author, jira_id, история и т.п.) в публичную карточку не идёт.
_CARRIED_FRONTMATTER_FIELDS = (
    "doc_id",
    "title",
    "requirement_type",
    "service_code",
)


def _build_card_frontmatter(meta: Dict) -> Dict:
    """Формирует frontmatter карточки: перенесённые поля источника + служебные.

    Служебные поля помечают карточку как генерируемое зеркало:
      • card: true              — это карточка, не оригинал
      • generated: true         — сгенерирована автоматически
      • do_not_edit: true       — править руками нельзя (перегенерируется)
      • source_doc_id           — откуда взята (для трассировки)
    """
    fm: Dict = {}
    for key in _CARRIED_FRONTMATTER_FIELDS:
        if meta.get(key):
            fm[key] = meta[key]

    fm["card"] = True
    fm["generated"] = True
    fm["do_not_edit"] = True
    if meta.get("doc_id"):
        fm["source_doc_id"] = meta["doc_id"]

    return fm


def _render_frontmatter(fm: Dict) -> str:
    """Сериализует frontmatter в YAML-блок между '---'."""
    if yaml is not None:
        body = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
    else:  # pragma: no cover — на проде yaml есть
        body = "".join(f"{k}: {v}\n" for k, v in fm.items())
    return f"---\n{body}---\n"


def _render_section(sec: Section) -> str:
    """Рендерит раздел в карточку как H1 + содержимое (унифицируем оформление).

    Даже если в источнике раздел был жирным inline-заголовком, в карточке он
    становится H1 — карточка имеет единообразную структуру независимо от того,
    как был оформлен оригинал.

    ВАЖНО (Вариант А пайплайна): ссылки здесь НЕ разрешаются. Проход 1 (генерация)
    собирает карточку с сырыми ссылками как в исходнике. Разрешение ссылок
    (сохранить / перенаправить на карточку / расплющить) выполняет отдельный
    проход 2 (card_link_resolver), которому уже доступен полный манифест сервиса.
    """
    return f"# {sec.title}\n\n{sec.body}\n"


def generate_card(
    source_path: str,
    config: Dict,
    use_transitional: bool = False,
) -> CardResult:
    """Генерирует публичную карточку для одного документа.

    Args:
        source_path: путь к .md документу требований.
        config: загруженный card_sections.json.
        use_transitional: если True — для swagger-типов (function/integration)
            на переходный период использовать transitional_sections и всё же
            сгенерировать карточку. По умолчанию False (целевое поведение:
            для swagger-типов карточка не генерируется).

    Returns:
        CardResult с текстом карточки или причиной пропуска.
    """
    text = Path(source_path).read_text(encoding="utf-8")
    meta, sections = parse_document(text)
    rtype = meta.get("requirement_type")

    result = CardResult(source_path=source_path, requirement_type=rtype)

    # 1) Тип определён?
    if not rtype:
        result.skipped_reason = "no requirement_type in frontmatter"
        result.warnings.append(f"{source_path}: не определён requirement_type — карточка пропущена")
        return result

    # 2) Есть правило для типа?
    type_rule = config.get("types", {}).get(rtype)
    if not type_rule:
        result.skipped_reason = f"no rule for type '{rtype}'"
        result.warnings.append(f"{source_path}: нет правила для типа '{rtype}' — карточка пропущена")
        return result

    result.resolve_target = type_rule.get("resolve_target")

    # 3) Карточка вообще генерируется для этого типа?
    generate = type_rule.get("generate_card", False)
    synonyms = type_rule.get("public_sections", [])

    if not generate:
        if use_transitional and type_rule.get("transitional_sections"):
            synonyms = type_rule["transitional_sections"]
            logger.info("[generate_card] %s: type '%s' → переходный режим карточки", source_path, rtype)
        else:
            result.skipped_reason = f"generate_card=false for type '{rtype}' (resolve via {result.resolve_target})"
            return result

    # 4) Находим публичные разделы
    found = find_sections_by_synonyms(sections, synonyms)
    if not found:
        result.skipped_reason = "no public sections found"
        present = [s.title for s in sections if s.title and not s.informative]
        result.warnings.append(
            f"{source_path}: публичные разделы не найдены для типа '{rtype}'. "
            f"Ожидались (синонимы): {synonyms}. Фактические разделы: {present}"
        )
        return result

    # 5) Собираем карточку
    fm = _build_card_frontmatter(meta)
    parts = [_render_frontmatter(fm), ""]
    for sec in found:
        parts.append(_render_section(sec))

    result.generated = True
    result.card_text = "\n".join(parts).rstrip() + "\n"
    result.sections_used = [s.title for s in found]

    return result