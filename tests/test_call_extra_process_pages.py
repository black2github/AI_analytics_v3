# tests/test_call_extra_process_pages.py
"""Доп. страницы-процессы в шапке карточки вызова (КК CALL-INT-012, постановка 2026-11-09, П-2):
литералы и таблицы доп. страницы, у которой есть своя карточка-держатель в комплекте, находятся в
этой карточке — у карточки вызова ✗ по ним нет; доп. страница без держателя по-прежнему сверяется
с группой карточки вызова и даёт ✗ при потере."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc

P_MAIN, P_PROC = "2000000088", "2000000090"
TAG = f"доп. страницы {P_PROC}"
PROC_BODY = ("Карта выпускается со статусом «Выпуск карты» или «Отказ в выпуске».\n\n"
             "| Код ошибки ТЕССА | Текст |\n|---|---|\n| TESS1.01 | Нет счёта |\n| TESS1.02 | Нет карты |\n")


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(cid, title, typ, pids, body="текст\n"):
    return (f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\nconfluence_page_ids: [{pids}]\n---\n\n"
            f"# {cid}. {title}\n\n{body}")


def page(pid, title, body="текст\n"):
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\n{body}"


def kit(tmp_path: Path, with_holder: bool) -> Path:
    docs = tmp_path / "kit/docs"
    src = docs.parent / "sources/confluence"
    make(docs / "traceability-matrix.md", "# М\n")
    root = docs / "srs/bc-issue"
    make(root / "process/proc-026.md", card("PROC-026", "Создать заявку", "process", P_MAIN))
    make(root / "contract-call/internal/call-int-012.md",
         card("CALL-INT-012", "Создать заявку", "contract-call", f"{P_MAIN}, {P_PROC}",
              "Метод вызывается с параметрами из процессов.\n"))
    if with_holder:
        make(root / "process/proc-033.md",
             card("PROC-033", "Получить информацию о выпуске карт", "process", P_PROC, PROC_BODY))
    make(src / f"{P_MAIN}.md", page(P_MAIN, "Создать заявку"))
    make(src / f"{P_PROC}.md", page(P_PROC, "Получить информацию о выпуске карт", PROC_BODY))
    return docs


def _extra_lines(report):
    return [ln for ln in report if TAG in ln and "call-int-012.md" in ln]


def test_process_extra_page_values_found_in_holder(tmp_path):
    report, _ok = sc.run(kit(tmp_path, with_holder=True), tmp_path / "kit/sources/confluence")
    lines = _extra_lines(report)
    assert lines, "\n".join(report)
    assert not any("отсутствуют" in ln for ln in lines), "\n".join(lines)
    assert any("proc-033.md" in ln for ln in lines), "\n".join(lines)
    group = [ln for ln in report if "proc-026.md" in ln and "←" in ln]
    assert group and group[0].startswith("✓"), "\n".join(report)


def test_process_extra_page_without_holder_still_defect(tmp_path):
    # ограничитель: у доп. страницы нет карточки-держателя — потеря у карточки вызова видна
    report, ok = sc.run(kit(tmp_path, with_holder=False), tmp_path / "kit/sources/confluence")
    lines = _extra_lines(report)
    assert any("отсутствуют" in ln for ln in lines), "\n".join(report)
    assert not ok
