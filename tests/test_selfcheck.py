# tests/test_selfcheck.py
"""Диспетчер самопроверки: обход docs/, мэппинг карточка↔источник по
confluence_page_id, изоляция крашей, полная перепись файлов (молчаливых
пропусков нет)."""

from pathlib import Path

from app.scripts.CI import selfcheck


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(title: str, pids: str = "") -> str:
    pid_line = f"confluence_page_ids: [{pids}]\n" if pids else ""
    return (f"---\nid: X-01\ntitle: '{title}'\ntype: function\n"
            f"{pid_line}---\n\n# Т\n\nтекст\n")


def source(title: str, pid: str, body: str = "текст\n") -> str:
    return (f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\n"
            + body)


def make_matrix(docs: Path, extra: str = "") -> None:
    make(docs / "traceability-matrix.md",
         "# Матрица\n\n| ID | Тип | Наименование | Файл |\n"
         "|---|---|---|---|\n" + extra)


def test_happy_mapping_and_census(tmp_path):
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "111222"))
    make_matrix(docs)
    make(srcs / "стр1.md", source("[X] Ф1", "111222"))
    report, ok = selfcheck.run(docs, srcs)
    assert ok, report
    assert any(ln.startswith("✓") and "стр1.md" in ln for ln in report)
    assert any("ИТОГО: файлов 2 — ✓ 1, ✗ 0, ⚠ 1" in ln for ln in report)


def test_unmapped_reverse_card_is_defect(tmp_path):
    # правило 2: reverse-карточка без источника — брак, не пропуск
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "999999"))
    make(srcs / "стр1.md", source("[X] Ф1", "111222"))
    report, ok = selfcheck.run(docs, srcs)
    assert not ok
    assert any("НЕ НАЙДЕН" in ln and "999999" in ln for ln in report)


def test_forward_card_internal_checks_only(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make_matrix(docs)
    report, ok = selfcheck.run(docs, None)
    assert ok, report
    assert any("page_ids нет" in ln for ln in report)


def test_broken_frontmatter_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", "---\nid: X\nбез закрытия\n")
    report, ok = selfcheck.run(docs, None)
    assert not ok and any("frontmatter не распознан" in ln
                          for ln in report)


def test_service_files_and_census_complete(tmp_path):
    # каждый файл комплекта попадает ровно в одну категорию
    docs = tmp_path / "docs"
    make(docs / "traceability-matrix.md", "# Матрица\n")
    make(docs / "open-questions.md", "## OQ-001. В\n")
    make(docs / "README.md", "# Комплект\n")  # без frontmatter
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    report, ok = selfcheck.run(docs, None)
    assert ok
    assert any("ИТОГО: файлов 4 — ✓ 1, ✗ 0, ⚠ 3" in ln for ln in report)


def test_crash_isolated_per_card(tmp_path, monkeypatch):
    # правило 1: краш одной карточки не роняет прогон
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make(docs / "srs/functions/f2.md", card("[X] Ф2"))
    real = selfcheck.nt.run_check

    def boom(files, src, **kw):
        if files[0].name == "f1.md":
            raise RuntimeError("патологический вход")
        return real(files, src, **kw)

    monkeypatch.setattr(selfcheck.nt, "run_check", boom)
    report, ok = selfcheck.run(docs, None)
    assert not ok
    assert any("КРАШ" in ln for ln in report)
    assert any(ln.startswith("✓") and "f2.md" in ln for ln in report)
    assert any("ИТОГО: файлов 2 — ✓ 1, ✗ 1" in ln for ln in report)


def test_multicard_union_single_call(tmp_path):
    # межтиповая страница: значения источника ищутся в объединении
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    body = ("| Код | Значение |\n|---|---|\n"
            "| A1 | Боевой код |\n| B2 | Второй код |\n")
    make(srcs / "стр.md", source("[X] К1", "555555", body))
    make(docs / "srs/data-model/k1.md",
         card("[X] К1", "555555").replace("текст", "A1 Боевой код"))
    make(docs / "srs/data-model/k2.md",
         card("[X] К2", "555555").replace("текст", "B2 Второй код"))
    make_matrix(docs)
    report, ok = selfcheck.run(docs, srcs)
    assert ok, report
    assert any("k1.md" in ln and "k2.md" in ln and ln.startswith("✓")
               for ln in report)


def test_duplicate_source_pid_warned(tmp_path):
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(srcs / "a.md", source("[X] Ф1", "111222"))
    make(srcs / "b.md", source("[X] Ф1", "111222"))
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "111222"))
    make_matrix(docs)
    report, ok = selfcheck.run(docs, srcs)
    assert ok
    assert any(ln.startswith("i") and "111222" in ln for ln in report)


def test_brackets_in_paths(tmp_path):
    # [скобки] в именах — pathlib, не glob-шаблоны
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(srcs / "[БлокН2Н]-Стр.md", source("[Б] Ф1", "777777"))
    make(docs / "srs/functions/f1.md", card("[Б] Ф1", "777777"))
    make_matrix(docs)
    report, ok = selfcheck.run(docs, srcs)
    assert ok and any("[БлокН2Н]-Стр.md" in ln for ln in report)


def test_matrix_missing_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    report, ok = selfcheck.run(docs, None)
    assert not ok and any("матрица не найдена" in ln for ln in report)


def test_overdue_debt_propagates(tmp_path):
    # link_debts в диспетчере: просроченный долг = брак прогона
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md",
         "---\nid: FUN-BNK-01\ntitle: 'Ф1'\ntype: function\n---\n\n"
         "шаг процесса Процесс обработки заявки на выпуск\n")
    make(docs / "srs/process/prc-001.md",
         "---\nid: PRC-001\ntitle: '[X] Процесс обработки заявки на "
         "выпуск'\ntype: process\n---\n\n# П\n")
    make_matrix(docs,
                "| FUN-BNK-01 | function | Ф1 | srs/functions/f1.md |\n"
                "| FUN-BNK-01 | — | нет целевого артефакта PRC «Процесс "
                "обработки заявки на выпуск» — требуется заход "
                "create-process |\n")
    report, ok = selfcheck.run(docs, None)
    assert not ok and any("ПРОСРОЧЕН" in ln for ln in report)


def test_oq_disorder_propagates(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make_matrix(docs)
    make(docs / "open-questions.md",
         "## OQ-001. А\n\n## OQ-003. Б\n\n## OQ-002. В\n")
    report, ok = selfcheck.run(docs, None)
    assert not ok and any("порядок реестра нарушен" in ln
                          for ln in report)


def test_coverage_informational_not_blocking(tmp_path):
    # непокрытая страница — информация (остаток конвейера), не брак
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "111222"))
    make_matrix(docs)
    make(srcs / "стр1.md", source("[X] Ф1", "111222"))
    make(srcs / "стр2.md", source("[X] Другая", "333333"))
    report, ok = selfcheck.run(docs, srcs)
    assert ok, report
    assert any("НЕ покрыто: 1" in ln for ln in report)
