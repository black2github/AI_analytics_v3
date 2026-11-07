"""Главная карточка группы — держатель страницы, а не карточка вызова (замечание ОНБ-В 66,
2026-11-07)."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc

P1 = "2000000111"
SRC_STEPS = "Шаг №1 Проверить заявку\n\nШаг №2 Отправить заявку\n\nШаг №3 Записать результат\n"


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(cid, title, typ, body="текст\n", pids=P1):
    return (f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\nconfluence_page_ids: [{pids}]\n---\n\n"
            f"# {title}\n\n{body}")


def kit(tmp_path, cards):
    docs = tmp_path / "kit/docs"
    src = tmp_path / "kit/sources/confluence"
    make(docs / "traceability-matrix.md", "# М\n")
    for rel, text in cards.items():
        make(docs / rel, text)
    make(src / f"{P1}.md", f"---\ntitle: 'Процесс'\nconfluence_page_id: '{P1}'\n---\n\n{SRC_STEPS}")
    return docs


def run(docs):
    report, ok = sc.run(docs, docs.parent / "sources/confluence")
    return report, ok


def _head(report):
    return next(ln for ln in report if ln.startswith(("✓ ", "✗ ", "⚠ ")) and "←" in ln)


def test_call_and_process_group_main_is_process(tmp_path):
    docs = kit(tmp_path, {
        "srs/contract-call/call-int-001.md": card("CALL-INT-001", "Процесс", "contract-call"),
        "srs/process/proc-001.md": card("PROC-001", "Процесс", "process"),
    })
    report, _ok = run(docs)
    head = _head(report)
    assert head.index("proc-001.md") < head.index("call-int-001.md")
    line = [ln for ln in report if "i главная карточка группы:" in ln]
    assert len(line) == 1
    assert "proc-001.md (тип process; по порядку путей была бы " in line[0]
    assert "call-int-001.md" in line[0]


def test_process_guards_run_on_process_card(tmp_path):
    # сторож маркеров шагов процесса: раньше на такой группе молча не выполнялся
    cards = {
        "srs/contract-call/call-int-001.md": card("CALL-INT-001", "Процесс", "contract-call"),
        "srs/process/proc-001.md": card("PROC-001", "Процесс", "process"),
    }
    report, ok = run(kit(tmp_path, cards))
    steps = [ln for ln in report if "маркеры шагов источника: в карточке отсутствуют" in ln]
    assert steps and not ok


def test_single_type_group_order_unchanged(tmp_path):
    docs = kit(tmp_path, {
        "srs/contract-call/call-int-001.md": card("CALL-INT-001", "Процесс", "contract-call"),
        "srs/contract-call/call-int-002.md": card("CALL-INT-002", "Процесс", "contract-call"),
    })
    report, _ok = run(docs)
    head = _head(report)
    assert head.index("call-int-001.md") < head.index("call-int-002.md")
    assert not any("главная карточка группы" in ln for ln in report)


def test_call_with_non_holder_type_order_unchanged(tmp_path):
    # иной тип (не держатель страницы) — порядок путей прежний
    docs = kit(tmp_path, {
        "srs/contract-call/call-int-001.md": card("CALL-INT-001", "Процесс", "contract-call"),
        "srs/data-model/ent-001.md": card("ENT-001", "Процесс", "data-model"),
    })
    report, _ok = run(docs)
    head = _head(report)
    assert head.index("call-int-001.md") < head.index("ent-001.md")
    assert not any("главная карточка группы" in ln for ln in report)


def test_holder_already_first_no_line(tmp_path):
    docs = kit(tmp_path, {
        "srs/a-function/fun-001.md": card("FUN-001", "Процесс", "function"),
        "srs/contract-call/call-int-001.md": card("CALL-INT-001", "Процесс", "contract-call"),
    })
    report, _ok = run(docs)
    head = _head(report)
    assert head.index("fun-001.md") < head.index("call-int-001.md")
    assert not any("главная карточка группы" in ln for ln in report)


def test_thin_call_exemption_follows_owner_after_reorder(tmp_path):
    # тонкая карточка вызова стала неглавной: её доп. страница-метод владельца сверяется с
    # освобождением тонкой карточки (по её шапке), а не строго по типу главной
    pm = "2000000888"
    thin = ("**Базовый контракт:** [EXTINT-ESK-001 Проверка полномочий](../../x.md)\n")
    docs = kit(tmp_path, {
        "srs/contract-call/call-ext-001.md": card("CALL-EXT-001", "Процесс", "contract-call",
                                                  body=thin, pids=f"{P1}, {pm}"),
        "srs/process/proc-001.md": card("PROC-001", "Процесс", "process"),
    })
    make(docs.parent / f"sources/confluence/{pm}.md",
         f"---\ntitle: 'Метод ЕСК'\nconfluence_page_id: '{pm}'\n---\n\n"
         "<table><tr><th>Параметр</th><th>Описание</th></tr>"
         "<tr><td>CL_ORG</td><td>GUID организации</td></tr>"
         "<tr><td>Is_Success</td><td>Признак успеха «1»</td></tr></table>\n")
    report, _ok = run(docs)
    lines = [ln for ln in report if f"доп. страницы {pm}" in ln]
    assert lines and all("карточки call-ext-001.md" in ln for ln in lines)
    assert not any("отсутствуют" in ln and "имён параметров" in ln for ln in lines), lines


def test_call_extra_pages_still_checked_after_reorder(tmp_path):
    # доп. страница карточки вызова, ставшей неглавной, сверяется (срез 3), title — нет
    pef = "2000000999"
    docs = kit(tmp_path, {
        "srs/contract-call/call-int-001.md": card("CALL-INT-001", "Процесс", "contract-call",
                                                  pids=f"{P1}, {pef}"),
        "srs/process/proc-001.md": card("PROC-001", "Процесс", "process"),
    })
    make(docs.parent / f"sources/confluence/{pef}.md",
         f"---\ntitle: 'ЭФ'\nconfluence_page_id: '{pef}'\n---\n\nКнопка «Отправить заявку».\n")
    report, _ok = run(docs)
    assert any(f"доп. страницы {pef}" in ln and "кавычечные литералы" in ln for ln in report)
    assert not any("ПОТЕРЯ НАИМЕНОВАНИЯ" in ln and pef in ln for ln in report)
