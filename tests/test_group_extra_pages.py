"""Доп. страницы НЕглавных файлов группы: таблицы и кавычечные литералы сверяются, как у
главной; сторож title их не видит (замечание ОНБ-В 72, 2026-11-07)."""
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI.kitcheck.core import is_soft_signal

P1, PEF = "2000000111", "2000000999"
TABLE = "| Код | Значение |\n|---|---|\n| ALFA | Первое значение |\n| BETA | Второе значение |\n"
EF_BODY = "Нажмите кнопку «Отправить заявку» или «Отменить ввод».\n\n" + TABLE
EF_VALUES = "ALFA Первое значение BETA Второе значение «Отправить заявку» «Отменить ввод»\n"
TAG = f"доп. страницы {PEF} «ЭФ Клиента Заявка»"


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(cid, title, pids, body="текст\n", typ="data-model"):
    return (f"---\nid: {cid}\ntitle: '{title}'\ntype: {typ}\nconfluence_page_ids: [{pids}]\n---\n\n"
            f"# {title}\n\n{body}")


def page(pid, title, body="текст\n"):
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\n{body}"


def kit(tmp_path, with_ef_card: bool, ef_card_body: str = EF_VALUES):
    docs = tmp_path / "kit/docs"
    src = tmp_path / "kit/sources/confluence"
    make(docs / "traceability-matrix.md", "# М\n")
    # главная группы по пути — srs/a/…; неглавная (srs/b/…) несёт доп. страницу-ЭФ
    make(docs / "srs/a/ent-main.md", card("ENT-001", "Главная страница", P1))
    make(docs / "srs/b/ent-call.md", card("ENT-002", "Главная страница", f"{P1}, {PEF}"))
    if with_ef_card:
        make(docs / "srs/c/scr.md", card("ENT-003", "ЭФ Клиента Заявка", PEF, ef_card_body))
    make(src / f"{P1}.md", page(P1, "Главная страница"))
    make(src / f"{PEF}.md", page(PEF, "ЭФ Клиента Заявка", EF_BODY))
    return docs


def run(docs):
    return sc.run(docs, docs.parent / "sources/confluence")


def _group_lines(report):
    return [ln for ln in report if TAG in ln]


def test_non_main_extra_page_values_lost_flagged(tmp_path):
    # раньше доп. страница неглавного файла не сверялась вовсе — теперь потеря видна
    report, ok = run(kit(tmp_path, with_ef_card=False))
    lines = _group_lines(report)
    assert any("таблица источника «Код | Значение»" in ln and "отсутствуют" in ln for ln in lines)
    assert any("кавычечные литералы " + TAG in ln for ln in lines)
    assert not ok


def test_non_main_extra_page_values_in_ef_card_not_lost(tmp_path):
    report, ok = run(kit(tmp_path, with_ef_card=True))
    lines = _group_lines(report)
    assert not any("отсутствуют" in ln for ln in lines), lines
    lit = [ln for ln in lines if "кавычечные литералы ×2 найдены в артефактах той же страницы" in ln]
    assert lit and "srs/c/scr.md" in lit[0] and is_soft_signal(lit[0].strip())
    tab = [ln for ln in lines if "i таблицы источника: значений" in ln]
    assert tab and "srs/c/scr.md" in tab[0]


def test_literal_absent_in_ef_card_still_flagged(tmp_path):
    # НЕсрабатывание снятия: литерал, которого нет и в карточке ЭФ, — ✗
    report, ok = run(kit(tmp_path, with_ef_card=True,
                         ef_card_body="ALFA Первое значение BETA Второе значение «Отправить заявку»\n"))
    lines = _group_lines(report)
    assert any("кавычечные литералы " + TAG in ln and "Отменить ввод" in ln for ln in lines)
    assert not ok


def test_title_guard_not_applied_to_non_main_extra(tmp_path):
    # title доп. страницы неглавного файла заголовком раздела быть не обязан
    report, _ok = run(kit(tmp_path, with_ef_card=True))
    assert not any("ПОТЕРЯ НАИМЕНОВАНИЯ" in ln for ln in report)


def test_main_extra_pages_unchanged(tmp_path):
    # доп. страница главной — как прежде: и title, и таблицы
    docs = tmp_path / "kit/docs"
    src = tmp_path / "kit/sources/confluence"
    make(docs / "traceability-matrix.md", "# М\n")
    make(docs / "srs/a/ent-main.md", card("ENT-001", "Главная страница", f"{P1}, {PEF}"))
    make(src / f"{P1}.md", page(P1, "Главная страница"))
    make(src / f"{PEF}.md", page(PEF, "ЭФ Клиента Заявка", EF_BODY))
    report, ok = run(docs)
    assert any("ПОТЕРЯ НАИМЕНОВАНИЯ" in ln for ln in report)
    assert any(TAG in ln and "отсутствуют" in ln for ln in report)
