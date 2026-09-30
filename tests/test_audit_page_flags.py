# tests/test_audit_page_flags.py
#
# Сверка страничных флагов заморозки архива с историей изменений (2026-09-30).
#
# Архив, выгруженный до версии 1.9.1, мог заморозить страницу целиком из-за задачи
# в середине истории. Истории в архиве нет, поэтому сверка читает её заново по
# confluence_page_id и применяет правило экспортёра. Здесь источник — каталог
# <page_id>.html (офлайн-режим утилиты).
#
# Главное: утилита ничего не пишет в архив и не путает «заморожена ошибочно» с
# флагами, которые ставил не список (сторож, --flag-page).

from pathlib import Path

from app.scripts.audit_page_flags import (FOREIGN, NO_DATA, OK, WRONG, audit,
                                          flagged_pages, main, render_report)

ORANGE = "rgb(255,102,0)"


def _hist(rows):
    head = "".join(f"<th>{h}</th>" for h in ("Дата", "Описание", "Автор", "Задача в JIRA"))
    return (f"<h1>История изменений</h1><table><thead><tr>{head}</tr></thead>"
            f"<tbody>{rows}</tbody></table><p>текст требования</p>")


def _row(date_iso, color, jira):
    y, m, d = date_iso.split("-")
    desc = (f'<span style="color: {color}">описание</span>' if color
            else "<span>описание</span>")
    return (f'<tr><td><time datetime="{date_iso}">{d}.{m}.{y}</time></td>'
            f"<td>{desc}</td><td>автор</td><td>{jira}</td></tr>")


def _page(root: Path, name: str, page_id: str, flag: str = "") -> Path:
    fm = ["---", f"title: '{name}'", f"confluence_page_id: '{page_id}'" if page_id
          else "jira_id: ''", "status: draft"]
    if flag:
        fm.append(f"unapproved_jira: {flag}")
    fm.append("---")
    path = root / f"{name}.md"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(fm) + "\n\n{++" + (flag or "GBO-0") + ": текст++}\n")
    return path


def _stand(tmp_path):
    """Архив из шести страниц и каталог истории к ним."""
    arc = tmp_path / "raw"
    html = tmp_path / "html"
    arc.mkdir()
    html.mkdir()
    _page(arc, "создана задачей", "101", "GBO-50")
    (html / "101.html").write_text(
        _hist(_row("2024-03-05", None, "GBO-50") + _row("2025-06-01", ORANGE, "GBO-77")),
        encoding="utf-8")
    _page(arc, "задача в середине", "102", "GBO-50")
    (html / "102.html").write_text(
        _hist(_row("2023-01-10", None, "GBO-1") + _row("2024-03-05", None, "GBO-50")),
        encoding="utf-8")
    _page(arc, "флаг сторожа", "103", "GBO-77")          # вся страница под цветом
    (html / "103.html").write_text(
        _hist(_row("2025-06-01", ORANGE, "GBO-77")), encoding="utf-8")
    _page(arc, "не загрузилась", "104", "GBO-50")        # html нет
    _page(arc, "без page_id", "", "GBO-50")
    _page(arc, "без флага", "106")                        # в сверку не входит
    (html / "106.html").write_text(
        _hist(_row("2023-01-10", None, "GBO-1")), encoding="utf-8")
    return arc, html


def _fetch(html: Path):
    def fetch(page_id):
        p = html / f"{page_id}.html"
        return p.read_text(encoding="utf-8") if p.is_file() else None
    return fetch


def _by_title(results):
    return {r["title"]: r for r in results}


class TestSelection:
    def test_only_flagged_pages_are_audited(self, tmp_path):
        arc, _ = _stand(tmp_path)
        titles = {p["title"] for p in flagged_pages(arc)}
        assert "без флага" not in titles
        assert len(titles) == 5


class TestVerdicts:
    def test_created_by_task_is_confirmed(self, tmp_path):
        arc, html = _stand(tmp_path)
        r = _by_title(audit(arc, _fetch(html)))["создана задачей"]
        assert r["verdict"] == OK

    def test_task_in_the_middle_is_wrongly_frozen(self, tmp_path):
        arc, html = _stand(tmp_path)
        r = _by_title(audit(arc, _fetch(html)))["задача в середине"]
        assert r["verdict"] == WRONG
        assert "не в первой записи" in r["detail"]

    def test_watchdog_flag_is_not_reported_as_wrong(self, tmp_path):
        # НЕсрабатывание: флаг сторожа (цветная страница) правка не касается
        arc, html = _stand(tmp_path)
        r = _by_title(audit(arc, _fetch(html)))["флаг сторожа"]
        assert r["verdict"] == FOREIGN

    def test_missing_page_and_missing_id_need_manual_check(self, tmp_path):
        arc, html = _stand(tmp_path)
        res = _by_title(audit(arc, _fetch(html)))
        assert res["не загрузилась"]["verdict"] == NO_DATA
        assert res["без page_id"]["verdict"] == NO_DATA
        assert "confluence_page_id" in res["без page_id"]["detail"]

    def test_page_without_history_needs_manual_check(self, tmp_path):
        arc, html = _stand(tmp_path)
        (html / "104.html").write_text("<p>страница без истории</p>", encoding="utf-8")
        r = _by_title(audit(arc, _fetch(html)))["не загрузилась"]
        assert r["verdict"] == NO_DATA and "не опознана" in r["detail"]

    def test_full_list_changes_nothing_for_the_flag_task(self, tmp_path):
        # со списком экспорта вердикты по задаче флага те же
        arc, html = _stand(tmp_path)
        res = _by_title(audit(arc, _fetch(html), unapproved={"GBO-50", "GBO-999"}))
        assert res["создана задачей"]["verdict"] == OK
        assert res["задача в середине"]["verdict"] == WRONG


class TestReadOnly:
    def test_archive_is_not_modified(self, tmp_path):
        arc, html = _stand(tmp_path)
        before = {p: p.read_bytes() for p in arc.rglob("*.md")}
        assert main([str(arc), "--html-dir", str(html)]) == 1
        assert {p: p.read_bytes() for p in arc.rglob("*.md")} == before
        assert sorted(arc.iterdir()) == sorted(before)      # новых файлов нет


class TestCli:
    def test_exit_code_and_report_file(self, tmp_path, capsys):
        arc, html = _stand(tmp_path)
        out = tmp_path / "audit.md"
        assert main([str(arc), "--html-dir", str(html), "--out", str(out)]) == 1
        text = out.read_text(encoding="utf-8")
        assert "## Заморожена ошибочно — страница потеряна целиком (1)" in text
        assert "`GBO-50` «задача в середине» (page_id 102)" in text
        assert f"{WRONG}: 1" in capsys.readouterr().out

    def test_exit_zero_when_nothing_wrong(self, tmp_path):
        arc, html = _stand(tmp_path)
        (arc / "задача в середине.md").unlink()
        assert main([str(arc), "--html-dir", str(html)]) == 0

    def test_missing_root_is_usage_error(self, tmp_path):
        assert main([str(tmp_path / "нет"), "--html-dir", str(tmp_path)]) == 2

    def test_report_lists_every_verdict(self, tmp_path):
        arc, html = _stand(tmp_path)
        text = render_report(audit(arc, _fetch(html)), arc)
        for verdict, n in ((WRONG, 1), (NO_DATA, 2), (FOREIGN, 1), (OK, 1)):
            assert f"| {verdict} | {n} |" in text
