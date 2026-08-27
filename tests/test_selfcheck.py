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


def test_journal_appends_timestamped_itogo(tmp_path, monkeypatch, capsys):
    # хронометраж этапов: время штампует прибор (у LLM нет часов)
    import re as _re
    from app.scripts.CI import selfcheck as sc
    docs = tmp_path / "docs"
    make(docs / "a.md", card("[Т] А"))
    make_matrix(docs)
    j = tmp_path / "sandbox" / "journal.txt"
    argv = ["selfcheck.py", "--docs", str(docs), "--journal", str(j)]
    monkeypatch.setattr("sys.argv", argv)
    sc.main()
    sc.main()
    make(docs / "b.md", card("[Т] Б"))  # правка между прогонами 2 и 3
    sc.main()
    lines = j.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3  # дозапись, не перезапись
    assert all(_re.match(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| ИТОГО", ln)
        for ln in lines)
    # соотнесение интервалов с шагами: изменённые файлы — в строке
    assert "первый прогон" in lines[0]
    assert "изменений файлов нет" in lines[1]
    assert "изменены:" in lines[2] and "b.md" in lines[2]


def _sub_fixture(tmp_path, card_rel: str):
    # сервис с таблицей разметки подсервисов в профиле источников
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(srcs / "Ветка-ЛК" / "стр1.md", source("[Т_ЛК] Функция лимитов",
                                               "111222"))
    make(docs / card_rel, card("[Т_ЛК] Функция лимитов", "111222"))
    make_matrix(docs)
    make(tmp_path / "README.md",
         "# Профиль\n\n## Разметка подсервисов\n\n"
         "| Матчер (тег или ветвь) | Зона |\n|---|---|\n"
         "| [Т_ЛК] | подсервис limits |\n"
         "| [Т_Виджет] | вне Экосистемы |\n")
    return docs, srcs


def test_subservice_mapping_ok(tmp_path):
    from app.scripts.CI import selfcheck as sc
    docs, srcs = _sub_fixture(tmp_path, "srs/limits/function/f1.md")
    report, ok = sc.run(docs, srcs)
    assert any("разметка подсервисов: соответствие" in ln
               for ln in report), report


def test_subservice_mapping_wrong_path_flagged(tmp_path):
    # карточка подсервиса легла в корень srs — брак с ожидаемым путём
    from app.scripts.CI import selfcheck as sc
    docs, srcs = _sub_fixture(tmp_path, "srs/function/f1.md")
    report, ok = sc.run(docs, srcs)
    assert not ok
    assert any("✗ разметка" in ln and "srs/limits/" in ln
               for ln in report), report


def test_subservice_external_zone_in_docs_flagged(tmp_path):
    # источник «вне Экосистемы» получил карточку в docs — брак
    from app.scripts.CI import selfcheck as sc
    docs, srcs = _sub_fixture(tmp_path, "srs/limits/function/f1.md")
    make(srcs / "Ветка-Виджеты" / "в1.md",
         source("[Т_Виджет] Скрипт ПИН", "333444"))
    make(docs / "srs" / "function" / "w1.md",
         card("[Т_Виджет] Скрипт ПИН", "333444"))
    report, ok = sc.run(docs, srcs)
    assert not ok
    assert any("вне Экосистемы" in ln and "не место" in ln
               for ln in report), report


def test_no_subservice_table_silent(tmp_path):
    # обычный сервис без таблицы — сторож молчит (ни строки о разметке)
    from app.scripts.CI import selfcheck as sc
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "111222"))
    make_matrix(docs)
    make(srcs / "стр1.md", source("[X] Ф1", "111222"))
    report, ok = sc.run(docs, srcs)
    assert not any("разметка" in ln for ln in report)


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


def test_cli_survives_cp1251_console(tmp_path):
    # Windows-консоль cp1251: перестройка stdout в UTF-8 стоит ДО argparse —
    # текст --help содержит «✗» и падал UnicodeEncodeError до перестройки
    # (ловилось на живом прогоне по эталону). Субпроцесс с PYTHONIOENCODING=
    # cp1251 честно воспроизводит консоль.
    import os
    import subprocess
    import sys
    script = (Path(__file__).resolve().parents[1]
              / "app" / "scripts" / "CI" / "selfcheck.py")
    env = {**os.environ, "PYTHONIOENCODING": "cp1251"}
    r = subprocess.run([sys.executable, str(script), "--help"],
                       capture_output=True, env=env)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert b"UnicodeEncodeError" not in r.stderr
    # и штатный прогон: вердикт печатается, не падает
    docs = tmp_path / "docs"
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make_matrix(docs)
    r2 = subprocess.run([sys.executable, str(script), "--docs", str(docs)],
                        capture_output=True, env=env)
    assert r2.returncode == 0, r2.stderr.decode("utf-8", "replace")
    assert "ИТОГО".encode("utf-8") in r2.stdout


def test_root_komplekt_v_korne(tmp_path):
    # топология «комплект в корне репозитория» (эталон
    # docs-account-opening-request): brd/, srs/, CODEOWNERS,
    # gpb-manifest.json — штатные; --docs указывает на сам корень.
    # С «--docs .» docs.parent == docs — прежний код флаговал brd/srs.
    from app.scripts.CI import selfcheck as sc
    docs = tmp_path
    make(docs / "srs/function/f1.md", card("[X] Ф1"))
    (docs / "brd").mkdir()
    make_matrix(docs)
    make(docs / "README.md", "# о\n")
    (docs / "CODEOWNERS").write_text("* @lead\n", encoding="utf-8")
    (docs / "gpb-manifest.json").write_text("{}\n", encoding="utf-8")
    report, ok = sc.run(docs, None)
    assert not any("корень репозитория" in ln for ln in report), report
    # тест на НЕсрабатывание послабления: скрипт в корне — по-прежнему брак
    (docs / "fix_all.py").write_text("print()\n", encoding="utf-8")
    report2, ok2 = sc.run(docs, None)
    assert any("корень репозитория" in ln and "fix_all.py" in ln
               for ln in report2)


def test_profiles_markers_soft_vs_strict(tmp_path):
    # Р-8: командный профиль (по умолчанию) — маркер сокращения =
    # предупреждение; полный (--strict) — брак, как раньше
    from app.scripts.CI import selfcheck as sc
    docs = tmp_path / "docs"
    make(docs / "srs/function/f1.md",
         card("[X] Ф1").replace("текст", "текст: коды A, B и т.д."))
    make_matrix(docs)
    rep_soft, ok_soft = sc.run(docs, None)
    assert ok_soft, rep_soft
    assert any("предупреждение: маркер сокращения" in ln for ln in rep_soft)
    rep_strict, ok_strict = sc.run(docs, None, strict=True)
    assert not ok_strict
    assert any("маркер сокращения" in ln and "ЦЕЛИКОМ" in ln
               for ln in rep_strict)


def test_nav_readme_exempt_from_frontmatter_warning(tmp_path):
    # Р-9: README без frontmatter — освобождён (нейтральная строка),
    # прочие файлы без frontmatter — прежнее предупреждение
    from app.scripts.CI import selfcheck as sc
    docs = tmp_path / "docs"
    make(docs / "srs/function/f1.md", card("[X] Ф1"))
    make(docs / "srs/README.md", "# Навигация\n")
    make(docs / "srs/notes.md", "# Заметки без frontmatter\n")
    make_matrix(docs)
    report, ok = sc.run(docs, None)
    assert any("README" in ln and "освобождён" in ln for ln in report)
    assert not any("README" in ln and "обязателен" in ln for ln in report)
    assert any("notes.md" in ln and "обязателен" in ln for ln in report)


def test_solo_fail_names_real_culprit(tmp_path):
    # пометка режима «без источника…» читалась причиной ✗ (вопрос
    # аналитика 2026-08-22): у ✗-файла первая строка называет брак
    # внутренних сторожей, пометка режима — после; у ✓ — как раньше
    from app.scripts.CI import selfcheck as sc
    docs = tmp_path / "docs"
    make(docs / "srs/function/bad.md",
         card("[X] Плохая").replace("текст", "текст заявкаID"))
    make(docs / "srs/function/good.md", card("[X] Хорошая"))
    make_matrix(docs)
    report, ok = sc.run(docs, None)
    bad = next(ln for ln in report if "bad.md" in ln)
    good = next(ln for ln in report if "good.md" in ln)
    assert bad.startswith("✗") and "брак внутренних сторожей" in bad
    assert "причины ниже" in bad and "без источника" in bad
    assert good.startswith("✓") and "брак" not in good


def test_multiline_page_ids_parsed_with_notice(tmp_path):
    # П-8 (COM-01 Корпкарт 2026-08-27): многострочный YAML-список
    # confluence_page_ids парсится (карточка НЕ выпадает из сверки),
    # формат помечается строкой-сигналом
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md",
         "---\nid: X-01\ntitle: '[X] Ф1'\ntype: function\n"
         "confluence_page_ids:\n  - '111222'\n  - '333444'\n---\n\n"
         "# Т\n\nтекст\n")
    make_matrix(docs)
    make(srcs / "стр1.md", source("[X] Ф1", "111222"))
    report, ok = selfcheck.run(docs, srcs)
    assert ok, report
    assert any(ln.startswith("✓") and "стр1.md" in ln for ln in report)
    assert any("многострочным" in ln for ln in report)
    assert not any("без источника" in ln and "f1.md" in ln
                   for ln in report)


def test_unparseable_page_ids_is_defect(tmp_path):
    # П-8: ключ задан, id не распознаны — брак, а не молчаливый forward
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md",
         "---\nid: X-01\ntitle: '[X] Ф1'\ntype: function\n"
         "confluence_page_ids: [TBD]\n---\n\n# Т\n\nтекст\n")
    make_matrix(docs)
    make(srcs / "стр1.md", source("[X] Ф1", "111222"))
    report, ok = selfcheck.run(docs, srcs)
    assert not ok
    assert any("id не распознаны" in ln for ln in report)


def test_forward_card_without_key_still_legal(tmp_path):
    # НЕсрабатывание П-8: forward-карточка БЕЗ ключа — по-прежнему норма
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make_matrix(docs)
    make(srcs / "стр1.md", source("[X] Ф1", "111222"))
    report, ok = selfcheck.run(docs, srcs)
    assert ok, report
    assert any("без источника" in ln for ln in report)


class TestCanonCut:
    """Сторож среза канона (П-5b): строка «срез канона: <hash>» профиля
    против фактического HEAD selfcheck; без строки молчит."""

    def _profile(self, tmp_path, line):
        srcs = tmp_path / "conf"
        srcs.mkdir()
        make(tmp_path / "README.md",
             f"# Профиль\n\n| Поле | Значение |\n|---|---|\n{line}\n")
        return srcs

    def test_match_ok(self, tmp_path):
        srcs = self._profile(tmp_path,
                             "| **Срез канона** | `e2b6971` |")
        rep, ok = selfcheck.check_canon_cut(srcs, "e2b6971")
        assert ok and any("✓ срез канона" in ln for ln in rep)

    def test_mismatch_defect(self, tmp_path):
        srcs = self._profile(tmp_path,
                             "| **Срез канона** | `e2b6971` |")
        rep, ok = selfcheck.check_canon_cut(srcs, "deadbee")
        assert not ok
        assert any("✗ срез канона" in ln and "deadbee" in ln
                   for ln in rep)

    def test_no_line_silent(self, tmp_path):
        # НЕсрабатывание: профиль без строки среза — сторож молчит
        srcs = self._profile(tmp_path, "| **service-id** | `CC` |")
        rep, ok = selfcheck.check_canon_cut(srcs, "deadbee")
        assert ok and rep == []

    def test_dev_copy_warns_not_fails(self, tmp_path):
        # dev-копия selfcheck вне канона (head=None) — ⚠, не ✗
        srcs = self._profile(tmp_path,
                             "| **Срез канона** | `e2b6971` |")
        rep, ok = selfcheck.check_canon_cut(srcs, None)
        assert ok and any(ln.startswith("⚠") for ln in rep)

    def test_prefix_lengths_tolerated(self, tmp_path):
        # короткий/длинный хэш одного коммита — совпадение
        srcs = self._profile(tmp_path,
                             "| **Срез канона** | `e2b69712abc` |")
        rep, ok = selfcheck.check_canon_cut(srcs, "e2b6971")
        assert ok, rep


class TestStagePrompts:
    """Сторож полноты промптов этапов (П-5b): каждый этап плана имеет
    prompts/<ЭТАП>.md либо выполненный отчёт в sandbox/; без строки
    «план миграции» в профиле молчит; информационный (ok всегда)."""

    def _stand(self, tmp_path, plan_line=True):
        srcs = tmp_path / "conf"
        srcs.mkdir()
        extra = ("| **План миграции** | `plan.md` |\n" if plan_line
                 else "")
        make(tmp_path / "README.md",
             "# Профиль\n\n| Поле | Значение |\n|---|---|\n"
             "| **service-id** | `CC` |\n" + extra)
        make(tmp_path / "plan.md",
             "# План\n\n| Этап | Тип |\n|---|---|\n"
             "| `PRE-00` | инфраструктура |\n"
             "| `COM-01` | data-model |\n"
             "| `COM-02` | control |\n")
        return srcs

    def test_missing_prompts_reported(self, tmp_path):
        srcs = self._stand(tmp_path)
        make(tmp_path / "prompts" / "COM-02.md", "промпт")
        rep, ok = selfcheck.check_stage_prompts(srcs)
        assert ok
        line = next(ln for ln in rep if ln.startswith("⚠ промпты"))
        assert "PRE-00" in line and "COM-01" in line
        assert "COM-02" not in line

    def test_done_stages_not_required(self, tmp_path):
        # выполненный этап (отчёт в sandbox/) промпта не требует
        srcs = self._stand(tmp_path)
        make(tmp_path / "prompts" / "COM-02.md", "промпт")
        make(tmp_path / "sandbox" / "selfcheck-PRE-00.txt", "отчёт")
        make(tmp_path / "sandbox" / "selfcheck-COM-01-fix.txt", "отчёт")
        rep, _ = selfcheck.check_stage_prompts(srcs)
        assert any(ln.startswith("✓ промпты этапов") for ln in rep), rep

    def test_silent_without_profile_line(self, tmp_path):
        # НЕсрабатывание: без строки «план миграции» — молчание
        srcs = self._stand(tmp_path, plan_line=False)
        rep, ok = selfcheck.check_stage_prompts(srcs)
        assert ok and rep == []

    def test_orphan_prompt_noted(self, tmp_path):
        srcs = self._stand(tmp_path)
        make(tmp_path / "sandbox" / "selfcheck-PRE-00.txt", "x")
        make(tmp_path / "sandbox" / "selfcheck-COM-01.txt", "x")
        make(tmp_path / "prompts" / "COM-02.md", "промпт")
        make(tmp_path / "prompts" / "XXX-99.md", "сирота")
        rep, _ = selfcheck.check_stage_prompts(srcs)
        assert any("XXX-99" in ln and ln.startswith("i ") for ln in rep)
