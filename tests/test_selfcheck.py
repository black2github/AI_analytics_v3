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
    # X-01 в реестре по умолчанию: фикстурные карточки card() несут этот
    # id, а К-22 требует состояния каждого id в реестре матрицы
    make(docs / "traceability-matrix.md",
         "# Матрица\n\n| ID | Тип | Наименование | Файл |\n"
         "|---|---|---|---|\n| X-01 | function | Ф | f.md |\n" + extra)


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
    make(docs / "traceability-matrix.md", "# Матрица\n\nX-01\n")
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


def test_toc_as_main_page_flagged(tmp_path):
    # К-20: README + карточки с доп. страницами в одной группе главного
    # page_id = карточкам главной поставлено оглавление — брак мэппинга
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(srcs / "оглавление.md", source("[X] МД", "100000"))
    make(srcs / "сущность.md", source("[X] Сущность", "200000"))
    make(docs / "srs/data-model/README.md",
         card("[X] МД", "100000").replace("X-01", "DM-000"))
    make(docs / "srs/data-model/ent-001.md",
         card("[X] Сущность", "'100000', '200000'"))
    make_matrix(docs)
    report, ok = selfcheck.run(docs, srcs)
    assert not ok
    assert any("главной указана страница-оглавление" in ln
               for ln in report)


def test_shared_main_without_readme_legal(tmp_path):
    # тест на НЕсрабатывание К-20: межтиповая страница без README в
    # группе (вкладки/пары карточек) — легитимная множественность
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    body = "| Код | Значение |\n|---|---|\n| A1 | Боевой код |\n"
    make(srcs / "стр.md", source("[X] К1", "555555", body))
    make(docs / "srs/data-model/k1.md",
         card("[X] К1", "'555555', '777777'").replace("текст",
                                                      "A1 Боевой код"))
    make(docs / "srs/data-model/k2.md",
         card("[X] К2", "555555").replace("текст", "A1 Боевой код"))
    make_matrix(docs)
    report, ok = selfcheck.run(docs, srcs)
    assert ok, report


def test_oq_page_refs_warned_softly(tmp_path):
    # К-17: page_id в тексте OQ — предупреждение при ✓-вердикте
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make_matrix(docs)
    make(docs / "open-questions.md",
         "## OQ-001\n\n**Вопрос:** страница 2169849344 не перенесена.\n")
    report, ok = selfcheck.run(docs, None)
    assert ok, report
    assert any("предупреждение" in ln and "2169849344" in ln
               for ln in report)


def test_ghost_id_not_in_matrix_flagged(tmp_path):
    # К-22: id карточки вне реестра матрицы = фантомный ID, брак
    docs = tmp_path / "docs"
    make(docs / "srs/rbac.md",
         "---\nid: RBAC-001\ntitle: 'Р'\ntype: rbac\n---\n\n# Р\n\nтекст\n")
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make_matrix(docs)
    report, ok = selfcheck.run(docs, None)
    assert not ok
    assert any("фантомные id" in ln for ln in report)
    assert any("RBAC-001" in ln for ln in report)


def test_feedback_register_order_wired(tmp_path):
    # цикл обратной связи: реестр FB-NN сторожится диспетчером
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make_matrix(docs)
    make(tmp_path / "feedback.md",
         "## FB-001. А\n\n## FB-003. Б\n\n## FB-002. В\n")
    report, ok = selfcheck.run(docs, None)
    assert not ok
    assert any("реестр замечаний команды" in ln for ln in report)


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


def test_out_writes_full_utf8_report(tmp_path, monkeypatch, capsys):
    # --out: отчёт пишет сама утилита в UTF-8 (замена самодельных
    # лаунчеров и PowerShell-редиректов с UTF-16)
    import sys
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make_matrix(docs)
    out = tmp_path / "sandbox" / "selfcheck.txt"
    monkeypatch.setattr(sys, "argv",
                        ["selfcheck.py", "--docs", str(docs),
                         "--out", str(out)])
    rc = selfcheck.main()
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "ИТОГО" in text and "✓" in text
    assert "ИТОГО" in capsys.readouterr().out


def test_service_registry_broken_table_flagged(tmp_path):
    # К-16 на служебных реестрах: разрыв таблицы матрицы = брак (жил
    # незамеченным — служебные файлы шли мимо нормализатора)
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make(docs / "traceability-matrix.md",
         "# Матрица\n\n| ID | Тип | Наименование | Файл |\n"
         "|---|---|---|---|\n| A-1 | function | Ф1 | f1.md |\n\n"
         "| A-2 | function | Ф2 | f2.md |\n")
    report, ok = selfcheck.run(docs, None)
    assert not ok
    assert any("таблицы битые" in ln for ln in report)


def test_clean_document_guard_wired(tmp_path):
    # волна D: сторож чистовика доезжает через диспетчер — битая ссылка
    # в карточке = брак файла; серая http-ссылка = предупреждение при ✓
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md",
         card("[X] Ф1").replace("текст", "[нет цели](missing.md)"))
    make(docs / "srs/functions/f2.md",
         card("[X] Ф2").replace(
             "текст", "[фигма](https://www.figma.com/file/QQ)"))
    make_matrix(docs)
    report, ok = selfcheck.run(docs, None)
    assert not ok
    assert any("битая" in ln for ln in report)
    assert any("предупреждение" in ln and "figma" in ln for ln in report)


def test_delta_report_closed_and_opened(tmp_path):
    # дельта против базлайна: закрытые и НОВЫЕ ✗ по именам; «монотонно
    # падать» не требуется — новые квалифицируются (раскрытие/порча)
    from app.scripts.CI.selfcheck import delta_report
    base = tmp_path / "baseline.txt"
    base.write_text(
        "# ✗ srs\\a.md: источник page_id 1 НЕ НАЙДЕН\n"
        "# ✓ srs\\b.md ← стр1.md\n"
        "# ✓ долги ссылок (link_debts):\n", encoding="utf-8")
    cur = ["✓ srs\\a.md ← стр1.md",
           "✗ srs\\b.md: frontmatter не распознан",
           "✓ долги ссылок (link_debts):"]
    out = delta_report(base, cur)
    assert any("было 1 → стало 1" in ln for ln in out)
    assert any("закрыто ✗→✓ ×1" in ln and "a.md" in ln for ln in out)
    assert any("НОВЫЕ ✗ ×1" in ln and "b.md" in ln
               and "квалифицировать" in ln for ln in out)


def test_delta_report_no_changes_and_missing_baseline(tmp_path):
    from app.scripts.CI.selfcheck import delta_report
    base = tmp_path / "baseline.txt"
    base.write_text("# ✓ srs\\a.md ← стр1.md\n", encoding="utf-8")
    out = delta_report(base, ["✓ srs\\a.md ← стр1.md"])
    assert any("изменений вердиктов нет" in ln for ln in out)
    out2 = delta_report(tmp_path / "нет.txt", ["✓ srs\\a.md ← стр1.md"])
    assert any("не прочитан" in ln for ln in out2)


def test_root_junk_flagged(tmp_path):
    # чистота корня: скрипты правок/кэши рядом с docs — брак
    from app.scripts.CI import selfcheck as sc
    docs = tmp_path / "docs"
    make(docs / "a.md", card("[Т] А"))
    make_matrix(docs)
    make(tmp_path / "_fix_links.py", "print('x')\n")
    (tmp_path / "__pycache__").mkdir()
    report, ok = sc.run(docs, None)
    assert not ok
    assert any("корень репозитория" in ln and "_fix_links.py" in ln
               and "__pycache__" in ln for ln in report)


def test_root_markdown_and_std_dirs_ok(tmp_path):
    # НЕсрабатывание: md-файлы, точечные файлы и штатные каталоги
    from app.scripts.CI import selfcheck as sc
    docs = tmp_path / "docs"
    make(docs / "a.md", card("[Т] А"))
    make_matrix(docs)
    make(tmp_path / "README.md", "# о\n")
    make(tmp_path / "open-questions.md", "# OQ\n")
    make(tmp_path / ".gitattributes", "* text\n")
    (tmp_path / "sandbox").mkdir()
    (tmp_path / "sources").mkdir()
    report, ok = sc.run(docs, None)
    assert not any("корень репозитория" in ln for ln in report)


def test_warning_visible_on_ok_file(tmp_path):
    # предупреждения печатаются и при ✓ (софт-сигнал Э-12)
    docs = tmp_path / "docs"
    make(docs / "srs/functions/bank/f1.md",
         "---\nid: FUN-BNK-01\ntitle: 'Ф1'\ntype: function\n---\n\n"
         "## Доступность\n\nДоступна всегда.\n")
    make_matrix(docs, "| FUN-BNK-01 | function | Ф1 | f1.md |\n")
    report, ok = selfcheck.run(docs, None)
    assert ok
    assert any("предупреждение" in ln for ln in report)
