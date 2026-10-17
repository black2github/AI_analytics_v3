# tests/test_selfcheck_matrix_sync.py
"""selfcheck вызывает matrix_sync --check (решение владельца канона 2026-10-17):
расхождения выводимых разделов матрицы — ⚠, вердикт не меняется; матрица не по
шаблону канона — одна строка «i … сверка пропущена»; без матрицы — молчит."""
from app.scripts.CI import selfcheck as sc
from tests.test_matrix_sync import fm, kit, w


class _Ctx:
    def __init__(self, docs):
        self.docs = docs


def test_template_matrix_consistent_one_ok_line(tmp_path):
    lines, ok = sc._kc_matrix_sync(_Ctx(kit(tmp_path)))
    assert ok is True
    assert lines == ["✓ выводимые разделы матрицы совпадают с документами (matrix_sync)"], lines


def test_discrepancy_is_warning_and_verdict_unchanged(tmp_path):
    docs = kit(tmp_path, fun_extra="Показывает [SCR-CL-02 Список](../screen-form/scr-cl-02.md).\n")
    w(docs / "srs/screen-form/scr-cl-02.md", fm("SCR-CL-02", "screen-form", "Список"))
    lines, ok = sc._kc_matrix_sync(_Ctx(docs))
    assert ok is True                                   # справочная: вердикт не трогает
    assert lines[0].startswith("⚠ выводимые разделы матрицы (matrix_sync) расходятся"), lines
    text = "\n".join(lines)
    assert "SCR-CL-02" in text and all(ln.startswith("   ") for ln in lines[1:]), text


def test_matrix_not_by_template_single_info_line(tmp_path):
    docs = kit(tmp_path)
    mx = docs / "traceability-matrix.md"
    mx.write_text(mx.read_text(encoding="utf-8").replace("## Источники миграции",
                                                         "## Источники (вне SRS)"), encoding="utf-8")
    lines, ok = sc._kc_matrix_sync(_Ctx(docs))
    assert ok is True
    assert lines == ["i матрица трассировки не по шаблону канона — сверка выводимых разделов "
                     "(matrix_sync) пропущена"], lines


def test_no_matrix_silent(tmp_path):
    """Несрабатывание: без матрицы проверка молчит — брак «матрица не найдена»
    даёт проверка реестра ID."""
    docs = tmp_path / "docs"
    docs.mkdir()
    assert sc._kc_matrix_sync(_Ctx(docs)) == ([], True)


def test_crash_isolated_without_verdict(tmp_path, monkeypatch):
    docs = kit(tmp_path)

    def boom(_docs):
        raise RuntimeError("сбой")
    monkeypatch.setattr(sc, "_matrix_sync_report", boom)
    lines, ok = sc._kc_matrix_sync(_Ctx(docs))
    assert ok is True and lines[0].startswith("КРАШ проверки"), lines


def test_registered_after_matrix_registry_not_affecting_verdict():
    ids = [c.id for c in sc.KIT_CHECKS]
    assert ids.index("matrix_sync") == ids.index("matrix_registry_and_debts") + 1
    check = next(c for c in sc.KIT_CHECKS if c.id == "matrix_sync")
    assert check.affects_verdict is False
