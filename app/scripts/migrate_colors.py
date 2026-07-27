# app/scripts/migrate_colors.py
#
# Модуль 1 (срез 1a), ТЗ п. 4.9-4.10: режим «только отчёт» миграции цвета.
#
# Строит по набору страниц Confluence (rendered-view HTML) карту «цвет → задача», обходит
# тело каждой страницы, классифицирует все встреченные цвета и формирует:
#   • migration-manifest.yaml   — реестр мигрировавших задач (ТЗ п. 4.9);
#   • migration-colors-report.json + .md — всё, что требует ручного разбора (ТЗ п. 4.10).
#
# ВАЖНО: этот срез НЕ пишет маркеры CriticMarkup в markdown (ТЗ п. 4.3: «Первый прогон
# выполняется в режиме только отчёт, без записи файлов»). Эмиссия маркеров — срез 1b.
#
# Вход первого прогона — каталог сохранённых .html (напр. debug/html); позже сюда же
# подключается штатный загрузчик Confluence (--http) без изменения ядра.

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from app.color_map import build_color_task_map, survey_body_colors


def aggregate(pages: List[Tuple[str, str]], service: str, migrated_at: str) -> Tuple[dict, dict]:
    """Обрабатывает страницы и возвращает (manifest, report).

    pages — список (имя_страницы, raw_html). Карта строится ЗАНОВО для каждой страницы
    (ТЗ п. 4.2.д): один и тот же цвет на разных страницах может означать разные задачи.
    """
    pages_without_history: List[str] = []
    collisions: List[dict] = []
    jira_unextractable: List[dict] = []
    unresolved_placeholders: List[dict] = []
    # task_id -> агрегат по всем страницам
    tasks: Dict[str, dict] = {}
    # нормализованный цвет -> агрегированная сводка (для диагностики набора black_colors)
    color_summary: Dict[str, dict] = {}

    colored_fragments_total = 0

    for name, raw_html in pages:
        result = build_color_task_map(raw_html)
        if result.no_history:
            pages_without_history.append(name)

        for col in result.collisions:
            collisions.append({"page": name, **col})
        for u in result.unresolved_jira:
            jira_unextractable.append({"page": name, "color": u["color"]})

        survey = survey_body_colors(raw_html, result)
        for color, info in survey.items():
            cls = info["classification"]
            cnt = info["count"]
            # Диагностика набора цветов (ТЗ п. 4.3): агрегируем частоты по всему прогону.
            agg = color_summary.setdefault(
                color, {"color": color, "count": 0, "classification": cls,
                        "task": info.get("task")})
            agg["count"] += cnt

            if cls == "black":
                continue
            colored_fragments_total += cnt

            task_id = info["task"]
            if cls == "unknown":
                unresolved_placeholders.append({
                    "placeholder": task_id, "color": color, "page": name,
                    "count": cnt, "reason": info.get("reason"),
                })
                confidence = "unresolved"
            else:
                confidence = result.confidence.get(color, "high")

            entry = tasks.setdefault(task_id, {
                "color": color, "confidence": confidence,
                "pages": set(), "markers": 0})
            entry["pages"].add(name)
            entry["markers"] += cnt
            # confidence 'low' (коллизия) приоритетнее 'high' в агрегате.
            if confidence == "low":
                entry["confidence"] = "low"

    # Приводим множества к спискам и стабилизируем порядок.
    manifest_tasks = {}
    for task_id in sorted(tasks):
        e = tasks[task_id]
        manifest_tasks[task_id] = {
            "color": e["color"],
            "confidence": e["confidence"],
            "pages": sorted(e["pages"]),
            "markers": e["markers"],
        }

    manifest = {
        "migrated_at": migrated_at,
        "service": service,
        "tasks": manifest_tasks,
    }

    positions_manual_review = (
        len(unresolved_placeholders) + len(collisions) + len(jira_unextractable))

    report = {
        "migrated_at": migrated_at,
        "service": service,
        "stats": {
            "pages_processed": len(pages),
            "colored_fragments_total": colored_fragments_total,
            "positions_manual_review": positions_manual_review,
            "nested_flattened": 0,
        },
        "pages_without_history": pages_without_history,
        "unresolved_placeholders": unresolved_placeholders,
        "collisions": collisions,
        "jira_unextractable": jira_unextractable,
        "nested_flattened": [],  # заполняется командой migrate (ТЗ п. 4.5/4.10)
        "color_summary": sorted(color_summary.values(),
                                key=lambda c: (-c["count"], c["color"])),
    }
    return manifest, report


def _safe_name(name: str) -> str:
    """Безопасное имя файла .md из имени страницы."""
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip() or "page"


def _render_md(title: str, body: str) -> str:
    """Минимальный .md: frontmatter с заголовком + тело с маркерами CriticMarkup."""
    fm = f"---\ntitle: {json.dumps(title, ensure_ascii=False)}\nsource: CONFLUENCE\n---\n\n"
    return fm + body


def migrate_pages(pages, service, migrated_at, out_dir):
    """Боевой проход миграции: пишет .md с маркерами и собирает манифест+отчёт.

    Для каждой страницы: карта «цвет→задача» → critic-экстракция → запись <имя>.md.
    Уплощённые вложенные конструкции (ТЗ п. 4.5) собираются из экстрактора в отчёт.
    """
    from app.color_map import build_color_task_map
    from app.content_extractor import create_critic_extractor

    manifest, report = aggregate(pages, service, migrated_at)

    out_dir.mkdir(parents=True, exist_ok=True)
    nested = []
    for name, raw_html in pages:
        cmap = build_color_task_map(raw_html).color_to_task
        extractor = create_critic_extractor(cmap)
        body = extractor.extract(raw_html)
        for rec in extractor._critic_report:
            nested.append({"page": name, "tasks": rec["tasks"], "html": rec["html"][:500]})
        (out_dir / (_safe_name(name) + ".md")).write_text(
            _render_md(name, body), encoding="utf-8")

    report["nested_flattened"] = nested
    report["stats"]["nested_flattened"] = len(nested)
    report["stats"]["positions_manual_review"] += len(nested)
    return manifest, report


def render_report_md(report: dict) -> str:
    """Человекочитаемый markdown-отчёт из JSON (ТЗ п. 4.10)."""
    st = report["stats"]
    lines: List[str] = []
    lines.append(f"# Отчёт миграции цвета — сервис {report['service']}")
    lines.append("")
    lines.append(f"Дата: {report['migrated_at']}")
    lines.append("")
    lines.append("## Статистика")
    lines.append("")
    lines.append(f"- Страниц обработано: {st['pages_processed']}")
    lines.append(f"- Цветных фрагментов найдено: {st['colored_fragments_total']}")
    lines.append(f"- Позиций требует ручного разбора: {st['positions_manual_review']}")
    lines.append("")

    def _section(title: str, items: List[str]):
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        if items:
            lines.extend(items)
        else:
            lines.append("_нет_")
        lines.append("")

    _section("Страницы без секции «История изменений»",
             [f"- {p}" for p in report["pages_without_history"]])
    _section("Неразрешённые цвета (плейсхолдеры UNKNOWN-*)",
             [f"- `{u['placeholder']}` цвет {u['color']} на «{u['page']}» "
              f"×{u['count']} ({u['reason']})" for u in report["unresolved_placeholders"]])
    _section("Коллизии «цвет → несколько задач»",
             [f"- {c['color']} на «{c['page']}»: выбран {c['chosen']} из "
              f"{c['candidates']}" for c in report["collisions"]])
    _section("Ячейки «Задача в Jira» без извлекаемого id",
             [f"- {j['color']} на «{j['page']}»" for j in report["jira_unextractable"]])
    _section("Автоматически уплощённые вложенные конструкции (требуют проверки)",
             [f"- задачи {n['tasks']} на «{n['page']}»" for n in report.get("nested_flattened", [])])

    lines.append("## Сводка цветов (диагностика набора black_colors)")
    lines.append("")
    lines.append("| Цвет | Частота | Классификация | Задача |")
    lines.append("| --- | --- | --- | --- |")
    for c in report["color_summary"]:
        lines.append(f"| {c['color']} | {c['count']} | {c['classification']} | "
                     f"{c['task'] or ''} |")
    lines.append("")
    return "\n".join(lines)


def _read_html_dir(html_dir: Path) -> List[Tuple[str, str]]:
    return [(p.stem, p.read_text(encoding="utf-8"))
            for p in sorted(html_dir.glob("*.html"))]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_colors.py",
        description="Миграция цвета Confluence → CriticMarkup, режим «только отчёт» (ТЗ Модуль 1).")
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_common(p):
        p.add_argument("--html-dir", required=True, help="каталог с сохранёнными .html")
        p.add_argument("--out", default=".", help="каталог для вывода")
        p.add_argument("--service", default="", help="код сервиса для манифеста")
        p.add_argument("--date", default=date.today().isoformat(),
                       help="значение migrated_at (по умолчанию сегодня)")

    _add_common(sub.add_parser("report", help="отчёт и манифест без записи маркеров (ТЗ 4.3)"))
    _add_common(sub.add_parser("migrate", help="боевой проход: запись .md с маркерами + отчёт"))

    args = parser.parse_args(argv)

    html_dir = Path(args.html_dir)
    if not html_dir.is_dir():
        print(f"ОШИБКА: каталог не найден: {html_dir}", file=sys.stderr)
        return 2

    pages = _read_html_dir(html_dir)
    if not pages:
        print(f"ОШИБКА: в {html_dir} нет .html файлов", file=sys.stderr)
        return 2

    out = Path(args.out)
    if args.command == "migrate":
        docs_dir = out / "docs"
        manifest, report = migrate_pages(pages, args.service, args.date, docs_dir)
    else:
        manifest, report = aggregate(pages, args.service, args.date)

    out.mkdir(parents=True, exist_ok=True)
    (out / "migration-manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (out / "migration-colors-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "migration-colors-report.md").write_text(
        render_report_md(report), encoding="utf-8")

    st = report["stats"]
    print(f"Команда: {args.command}. Обработано страниц: {st['pages_processed']}; "
          f"цветных фрагментов: {st['colored_fragments_total']}; "
          f"ручной разбор: {st['positions_manual_review']} позиций"
          f" (в т.ч. уплощений: {st.get('nested_flattened', 0)}).")
    if args.command == "migrate":
        print(f"Markdown с маркерами записан в {out / 'docs'}")
    print(f"Отчёт и манифест записаны в {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
