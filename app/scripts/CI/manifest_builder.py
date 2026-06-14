# app/scripts/CI/manifest_builder.py

# (проход 1) — отвечает за «где что лежит»: строит манифест экспортируемых элементов из тех же распарcенных документов.

# Шаг 4 генератора карточек: построение манифеста сервиса.
#
# Манифест — машиночитаемый индекс публичных элементов сервиса. Используется
# резолвером ссылок {{сервис:Имя}} (и людьми через MkDocs, и агентами при ревью),
# а также проходом 2 (card_link_resolver) для перенаправления ссылок между
# карточками.
#
# Принцип адресации — ЕДИНЫЙ с остальным проектом: url элемента строится из его
# doc_id ровно так же, как doc_id строится в migrate_confluence_tree
# (путь относительно корня без расширения, прямые слеши). Это даёт один источник
# истины: меняется конвенция doc_id — url следует за ней автоматически.
#
# Структура манифеста зафиксирована в "Архитектура-межсервисных-ссылок-DocAsCode-PoC":
#   шапка: service_code, generated_at
#   элементы: name, kind (card|swagger), doc_id, url

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from section_parser import parse_document

logger = logging.getLogger(__name__)


# kind в манифесте берётся напрямую из resolve_target в card_sections.json —
# единый словарь сквозь всю систему (конфиг, манифест, резолвер говорят одинаково):
#   card    → ссылка ведёт на публичную карточку
#   swagger → ссылка ведёт на OpenAPI-операцию
_VALID_KINDS = ("card", "swagger")


@dataclass
class ManifestEntry:
    """Одна запись манифеста — публичный элемент сервиса."""
    name: str
    kind: str            # card | swagger
    doc_id: str
    url: str

    def as_dict(self) -> Dict:
        return {"name": self.name, "kind": self.kind, "doc_id": self.doc_id, "url": self.url}


@dataclass
class ManifestBuildResult:
    """Итог построения манифеста с диагностикой."""
    service_code: Optional[str] = None
    entries: List[ManifestEntry] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)   # doc_id, не попавшие в манифест


def _doc_id_to_url(doc_id: str, kind: str, swagger_base: Optional[str] = None,
                   swagger_url: Optional[str] = None) -> str:
    """Строит url элемента манифеста из doc_id, единообразно с конвенцией doc_id.

    Для card (карточка): url = doc_id + ".md" — путь карточки в dbo-registry,
        относительно корня реестра, прямые слеши (так же, как doc_id в проекте).
    Для swagger (операция): url = явный swagger_url, если задан в frontmatter;
        иначе собирается из swagger_base + doc_id как fallback (переходный период).
    """
    if kind == "swagger":
        if swagger_url:
            return swagger_url
        if swagger_base:
            # Fallback: операция адресуется по doc_id в общем swagger-портале.
            return f"{swagger_base.rstrip('/')}/#/{doc_id}"
        # Нет swagger-адреса — оставляем doc_id как маркер (резолвер предупредит).
        return doc_id
    # card → путь карточки относительно корня реестра, прямые слеши.
    return f"{doc_id}.md"


def build_entry(
    meta: Dict,
    config: Dict,
    swagger_base: Optional[str] = None,
) -> Optional[ManifestEntry]:
    """Строит запись манифеста из frontmatter одного документа.

    Возвращает None, если элемент не публичен (нет правила для типа, или тип
    помечен как непубличный на PoC).
    """
    name = (meta.get("title") or "").strip()
    doc_id = (meta.get("doc_id") or "").strip()
    rtype = meta.get("requirement_type")

    if not name or not doc_id or not rtype:
        return None

    type_rule = config.get("types", {}).get(rtype)
    if not type_rule:
        return None

    resolve_target = type_rule.get("resolve_target")
    kind = resolve_target if resolve_target in _VALID_KINDS else None
    if not kind:
        return None

    # На PoC в манифест попадают только элементы, которые реально публичны:
    #  • card с generate_card=true (есть карточка), либо
    #  • swagger (есть/будет swagger).
    # Непубличные типы (process/control/... с generate_card=false и target=card)
    # в манифест не включаются — ссылаться на них извне нельзя.
    if kind == "card" and not type_rule.get("generate_card", False):
        return None

    swagger_url = meta.get("swagger_url")  # опциональное явное поле во frontmatter
    url = _doc_id_to_url(doc_id, kind, swagger_base=swagger_base, swagger_url=swagger_url)

    return ManifestEntry(name=name, kind=kind, doc_id=doc_id, url=url)


def build_manifest(
    doc_paths: List[str],
    config: Dict,
    service_code: Optional[str] = None,
    swagger_base: Optional[str] = None,
) -> ManifestBuildResult:
    """Строит манифест сервиса из списка путей к .md документам.

    Args:
        doc_paths: пути к .md документам требований сервиса.
        config: загруженный card_sections.json.
        service_code: код сервиса для шапки манифеста; если None — берётся из
            frontmatter первого документа.
        swagger_base: базовый URL swagger-портала (для swagger-элементов без явного
            swagger_url). Опционально, переходный период.

    Returns:
        ManifestBuildResult с записями и диагностикой.
    """
    result = ManifestBuildResult(service_code=service_code)
    seen_names: Dict[str, str] = {}   # name -> doc_id, для контроля уникальности

    for path in doc_paths:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except Exception as e:
            result.warnings.append(f"{path}: не удалось прочитать — {e}")
            continue

        meta, _ = parse_document(text)

        if result.service_code is None:
            result.service_code = meta.get("service_code")

        entry = build_entry(meta, config, swagger_base=swagger_base)
        if entry is None:
            result.skipped.append(meta.get("doc_id") or path)
            continue

        # Контроль уникальности name в пределах сервиса (гарантия из правил именования).
        if entry.name in seen_names and seen_names[entry.name] != entry.doc_id:
            result.warnings.append(
                f"Дубль имени '{entry.name}': doc_id '{seen_names[entry.name]}' и "
                f"'{entry.doc_id}' — резолв {{{{...}}}} станет неоднозначным"
            )
        seen_names[entry.name] = entry.doc_id

        result.entries.append(entry)

    return result


def render_manifest(result: ManifestBuildResult) -> str:
    """Сериализует манифест в YAML (шапка + список элементов)."""
    doc = {
        "service_code": result.service_code,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elements": [e.as_dict() for e in result.entries],
    }
    if yaml is not None:
        return yaml.dump(doc, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return json.dumps(doc, ensure_ascii=False, indent=2)  # pragma: no cover