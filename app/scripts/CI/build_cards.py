# app/scripts/CI/build_cards.py
#
# Шаг 6: оркестратор пайплайна генерации публичных карточек и манифеста сервиса.
#
# Связывает готовые модули в единый процесс (Вариант А — два прохода):
#
#   ПРОХОД 1 (полный, по ВСЕМ документам сервиса):
#     • manifest_builder.build_entry  → строка манифеста (если элемент публичен)
#     • card_generator.generate_card  → карточка с СЫРЫМИ ссылками (если есть карточка)
#     Полнота прохода 1 обязательна: резолвер прохода 2 должен видеть весь манифест,
#     иначе ссылки на неизменённые публичные элементы деградируют (расплющиваются).
#
#   ПРОХОД 2 (по сгенерированным карточкам):
#     • card_link_resolver.resolve_links_in_card → разрешить ссылки по 4 классам
#     Выполняется ПОСЛЕ построения полного манифеста.
#
# ВЫХОД (раскладка в dbo-registry):
#     <output_dir>/manifest.yaml          — манифест сервиса
#     <output_dir>/<doc_id>.md            — карточки по их полному doc_id-пути
#
# Использование:
#   python build_cards.py <service_dir> <output_dir> [--service CODE]
#       [--config card_sections.json] [--swagger-base URL]
#
# Пример:
#   python build_cards.py conf-requirements/cc dbo-registry/cc \
#       --swagger-base https://swagger.bank/cc/v1

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from card_generator import load_card_config, generate_card, CardResult
from manifest_builder import build_manifest, render_manifest, ManifestBuildResult, card_rel_url
from card_link_resolver import ManifestIndex, resolve_links_in_card
from section_parser import split_frontmatter

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


@dataclass
class PipelineReport:
    """Сводка прогона пайплайна для журнала."""
    service_code: Optional[str] = None
    docs_total: int = 0
    docs_of_service: int = 0
    cards_generated: int = 0
    cards_skipped: int = 0
    manifest_entries: int = 0
    links_redirected: int = 0
    links_flattened: int = 0
    links_kept_external: int = 0
    links_kept_interservice: int = 0
    warnings: List[str] = field(default_factory=list)


def discover_service_docs(service_dir: Path, service_code: Optional[str]) -> List[Path]:
    """Находит .md документы, относящиеся к сервису.

    Обходит все .md в каталоге рекурсивно, фильтрует по service_code из
    frontmatter (на случай чужих файлов в дереве). Если service_code не задан —
    берёт все .md с непустым service_code и фиксирует первый встреченный как
    код сервиса (контролируя, что в каталоге один сервис).
    """
    all_md = sorted(service_dir.rglob("*.md"))
    docs: List[Path] = []

    for path in all_md:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("  ⚠ не прочитан %s: %s", path, e)
            continue

        meta, _ = split_frontmatter(text)
        svc = meta.get("service_code")
        if not svc:
            continue  # не документ требований (нет frontmatter/сервиса)

        if service_code is None or svc == service_code:
            docs.append(path)

    return docs


def run_pipeline(
    service_dir: str,
    output_dir: str,
    config: Dict,
    service_code: Optional[str] = None,
    swagger_base: Optional[str] = None,
) -> PipelineReport:
    """Полный прогон: проход 1 (карточки + манифест) → проход 2 (резолв ссылок)."""
    service_path = Path(service_dir)
    out_path = Path(output_dir)
    report = PipelineReport(service_code=service_code)

    # --- Сбор документов сервиса ---
    docs = discover_service_docs(service_path, service_code)
    report.docs_of_service = len(docs)
    if not docs:
        report.warnings.append(f"В {service_dir} не найдено документов сервиса")
        logger.warning("Нет документов сервиса в %s", service_dir)
        return report

    # --- ПРОХОД 1: манифест (полный) ---
    doc_paths = [str(p) for p in docs]
    manifest_result: ManifestBuildResult = build_manifest(
        doc_paths, config, service_code=service_code, swagger_base=swagger_base,
        service_dir=str(service_path),
    )
    report.service_code = manifest_result.service_code
    report.manifest_entries = len(manifest_result.entries)
    report.warnings.extend(manifest_result.warnings)

    # --- ПРОХОД 1: карточки (сырые ссылки) ---
    # Держим карточки в памяти как (source_path, doc_id, card_text) до прохода 2.
    # source_path нужен для зеркального расположения карточки (doc_id больше не путь).
    raw_cards: List[tuple] = []
    for path in doc_paths:
        result: CardResult = generate_card(path, config)
        report.warnings.extend(result.warnings)
        if result.generated:
            raw_cards.append((path, result.card_text))
            report.cards_generated += 1
        else:
            report.cards_skipped += 1

    # --- ПРОХОД 2: резолв ссылок по полному манифесту ---
    index = ManifestIndex([e.as_dict() for e in manifest_result.entries])

    for path, card_text in raw_cards:
        # Карточка лежит зеркально пути источника (тот же относительный путь, что и
        # url в манифесте — общий card_rel_url). Этот путь передаём резолверу как
        # расположение карточки-источника для резолва относительных ссылок.
        card_rel = card_rel_url(path, service_path)
        resolved_text, stats = resolve_links_in_card(card_text, card_rel, index)
        report.links_redirected += stats.redirected
        report.links_flattened += stats.flattened
        report.links_kept_external += stats.kept_external
        report.links_kept_interservice += stats.kept_interservice

        card_path = out_path / card_rel
        card_path.parent.mkdir(parents=True, exist_ok=True)
        card_path.write_text(resolved_text, encoding="utf-8")

    # --- Запись манифеста ---
    out_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / "manifest.yaml"
    manifest_path.write_text(render_manifest(manifest_result), encoding="utf-8")

    return report


def _log_report(report: PipelineReport, output_dir: str) -> None:
    logger.info("")
    logger.info("=" * 60)
    logger.info("Пайплайн карточек завершён")
    logger.info("  Сервис:                    %s", report.service_code)
    logger.info("  Документов сервиса:        %d", report.docs_of_service)
    logger.info("  Карточек сгенерировано:    %d", report.cards_generated)
    logger.info("  Карточек пропущено:        %d", report.cards_skipped)
    logger.info("  Записей в манифесте:        %d", report.manifest_entries)
    logger.info("  Ссылок:")
    logger.info("    перенаправлено на карточки: %d", report.links_redirected)
    logger.info("    сохранено внешних URL:      %d", report.links_kept_external)
    logger.info("    сохранено {{...}}:          %d", report.links_kept_interservice)
    logger.info("    расплющено в текст:         %d", report.links_flattened)
    logger.info("  Выход: %s", output_dir)
    if report.warnings:
        logger.info("")
        logger.info("  Предупреждения (%d) — что стоит починить аналитикам:", len(report.warnings))
        for w in report.warnings:
            logger.info("    ⚠ %s", w)
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Генерация публичных карточек и манифеста сервиса (Doc as Code).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Пример:\n"
            "  python build_cards.py conf-requirements/cc dbo-registry/cc \\\n"
            "      --swagger-base https://swagger.bank/cc/v1\n"
        ),
    )
    parser.add_argument("service_dir", help="Каталог с .md документами сервиса")
    parser.add_argument("output_dir", help="Каталог вывода (dbo-registry/<сервис>)")
    parser.add_argument("--service", default=None,
                        help="Код сервиса (если не задан — берётся из frontmatter)")
    parser.add_argument("--config", default="card_sections.json",
                        help="Путь к card_sections.json")
    parser.add_argument("--swagger-base", default=None,
                        help="Базовый URL swagger-портала для operation-элементов")
    args = parser.parse_args()

    config = load_card_config(args.config)

    logger.info("Генерация карточек для каталога: %s", args.service_dir)
    report = run_pipeline(
        service_dir=args.service_dir,
        output_dir=args.output_dir,
        config=config,
        service_code=args.service,
        swagger_base=args.swagger_base,
    )
    _log_report(report, args.output_dir)

    # Ненулевой код выхода, если были предупреждения — CI может на это реагировать.
    sys.exit(1 if report.warnings else 0)


if __name__ == "__main__":
    main()