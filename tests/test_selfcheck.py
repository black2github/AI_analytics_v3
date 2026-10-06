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
             "текст", "[зеплин](https://zeplin.io/project/QQ)"))
    make_matrix(docs)
    report, ok = selfcheck.run(docs, None)
    assert not ok
    assert any("битая" in ln for ln in report)
    assert any("предупреждение" in ln and "zeplin" in ln for ln in report)


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


def test_pardoned_marker_visible_on_ok_file(tmp_path):
    # FB-09: помилованный маркер («и т.д.» дословно из источника) виден
    # при ✓ — исчезновение ⚠ должно быть отличимо от «не проверялось»
    docs = tmp_path / "docs"
    src = tmp_path / "confluence"
    make(src / "page.md",
         "---\ndoc_id: x\ntitle: '[КК] Лимит'\nconfluence_page_id: '2166859948'\n"
         "---\n<p>Описание.</p>\n<p>Может использоваться для контроля "
         "периода, отличного от месяца/квартала и т.д.</p>\n")
    make(docs / "srs/data-model/ent-001-limit.md",
         "---\nid: ENT-001\ntitle: '[КК] Лимит'\ntype: data-model\n"
         "confluence_page_ids: ['2166859948']\n---\n\n# ENT-001. Лимит\n\n"
         "Может использоваться для контроля периода, отличного от "
         "месяца/квартала и т.д.\n")
    make_matrix(docs, "| ENT-001 | data-model | Лимит | ent-001-limit.md |\n")
    report, _ = selfcheck.run(docs, src)
    assert any("ent-001-limit.md" in ln and ln.startswith("✓")
               for ln in report), "\n".join(report)
    assert any("дословно из источника" in ln for ln in report)
    assert not any("маркер сокращения" in ln for ln in report)


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


class TestProtocolDiscipline:
    """Сторожа протокольной дисциплины (П-5c): посторонние скрипты в
    src-репо (§3) и retry сверх лимита (§6); активны только на
    протокольном стенде (строка «срез канона» в профиле)."""

    def _stand(self, tmp_path, cut_line=True):
        srcs = tmp_path / "conf"
        srcs.mkdir(exist_ok=True)
        cut = ("| **Срез канона** | `abc1234` |\n" if cut_line else "")
        make(tmp_path / "README.md",
             "# Профиль\n\n| Поле | Значение |\n|---|---|\n"
             "| **service-id** | `CC` |\n" + cut)
        return srcs

    def test_foreign_script_defect(self, tmp_path):
        srcs = self._stand(tmp_path)
        make(tmp_path / "sandbox" / "build_controls.py", "print(1)")
        rep, ok = selfcheck.check_protocol_discipline(srcs)
        assert not ok
        assert any("§3" in ln and "build_controls.py" in ln for ln in rep)

    def test_retry_3_warns_not_fails(self, tmp_path):
        # retry-3 — легален при параллельных ✗ (кейс z01): ⚠ приёмке
        srcs = self._stand(tmp_path)
        make(tmp_path / "sandbox" / "selfcheck-ISS-02-retry-3.txt", "x")
        rep, ok = selfcheck.check_protocol_discipline(srcs)
        assert ok
        assert any(ln.startswith("⚠") and "retry-3" in ln for ln in rep)

    def test_retry_5_defect(self, tmp_path):
        srcs = self._stand(tmp_path)
        make(tmp_path / "sandbox" / "selfcheck-X-retry-5.txt", "x")
        rep, ok = selfcheck.check_protocol_discipline(srcs)
        assert not ok
        assert any("§6" in ln and "retry-5" in ln for ln in rep)

    def test_retry_2_legal(self, tmp_path):
        # НЕсрабатывание: retry-1/2 — в лимите
        srcs = self._stand(tmp_path)
        make(tmp_path / "sandbox" / "selfcheck-COM-02-retry-2.txt", "x")
        rep, ok = selfcheck.check_protocol_discipline(srcs)
        assert ok and rep == []

    def test_source_scripts_ignored(self, tmp_path):
        # НЕсрабатывание: скрипт среди ДАННЫХ источника — не нарушение
        srcs = self._stand(tmp_path)
        make(srcs / "вложение" / "example.py", "print(1)")
        rep, ok = selfcheck.check_protocol_discipline(srcs)
        assert ok and rep == []

    def test_silent_without_protocol_stand(self, tmp_path):
        # НЕсрабатывание: стенд без строки среза — сторож молчит
        srcs = self._stand(tmp_path, cut_line=False)
        make(tmp_path / "sandbox" / "hack.py", "print(1)")
        rep, ok = selfcheck.check_protocol_discipline(srcs)
        assert ok and rep == []


class TestJournalName:
    """Сторож имени журнала (П-5d): единый sandbox/journal.txt."""

    def test_custom_name_rejected(self, tmp_path):
        srcs = tmp_path / "conf"
        srcs.mkdir()
        w = selfcheck.check_journal_name(
            tmp_path / "sandbox" / "selfcheck-journal.md", srcs)
        assert w and "§4" in w

    def test_canonical_name_ok(self, tmp_path):
        srcs = tmp_path / "conf"
        srcs.mkdir()
        w = selfcheck.check_journal_name(
            tmp_path / "sandbox" / "journal.txt", srcs)
        assert w is None


class TestRegistryDuplicates:
    """Сторож дублей реестровых ID (П-5d): по секции «Реестр ID»."""

    def _matrix(self, tmp_path, body):
        p = tmp_path / "traceability-matrix.md"
        make(p, "# Матрица\n\n## 1. Покрытие\n\n"
                "| FUN-01 | Ф | [SCR-01](s.md) |\n\n"
                "## 4. Реестр ID\n\n| ID | Название | Файл |\n"
                "|---|---|---|\n" + body)
        return p

    def test_duplicate_with_two_files_defect(self, tmp_path):
        p = self._matrix(tmp_path,
                         "| CTL-000 | Общие | `srs/control/README.md` |\n"
                         "| CTL-000 | Подсервис | `srs/cc/README.md` |\n")
        rep, ok = selfcheck.check_registry_duplicates(p)
        assert not ok and any("дубль CTL-000" in ln for ln in rep)

    def test_coverage_repeat_not_flagged(self, tmp_path):
        # НЕсрабатывание: повтор ID в разделах ПОКРЫТИЯ — легален,
        # сторож смотрит только секцию «Реестр ID»
        p = self._matrix(tmp_path,
                         "| FUN-01 | Функция | `srs/f.md` |\n")
        rep, ok = selfcheck.check_registry_duplicates(p)
        assert ok and rep == []

    def test_no_registry_section_silent(self, tmp_path):
        p = tmp_path / "traceability-matrix.md"
        make(p, "# Матрица\n\n| X-01 | а | b.md |\n| X-01 | а | c.md |\n")
        rep, ok = selfcheck.check_registry_duplicates(p)
        assert ok and rep == []


class TestSimilarGroupPoints:
    """Детектор похожих точек применения (П-5e): i-сигналы по общему
    цитируемому литералу ВНУТРИ одного реестра групп."""

    def test_shared_button_flagged(self, tmp_path):
        docs = tmp_path / "docs"
        make(docs / "srs/cc/control/README.md",
             "| ID | Точка применения |\n|---|---|\n"
             "| CTL-GRP-7 | При нажатии «Подписать и отправить» на ЭФ |\n"
             "| CTL-GRP-9 | При нажатии «Подписать и отправить», фаза 2 |\n"
             "| CTL-GRP-8 | При нажатии «Сохранить» |\n")
        rep = selfcheck.check_similar_group_points(docs)
        assert any("CTL-GRP-7 ↔ CTL-GRP-9" in ln
                   and "подписать и отправить" in ln for ln in rep)
        assert not any("CTL-GRP-8" in ln for ln in rep)

    def test_status_backtick_flagged(self, tmp_path):
        docs = tmp_path / "docs"
        make(docs / "srs/cc/control/README.md",
             "| CTL-GRP-14 | Контроли статуса `DRAFT` со стороны ЭФ |\n"
             "| CTL-GRP-24 | Контроли статуса `DRAFT` модели данных |\n")
        rep = selfcheck.check_similar_group_points(docs)
        assert any("draft" in ln for ln in rep)

    def test_cross_registry_not_compared(self, tmp_path):
        # НЕсрабатывание: одинаковая кнопка в РАЗНЫХ реестрах
        # (подсервисах) — разные ЭФ, не сравниваются
        docs = tmp_path / "docs"
        make(docs / "srs/cc-a/control/README.md",
             "| CTL-GRP-1 | При нажатии «Сохранить» на ЭФ A |\n")
        make(docs / "srs/cc-b/control/README.md",
             "| CTL-GRP-2 | При нажатии «Сохранить» на ЭФ B |\n")
        rep = selfcheck.check_similar_group_points(docs)
        assert rep == []


class TestGroupPartPardonSource:
    """z03 ISS-03 (scr-cl-01.4): неглавные карточки группы гоняются без
    source_path — источник группы обязан доезжать до них каналом
    помилований (pardon_source), иначе честное «ОK» из кавычечного
    литерала источника бракует часть формы гомоглифом К-30."""

    def _stand(self, tmp_path, part_body):
        docs, srcs = tmp_path / "docs", tmp_path / "conf"
        make(docs / "srs/ef/01-main.md",
             "---\nid: X-01\ntitle: '[X] Ф1'\ntype: function\n"
             "confluence_page_ids: ['111222']\n---\n\n# Т\n\nтекст\n")
        make(docs / "srs/ef/02-part.md",
             "---\nid: X-02\ntitle: '[X] Ф1 — вкладка'\ntype: function\n"
             "confluence_page_ids: ['111222']\n---\n\n# Т\n\n"
             + part_body)
        make_matrix(docs, "| X-02 | function | Ф2 | f2.md |\n")
        return docs, srcs

    def test_part_homoglyph_from_group_source_pardoned(self, tmp_path):
        docs, srcs = self._stand(tmp_path, 'Кнопка "ОK" — закрыть.\n')
        make(srcs / "стр1.md",
             source("[X] Ф1", "111222",
                    'текст\n\nКнопка "ОK" закрывает.\n'))
        report, ok = selfcheck.run(docs, srcs)
        assert ok, report

    def test_part_alien_homoglyph_still_defect(self, tmp_path):
        # НЕсрабатывание помилования: гомоглифа нет в литералах
        # источника группы — часть бракуется как раньше
        docs, srcs = self._stand(tmp_path, 'Статус "Aктивен".\n')
        make(srcs / "стр1.md", source("[X] Ф1", "111222"))
        report, ok = selfcheck.run(docs, srcs)
        assert not ok
        assert any("02-part.md" in ln and "К-30" in ln for ln in report)


class TestBareEntityMentions:
    """Сторож голых атрибутных обращений (2026-08-29): «Название.<Атрибут>»
    без ссылки при существующей карточке реестра; матчинг по
    наименованиям матрицы, не по тегам [XX]."""

    def _docs(self, tmp_path, card_body):
        docs = tmp_path / "docs"
        make(docs / "traceability-matrix.md",
             "# Матрица\n\n## 4. Реестр ID\n\n"
             "| ID | Название | Файл |\n|---|---|---|\n"
             "| EXT-002 | Клиент Банка | `srs/dm/d.md` |\n"
             "| ENT-003 | Фильтр | `srs/dm/f.md` |\n")
        make(docs / "srs/ef/card.md", card_body)
        return docs

    def test_bare_attribute_access_flagged(self, tmp_path):
        docs = self._docs(tmp_path,
                          "# К\n\nЕсли Клиент Банка.<ОГРН> пусто, то...\n")
        rep = selfcheck.check_bare_entity_mentions(docs)
        assert any("клиент банка" in ln and "EXT-002" in ln for ln in rep)

    def test_linked_access_not_flagged(self, tmp_path):
        # НЕсрабатывание: обращение оформлено ссылкой
        docs = self._docs(
            tmp_path,
            "# К\n\n[EXT-002 Клиент Банка](../dm/d.md).<ОГРН> пусто.\n")
        rep = selfcheck.check_bare_entity_mentions(docs)
        assert rep == []

    def test_short_name_and_plain_mention_not_flagged(self, tmp_path):
        # НЕсрабатывание: односложное имя («Фильтр») и упоминание БЕЗ
        # атрибутного обращения — не флагаются
        docs = self._docs(
            tmp_path,
            "# К\n\nФильтр.<Тип> задан. Просто Клиент Банка в тексте.\n")
        rep = selfcheck.check_bare_entity_mentions(docs)
        assert rep == []


class TestGroupContours:
    """Сторож контура групп (полигон 2026-08-29): явная колонка FE/BE
    сверяется с формулировкой привязки; BE без UI-мест (API First)."""

    def _readme(self, tmp_path, rows):
        docs = tmp_path / "docs"
        make(docs / "srs/cc/control/README.md",
             "# Реестр\n\n| ID | Контур | Привязка | Где |\n"
             "|---|---|---|---|\n" + rows)
        return docs

    def test_consistent_rows_silent(self, tmp_path):
        docs = self._readme(
            tmp_path,
            "| CTL-GRP-6 | FE | При нажатии кнопки «Продолжить» | — |\n"
            "| CTL-GRP-15 | BE | Переход заявки в статус `NEW` | — |\n"
            "| CTL-GRP-18 | BE | При выполнении функции импорта | — |\n")
        assert selfcheck.check_group_contours(docs) == []

    def test_be_with_ui_markers_flagged(self, tmp_path):
        docs = self._readme(
            tmp_path,
            "| CTL-GRP-15 | BE | Попытка сохранения в статус `NEW` при "
            "нажатии кнопки «Продолжить» на ЭФ | — |\n")
        rep = selfcheck.check_group_contours(docs)
        assert any("CTL-GRP-15" in ln and "UI-маркеры" in ln
                   for ln in rep)

    def test_fe_with_status_markers_flagged(self, tmp_path):
        docs = self._readme(
            tmp_path,
            "| CTL-GRP-6 | FE | При нажатии «Продолжить» и переходе "
            "заявки в статус NEW | — |\n")
        rep = selfcheck.check_group_contours(docs)
        assert any("CTL-GRP-6" in ln and "расщепить" in ln for ln in rep)

    def test_undetermined_binding_flagged(self, tmp_path):
        # «забыли упомянуть статусы» — вопрос аналитику, не догадка
        docs = self._readme(
            tmp_path,
            "| CTL-GRP-9 | BE | Проверки данных держателя | — |\n")
        rep = selfcheck.check_group_contours(docs)
        assert any("CTL-GRP-9" in ln and "вопрос аналитику" in ln
                   for ln in rep)

    def test_registry_without_contour_column_flagged_once(self, tmp_path):
        docs = tmp_path / "docs"
        make(docs / "srs/cc/control/README.md",
             "# Реестр\n\n| ID | Точка применения | Где |\n|---|---|---|\n"
             "| CTL-GRP-1 | При нажатии «X» | — |\n"
             "| CTL-GRP-2 | При нажатии «Y» | — |\n")
        rep = selfcheck.check_group_contours(docs)
        assert len(rep) == 1 and "без колонки «Контур»" in rep[0]

    def test_similar_points_reads_third_column(self, tmp_path):
        # детектор похожих точек понимает формат с колонкой «Контур»
        docs = self._readme(
            tmp_path,
            "| CTL-GRP-7 | FE | При нажатии «Подписать и отправить» | — |\n"
            "| CTL-GRP-9 | FE | При нажатии «Подписать и отправить», "
            "фаза 2 | — |\n")
        rep = selfcheck.check_similar_group_points(docs)
        assert any("CTL-GRP-7 ↔ CTL-GRP-9" in ln for ln in rep)


class TestGroupFigmaInReadme:
    """Макеты Figma группы (2026-08-31): живут в несверяемом README —
    наличие держит сторож группы."""

    def _stand(self, tmp_path, readme_body):
        docs, srcs = tmp_path / "docs", tmp_path / "conf"
        make(docs / "srs/ef/g/scr-x-01-main.md",
             "---\nid: X-01\ntitle: '[X] Ф1'\ntype: screen-form\n"
             "confluence_page_ids: ['111222']\n---\n\n# Т\n\nтекст\n")
        make(docs / "srs/ef/g/README.md", readme_body)
        make_matrix(docs)
        make(srcs / "стр1.md", source(
            "[X] Ф1", "111222",
            'текст\n\nМакет: <a href="https://www.figma.com/design/'
            'x">ссылка</a>\n'))
        return docs, srcs

    def test_readme_without_figma_warned(self, tmp_path):
        docs, srcs = self._stand(tmp_path, "# Ф\n\nоглавление\n")
        report, ok = selfcheck.run(docs, srcs)
        assert ok, report
        assert any("README-оглавление группы — нет" in ln
                   for ln in report)

    def test_readme_with_figma_silent(self, tmp_path):
        docs, srcs = self._stand(
            tmp_path,
            "# Ф\n\n[макет](https://www.figma.com/design/x)\n")
        report, ok = selfcheck.run(docs, srcs)
        assert ok, report
        assert not any("README-оглавление группы — нет" in ln
                       for ln in report)


def test_stray_sidecar_in_sources_flagged(tmp_path):
    # §5 (STS-01): sidecar рядом с источниками — нормализатор гоняли
    # по выгрузке, а не по копии
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(tmp_path / "README.md", "| **Срез канона** | `abc1234` |")
    make(srcs / "стр1.md", source("[X] Ф1", "111222"))
    make(srcs / "стр1.md.tables.md", "| sidecar |")
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "111222"))
    make_matrix(docs)
    report, ok = selfcheck.run(docs, srcs)
    assert not ok
    assert any("§5" in ln and "sidecar" in ln for ln in report)


class TestFileArtifacts:
    """Сторож не-markdown артефактов files/ (Д-24): сирота и битая
    ссылка — ✗; связанный файл и img/ — не срабатывает."""

    def _docs(self, tmp_path):
        docs = tmp_path / "docs"
        (docs / "srs" / "contract" / "files").mkdir(parents=True)
        return docs

    def test_linked_artifact_ok(self, tmp_path):
        from selfcheck import check_file_artifacts
        docs = self._docs(tmp_path)
        (docs / "srs" / "contract" / "files" / "req.xsd").write_bytes(
            b"<xs:schema/>")
        (docs / "srs" / "contract" / "card.md").write_text(
            "---\nid: EXTINT-001\n---\n\n"
            "Нормативная схема: [req.xsd](files/req.xsd)\n",
            encoding="utf-8")
        rep, ok = check_file_artifacts(docs)
        assert ok and rep == []

    def test_orphan_artifact_flagged(self, tmp_path):
        from selfcheck import check_file_artifacts
        docs = self._docs(tmp_path)
        (docs / "srs" / "contract" / "files" / "orphan.xsd").write_bytes(
            b"<xs:schema/>")
        rep, ok = check_file_artifacts(docs)
        assert not ok
        assert any("сирота" in ln and "orphan.xsd" in ln for ln in rep)

    def test_broken_files_link_flagged(self, tmp_path):
        from selfcheck import check_file_artifacts
        docs = self._docs(tmp_path)
        (docs / "srs" / "contract" / "card.md").write_text(
            "---\nid: EXTINT-001\n---\n\n"
            "[схема](files/missing.xsd)\n", encoding="utf-8")
        rep, ok = check_file_artifacts(docs)
        assert not ok
        assert any("битая ссылка" in ln and "missing.xsd" in ln
                   for ln in rep)

    def test_img_not_guarded(self, tmp_path):
        # НЕсрабатывание: img/ — конвенция картинок, сторож молчит
        from selfcheck import check_file_artifacts
        docs = self._docs(tmp_path)
        (docs / "srs" / "img").mkdir(parents=True)
        (docs / "srs" / "img" / "pic.png").write_bytes(b"\x89PNG")
        rep, ok = check_file_artifacts(docs)
        assert ok and rep == []

    def test_url_encoded_link_resolves(self, tmp_path):
        # НЕсрабатывание: имя с пробелом, ссылка с %20 — файл связан
        from selfcheck import check_file_artifacts
        docs = self._docs(tmp_path)
        (docs / "srs" / "contract" / "files" / "req 1.xsd").write_bytes(
            b"<xs:schema/>")
        (docs / "srs" / "contract" / "card.md").write_text(
            "---\nid: EXTINT-001\n---\n\n"
            "[схема](files/req%201.xsd)\n", encoding="utf-8")
        rep, ok = check_file_artifacts(docs)
        assert ok, rep


def test_root_prompts_dir_is_legit_and_junk_still_flagged(tmp_path):
    # prompts/ — промпты этапов (протокол §10): штатный каталог корня,
    # не «посторонний»; каталог скриптов/кэш по-прежнему брак (пара)
    docs = tmp_path / "docs"
    (tmp_path / ".git").mkdir()             # стендовая топология: репозиторий = родитель docs
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make_matrix(docs)
    make(tmp_path / "prompts/PRE-01.md", "# промпт этапа\n")
    make(tmp_path / "sandbox/journal.txt", "")
    report, ok = selfcheck.run(docs, None)
    assert ok, report
    assert not any("посторонние файлы" in ln for ln in report)
    make(tmp_path / "__pycache__/x.pyc", "")
    make(tmp_path / "fix_all.py", "print(1)\n")
    report, ok = selfcheck.run(docs, None)
    assert not ok
    junk = [ln for ln in report if "посторонние файлы" in ln]
    assert junk and "__pycache__" in junk[0] and "fix_all.py" in junk[0]
    assert "prompts" not in junk[0].split(" — ")[0]      # не в перечне мусора


def test_root_topology_repo_root_as_docs(tmp_path):
    # эталонная топология: --docs = корень репозитория (есть .git):
    # brd/srs штатны, а мусор в корне флагуется
    docs = tmp_path
    (docs / ".git").mkdir()
    make(docs / "srs/functions/f1.md", card("[X] Ф1"))
    make(docs / "brd/b.md", "# brd\n")
    make_matrix(docs)
    report, ok = selfcheck.run(docs, None)
    assert ok, report
    make(docs / "build.py", "print(1)\n")
    report, ok = selfcheck.run(docs, None)
    assert not ok
    junk = [ln for ln in report if "посторонние файлы" in ln]
    assert junk and "build.py" in junk[0] and "srs" not in junk[0]


def _slot_card(cid: str, typ: str = "function") -> str:
    return f"---\nid: {cid}\ntype: {typ}\n---\n\n# {cid}\n\nтекст\n"


_PART_TABLE = ("# Комплект\n\n### Подсервисы (слот в ID)\n\n"
               "| Код | Каталог | Подсервис |\n|---|---|---|\n"
               "| **SHR** | `shared` | Общая часть |\n"
               "| **DS** | `document-signing` | Подпись документов |\n")


def test_id_slots_silent_without_parts(tmp_path):
    # сервис без подсервисов и без таблицы: сторож молчит
    docs = tmp_path / "docs"
    make(docs / "srs/function/f1.md", card("[X] Ф1"))
    make_matrix(docs)
    report, _ = selfcheck.run(docs, None)
    assert not any("слот части" in ln for ln in report)


def test_id_slots_dirs_without_table_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "srs/document-signing/function/f1.md", _slot_card("FUN-DS-SYS-01"))
    make_matrix(docs, "| FUN-DS-SYS-01 | function | Ф | f1.md |\n")
    report, ok = selfcheck.run(docs, None)
    assert not ok
    assert any("без таблицы кодов частей" in ln and "FUN-DS-SYS-01" in ln for ln in report)


def test_id_slots_table_without_folder_column_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "README.md", "# К\n\n### Подсервисы (слот в ID)\n\n| Код | Подсервис |\n|---|---|\n| **DS** | Подпись |\n")
    make(docs / "srs/document-signing/function/f1.md", _slot_card("FUN-DS-SYS-01"))
    make_matrix(docs, "| FUN-DS-SYS-01 | function | Ф | f1.md |\n")
    report, ok = selfcheck.run(docs, None)
    assert not ok
    assert any("нет колонки «Каталог»" in ln for ln in report)


def test_id_slots_happy_layout(tmp_path):
    # раскладка docs-sign: слоты по таблице, общая часть в shared/, корень без слота
    docs = tmp_path / "docs"
    make(docs / "README.md", _PART_TABLE)
    make(docs / "srs/document-signing/function/f1.md", _slot_card("FUN-DS-SYS-01"))
    make(docs / "srs/document-signing/ntf-notification.md", _slot_card("NTF-DS-000", "notification"))
    make(docs / "srs/shared/data-model/e1.md", _slot_card("ENT-SHR-001", "data-model"))
    make(docs / "srs/platform-functions.md", _slot_card("PLT-000", "platform-function"))
    make(docs / "srs/control/README.md", _slot_card("CTL-000", "control"))
    make_matrix(docs, "| FUN-DS-SYS-01 | function | Ф | f1.md |\n| NTF-DS-000 | notification | Н | n.md |\n"
                      "| ENT-SHR-001 | data-model | С | e1.md |\n| PLT-000 | platform-function | П | p.md |\n"
                      "| CTL-000 | control | К | c.md |\n")
    report, _ = selfcheck.run(docs, None)
    assert any("слоты частей: 2 кодов" in ln for ln in report), report
    assert not any(ln.strip().startswith("✗ слот части") for ln in report)


def test_id_slots_violations_each_flagged(tmp_path):
    docs = tmp_path / "docs"
    make(docs / "README.md", _PART_TABLE)
    make(docs / "srs/document-signing/function/f1.md", _slot_card("FUN-SHR-SYS-01"))   # чужой слот
    make(docs / "srs/document-signing/function/f2.md", _slot_card("FUN-SYS-02"))       # без слота
    make(docs / "srs/rbac.md", _slot_card("RBAC-DS-001", "rbac"))                       # слот у корня
    make(docs / "srs/multi-bank/function/f3.md", _slot_card("FUN-MB-SYS-01"))          # каталог не объявлен
    make_matrix(docs, "| FUN-SHR-SYS-01 | function | Ф | f1.md |\n| FUN-SYS-02 | function | Ф | f2.md |\n"
                      "| RBAC-DS-001 | rbac | Р | rbac.md |\n| FUN-MB-SYS-01 | function | Ф | f3.md |\n")
    report, ok = selfcheck.run(docs, None)
    assert not ok
    lines = [ln for ln in report if ln.strip().startswith("✗ слот части:")]
    assert len(lines) == 4, lines
    assert any("несёт слот «SHR»" in ln and "«DS»" in ln for ln in lines)
    assert any("без слота" in ln for ln in lines)
    assert any("вне каталогов подсервисов" in ln for ln in lines)
    assert any("«multi-bank» не объявлен" in ln for ln in lines)


# --- сторож каталога сервисов (2026-09-29) ---

def _catalog(tmp_path, items) -> Path:
    import json
    cat = tmp_path / "services.json"
    cat.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return cat


def _docs_with_service(tmp_path, code: str, n: int = 2) -> Path:
    docs = tmp_path / "docs"; docs.mkdir(exist_ok=True)
    for i in range(n):
        (docs / f"fun-cl-0{i + 1}-x.md").write_text(
            f"---\nid: FUN-CL-0{i + 1}\ntitle: 'x'\ntype: function\n"
            f"service: {code}\n---\n\n# x\n", encoding="utf-8")
    return docs


def test_catalog_guard_silent_without_catalog(tmp_path):
    docs = _docs_with_service(tmp_path, "business-cards")
    rep, ok = selfcheck.check_service_catalog(None, docs)
    assert rep == [] and ok


def test_catalog_guard_own_code_found_with_repo(tmp_path):
    docs = _docs_with_service(tmp_path, "business-cards")
    cat = _catalog(tmp_path, [
        {"code": "business-cards", "key": "CORP_CARDS", "name": "[КК]",
         "is_platform": False,
         "repo": "https://gitlab.gboteam.ru/EAS/src-business-cards/-/tree/HEAD/docs"},
        {"code": "locks", "key": "LK", "name": "Блокировки", "is_platform": True,
         "repo": "https://gitlab.gboteam.ru/EAS/src-locks"},
    ])
    rep, ok = selfcheck.check_service_catalog(cat, docs)
    assert ok and len(rep) == 1
    assert rep[0].startswith("✓ каталог сервисов: код `business-cards` (2 файлов)")
    assert "tree/HEAD/docs" in rep[0]


def test_catalog_guard_duplicates_code_and_key(tmp_path):
    docs = _docs_with_service(tmp_path, "business-cards")
    cat = _catalog(tmp_path, [
        {"code": "business-cards", "key": "CORP_CARDS", "name": "[КК]"},
        {"code": "EPR", "key": "EP", "name": "[ЕПР] Сервис распознавания", "is_platform": True},
        {"code": "EPR", "key": "EP", "name": "АС ЕПР", "is_platform": False},
    ])
    rep, ok = selfcheck.check_service_catalog(cat, docs)
    assert ok
    warns = [l for l in rep if l.startswith("⚠")]
    assert len(warns) == 2
    assert "код `EPR` у 2 записей" in warns[0] and "АС ЕПР" in warns[0]
    assert "ключ `EP` у 2 записей" in warns[1]


def test_catalog_guard_repo_formats(tmp_path):
    docs = _docs_with_service(tmp_path, "business-cards")
    cat = _catalog(tmp_path, [
        {"code": "business-cards", "key": "K1", "name": "n1",
         "repo": "https://gitlab.gboteam.ru/EAS/src-business-cards/-/tree/HEAD/docs"},
        {"code": "a", "key": "K2", "name": "n2",
         "repo": "https://gitlab.gboteam.ru/EAS/src-common-dictionary/-/tree/master/output/types_doc/docs?ref_type=heads"},
        {"code": "b", "key": "K3", "name": "n3",
         "repo": "https://gitlab.gboteam.ru/EAS/src-common-dictionary/-/tree/master/output/okfs/docs"},
        {"code": "c", "key": "K4", "name": "n4",
         "repo": "https://gitlab.gboteam.ru/EAN/docs-o2new/-/blob/master/output/x/docs"},
        {"code": "d", "key": "K5", "name": "n5",
         "repo": "https://github.com/x/y"},
        {"code": "e", "key": "K6", "name": "n6",
         "repo": "https://gitlab.gboteam.ru/EAS/src-invite"},
    ])
    rep, ok = selfcheck.check_service_catalog(cat, docs)
    assert ok
    warns = [l for l in rep if l.startswith("⚠")]
    assert [w.split("`")[1] for w in warns] == ["a", "b", "c", "d"]
    assert "?ref_type=heads" in warns[0] and "хвост запроса" in warns[0]
    assert "имя ветки `master`" in warns[1]
    assert "`/-/blob/`" in warns[2]
    assert "не в GitLab контура" in warns[3]
    # тест на НЕсрабатывание: e (корень репозитория) и business-cards (HEAD) — без ⚠
    assert not any("`e`" in w or "`business-cards`" in w for w in warns)


def test_catalog_guard_own_code_missing_is_warning_not_defect(tmp_path):
    # референс-стенд КК: frontmatter `service: CC`, в каталоге `business-cards`
    docs = _docs_with_service(tmp_path, "CC", n=3)
    cat = _catalog(tmp_path, [{"code": "business-cards", "key": "CORP_CARDS", "name": "[КК]"}])
    rep, ok = selfcheck.check_service_catalog(cat, docs)
    assert ok  # вердикт не трогает (решение о ✗ — после приведения frontmatter пилота)
    assert len(rep) == 1 and rep[0].startswith("⚠ каталог сервисов: код `CC` из frontmatter 3 файлов не найден")


def test_catalog_guard_broken_json(tmp_path):
    docs = _docs_with_service(tmp_path, "business-cards")
    cat = tmp_path / "services.json"; cat.write_text("[{\"code\": ", encoding="utf-8")
    rep, ok = selfcheck.check_service_catalog(cat, docs)
    assert ok and len(rep) == 1 and rep[0].startswith("⚠ каталог сервисов: services.json не читается")


def test_catalog_guard_wired_into_run(tmp_path):
    docs = _docs_with_service(tmp_path, "business-cards", n=1)
    cat = _catalog(tmp_path, [
        {"code": "business-cards", "key": "K", "name": "[КК]"},
        {"code": "EPR", "key": "E1", "name": "a"}, {"code": "EPR", "key": "E2", "name": "b"},
    ])
    report, _ok = selfcheck.run(docs, None, catalog=cat)
    assert any(l.startswith("⚠ каталог сервисов: код `EPR` у 2 записей") for l in report)
    assert any(l.startswith("✓ каталог сервисов: код `business-cards`") for l in report)
    # без каталога и вне канона (dev-копия) — ни строки
    report2, _ = selfcheck.run(docs, None)
    assert not any("каталог сервисов" in l for l in report2)


# --- сторож ссылок-названий на сущности (2026-10-02) ---

_ENT16 = "../data-model/ent-016-card-issue-request.md"


def _card_with_body(tmp_path, body: str, name: str = "fun-cl-01-x.md") -> Path:
    docs = tmp_path / "docs"; (docs / "function").mkdir(parents=True, exist_ok=True)
    (docs / "function" / name).write_text(
        "---\nid: FUN-CL-01\ntitle: 'x'\ntype: function\nservice: business-cards\n---\n\n"
        "# FUN-CL-01. x\n\n" + body + "\n", encoding="utf-8")
    return docs


def test_named_link_after_full_link_is_ok(tmp_path):
    docs = _card_with_body(tmp_path,
        f"Создаётся [ENT-016 Заявка на выпуск карты]({_ENT16}). В [Заявке на выпуск карты]({_ENT16}) "
        f"заполняется [ENT-016]({_ENT16}).«ИНН клиента».")
    assert selfcheck.check_named_entity_links(docs) == []


def test_named_link_without_full_link_flagged(tmp_path):
    docs = _card_with_body(tmp_path,
        f"В [Заявке на выпуск карты]({_ENT16}) заполняется ИНН. [Заявка]({_ENT16}) сохраняется.")
    rep = selfcheck.check_named_entity_links(docs)
    assert len(rep) == 1 and "ENT-016 названием без ID ×2" in rep[0]
    assert "полной ссылки `[ENT-016 <название>]`" in rep[0] and "документе нет" in rep[0]


def test_named_link_before_full_link_flagged(tmp_path):
    docs = _card_with_body(tmp_path,
        f"В [Заявке на выпуск карты]({_ENT16}) заполняется ИНН. "
        f"Затем [ENT-016 Заявка на выпуск карты]({_ENT16}) сохраняется.")
    rep = selfcheck.check_named_entity_links(docs)
    assert len(rep) == 1 and "стоит раньше полной ссылки" in rep[0]


def test_named_links_guard_silent_on_old_form(tmp_path):
    # тест на НЕсрабатывание: старая форма (одни короткие ссылки, даже без
    # полной) сторожем не затрагивается — остаётся допустимой
    docs = _card_with_body(tmp_path,
        f"Значение = [ENT-016]({_ENT16}).«Фамилия» + [ENT-016]({_ENT16}).«Имя».")
    assert selfcheck.check_named_entity_links(docs) == []


def test_named_links_guard_nested_brackets_tag_and_part_slot(tmp_path):
    ent20 = "../data-model/ent-020-card-status-change-request.md"
    shr = "../../shared/data-model/ent-shr-012-signature-profile.md"
    docs = _card_with_body(tmp_path,
        f"Создаётся [ENT-020 [КК_БК] Заявка на изменение статуса карты]({ent20}); в [заявке]({ent20}) "
        f"указывается [профиль подписи]({shr}).")
    rep = selfcheck.check_named_entity_links(docs)
    # полная ссылка с тегом в квадратных скобках распознана — по ENT-020 тихо;
    # слот части в имени файла даёт ID ENT-SHR-012, полной ссылки на него нет
    assert len(rep) == 1 and "ENT-SHR-012 названием без ID ×1" in rep[0]


def test_named_links_guard_skips_filenames_code_and_registries(tmp_path):
    docs = _card_with_body(tmp_path,
        f"Файл: [ent-016-card-issue-request.md]({_ENT16}).\n\n```markdown\n[Заявка]({_ENT16})\n```\n")
    (docs / "function" / "README.md").write_text(
        f"| ID | Файл |\n|---|---|\n| ENT-016 | [Заявка]({_ENT16}) |\n", encoding="utf-8")
    assert selfcheck.check_named_entity_links(docs) == []


def test_named_links_guard_title_hint_does_not_replace_full_link(tmp_path):
    # ID в подсказке ссылки — не видимый текст: полная ссылка всё равно нужна
    docs = _card_with_body(tmp_path, f'В [Заявке на выпуск карты]({_ENT16} "ENT-016") заполняется ИНН.')
    rep = selfcheck.check_named_entity_links(docs)
    assert len(rep) == 1 and "ENT-016 названием без ID ×1" in rep[0]


def test_named_links_guard_wired_into_run_as_warning(tmp_path):
    docs = _card_with_body(tmp_path, f"В [Заявке на выпуск карты]({_ENT16}) заполняется ИНН.")
    report, _ok = selfcheck.run(docs, None)
    lines = [l for l in report if "названием без ID" in l]
    assert len(lines) == 1 and lines[0].startswith("⚠ ")


def test_named_links_guard_tagged_source_name_counts_as_full(tmp_path):
    # тест на НЕсрабатывание: дословное имя источника с тегом сервиса —
    # полноценное упоминание (практика reverse-переноса, стенд КК);
    # экранированная и неэкранированная запись тега
    esc = "[\\[КК_ВК\\] Заявка на выпуск карты](" + _ENT16 + ")"
    raw = "[[КК_ВК] Заявка на выпуск карты](" + _ENT16 + ")"
    free = "[заявке](" + _ENT16 + ")"
    docs = _card_with_body(tmp_path, f"Создаётся запись {esc}; далее в {free} заполняется ИНН.")
    assert selfcheck.check_named_entity_links(docs) == []
    docs2 = _card_with_body(tmp_path / "b", f"Создаётся запись {raw}; далее в {free} ИНН.")
    assert selfcheck.check_named_entity_links(docs2) == []
    # свободное название раньше дословного с тегом — сигнал порядка
    docs3 = _card_with_body(tmp_path / "c", f"В {free} ИНН. Затем {esc}.")
    rep = selfcheck.check_named_entity_links(docs3)
    assert len(rep) == 1 and "стоит раньше полной ссылки" in rep[0]


# --- пустой источник (2026-10-05) ---

def _frozen_source(title: str, pid: str) -> str:
    return (f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n"
            f"unapproved_jira: GBO-143661\n---\n")


def test_empty_frozen_source_is_defect(tmp_path):
    # страница заморожена: после reject-all от неё один frontmatter —
    # карточка раньше получала ✓ без сверки; с 2026-10-05 это ✗
    # (решение владельца по FB-08: предупреждение не остановило бы сборку
    # карточек из архива raw)
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "111222"))
    make_matrix(docs)
    make(srcs / "стр1.md", _frozen_source("[X] Ф1", "111222"))
    report, ok = selfcheck.run(docs, srcs)
    assert not ok
    assert any(ln.startswith("✗") and "стр1.md" in ln for ln in report)
    assert any("источник пуст: страница заморожена флагом unapproved_jira "
               "(GBO-143661)" in ln for ln in report)
    assert not any(ln.startswith(("✓", "⚠")) and "стр1.md" in ln
                   for ln in report)
    assert any("ИТОГО: файлов 2 — ✓ 0, ✗ 1, ⚠ 1" in ln and "БРАК" in ln
               for ln in report)


def test_frozen_flag_with_text_is_not_empty_source(tmp_path):
    # тест на НЕсрабатывание: флаг заморозки есть, но тело страницы не
    # пусто (страница разморожена частично либо флаг снят не до конца) —
    # сторож пустого источника молчит, идёт обычная сверка
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "111222"))
    make_matrix(docs)
    make(srcs / "стр1.md",
         _frozen_source("[X] Ф1", "111222") + "\nтекст\n")
    report, ok = selfcheck.run(docs, srcs)
    assert ok, report
    assert not any("источник пуст" in ln for ln in report)


def test_empty_source_without_flag_gives_warning(tmp_path):
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "111222"))
    make_matrix(docs)
    make(srcs / "стр1.md", source("[X] Ф1", "111222", body="\n  \n"))
    report, _ = selfcheck.run(docs, srcs)
    assert any("источник пуст: в теле страницы-источника нет текста" in ln
               for ln in report)
    assert any(ln.startswith("⚠") and "стр1.md" in ln for ln in report)


def test_nonempty_source_and_readme_container_not_flagged(tmp_path):
    # тесты на НЕсрабатывание: (1) источник с одной строкой текста — не
    # пуст; (2) README-оглавление на странице-контейнере без текста — норма
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    make(docs / "srs/functions/f1.md", card("[X] Ф1", "111222"))
    make(docs / "srs/functions/README.md", card("[X] Функции", "333444"))
    make_matrix(docs)
    make(srcs / "стр1.md", source("[X] Ф1", "111222", body="текст\n"))
    make(srcs / "оглавление.md", source("[X] Функции", "333444", body=""))
    report, _ = selfcheck.run(docs, srcs)
    assert not any("источник пуст" in ln for ln in report), report
    assert any(ln.startswith("✓") and "стр1.md" in ln for ln in report)
    assert any(ln.startswith("✓") and "оглавление.md" in ln for ln in report)


def test_empty_source_keeps_defect_and_adds_note(tmp_path):
    # карточка с браком внутренних сторожей остаётся ✗, пояснение о
    # пустом источнике добавляется строкой
    docs, srcs = tmp_path / "docs", tmp_path / "conf"
    bad = card("[X] Ф1", "111222").replace("текст\n", "см. page 2169849859\n")
    make(docs / "srs/functions/f1.md", bad)
    make_matrix(docs)
    make(srcs / "стр1.md", _frozen_source("[X] Ф1", "111222"))
    report, ok = selfcheck.run(docs, srcs)
    assert not ok
    assert any(ln.startswith("✗") and "стр1.md" in ln for ln in report)
    assert any("источник пуст" in ln for ln in report)


def test_delta_report_explains_counting(tmp_path):
    # в дельту входят файлы (каждый файл группы отдельно) и ✗ сторожей
    # уровня комплекта: два файла + «срез канона» = 3, тогда как ИТОГО
    # по тем же строкам насчитал бы 2 файла
    base = tmp_path / "base.txt"
    base.write_text("# ✓ a.md ← s.md\n# ИТОГО: файлов 1 — ✓ 1, ✗ 0, ⚠ 0\n", encoding="utf-8")
    out = selfcheck.delta_report(base, ["✗ a.md, b.md ← s.md", "✗ срез канона: x"])
    assert out[0].endswith("✗ было 0 → стало 3")
    assert "в счёт дельты входят и ✗ сторожей уровня комплекта" in out[1]
    assert any("НОВЫЕ ✗ ×3" in ln for ln in out)


class TestApiSpecInCodeRepo:
    """Решение 2026-10-06: контракты OpenAPI/AsyncAPI — в api-specification/
    репозитория кода; каталог api/ и YAML в комплекте — ⚠; ссылки матрицы
    «API ↔ SRS» — через HEAD, явный ref только по шапке раздела; поле api
    каталога — для исключений."""

    def test_api_dir_and_yaml_warned_not_failed(self, tmp_path):
        docs = tmp_path / "docs"
        make(docs / "srs/x/api/rest/a.yaml", "openapi: 3.0.0\n")
        make(docs / "srs/y/b-asyncapi.yaml", "asyncapi: 3.0.0\n")
        make(docs / "srs/z/notes.yaml", "foo: bar\n")  # не контракт
        rep, ok = selfcheck.check_no_api_in_bundle(docs)
        assert ok
        assert any("каталог srs/x/api/ (1 файлов)" in l for l in rep), rep
        assert any("YAML OpenAPI/AsyncAPI ×1 (srs/y/b-asyncapi.yaml)" in l for l in rep), rep
        assert not any("notes.yaml" in l for l in rep)

    def test_clean_bundle_silent(self, tmp_path):
        # НЕсрабатывание: комплект без api/ и без контрактов — ни строки
        docs = tmp_path / "docs"
        make(docs / "srs/f.md", "x\n")
        assert selfcheck.check_no_api_in_bundle(docs) == ([], True)

    def _matrix(self, tmp_path, header, rows):
        docs = tmp_path / "docs"
        make(docs / "traceability-matrix.md",
             "# Матрица\n\n## 1. Покрытие\n\n| a |\n|---|\n\n"
             "## 3. Покрытие: API ↔ SRS\n\n" + header +
             "| Операция | Артефакты SRS |\n| --- | --- |\n" + rows +
             "\n## 4. Реестр ID\n\n| ID |\n|---|\n")
        return docs

    def test_head_links_silent(self, tmp_path):
        docs = self._matrix(tmp_path, "", "| POST /a | FUN-01 — Источник: https://gitlab.gboteam.ru/ECO_BE/ms-x/-/blob/HEAD/api-specification/x.yaml |\n")
        assert selfcheck.check_api_matrix_refs(docs) == ([], True)
        assert selfcheck.check_api_matrix_refs(docs, strict=True) == ([], True)

    def test_default_branch_warn_soft_fail_strict(self, tmp_path):
        docs = self._matrix(tmp_path, "", "| POST /a | https://gitlab.gboteam.ru/ECO_BE/ms-x/-/blob/master/api-specification/x.yaml |\n| POST /b | https://gitlab.gboteam.ru/ECO_BE/ms-x/-/blob/master/api-specification/x.yaml |\n")
        rep, ok = selfcheck.check_api_matrix_refs(docs)
        assert ok and rep[0].startswith("⚠ матрица «API ↔ SRS»: ссылки с именем ветки по умолчанию `master` ×2")
        rep, ok = selfcheck.check_api_matrix_refs(docs, strict=True)
        assert not ok and rep[0].startswith("✗ матрица")

    def test_declared_ref_in_header_accepted_other_ref_warned(self, tmp_path):
        header = "Комплект описывает промышленный срез: ссылки на тег `v2.4.0` (основная ветка — разработка).\n\n"
        docs = self._matrix(tmp_path, header,
                            "| POST /a | https://gitlab.gboteam.ru/ECO_BE/ms-x/-/blob/v2.4.0/api-specification/x.yaml |\n"
                            "| POST /b | https://gitlab.gboteam.ru/ECO_BE/ms-x/-/blob/release-1/api-specification/x.yaml |\n")
        rep, ok = selfcheck.check_api_matrix_refs(docs, strict=True)
        assert ok, rep
        assert any(l.startswith("⚠ матрица «API ↔ SRS»: ссылки с явным ref `release-1` ×1") for l in rep)
        assert any(l.startswith("i матрица «API ↔ SRS»: в шапке раздела назван ref v2.4.0") for l in rep)
        assert not any("v2.4.0` ×" in l for l in rep)

    def test_subsections_inside_and_prose_backticks_not_refs(self, tmp_path):
        # docs-sign: подразделы «### 3.1 …» входят в раздел; кавычки прозы
        # шапки (пути, ID) не считаются объявленным ref
        header = ("Собственные методы — карточки `srs/shared/internal-contract/`, "
                  "ID `INTC`.\n\n### 3.1. REST\n\n")
        docs = self._matrix(tmp_path, header,
                            "| POST /a | https://gitlab.gboteam.ru/ECO_BE/ms-x/-/blob/master/api-specification/x.yaml |\n")
        rep, ok = selfcheck.check_api_matrix_refs(docs, strict=True)
        assert not ok and rep[0].startswith("✗ матрица «API ↔ SRS»: ссылки с именем ветки по умолчанию `master` ×1")
        assert not any(l.startswith("i матрица") for l in rep)

    def test_refs_outside_section_ignored(self, tmp_path):
        # НЕсрабатывание: ссылка с веткой в другом разделе матрицы — не этот сторож
        docs = tmp_path / "docs"
        make(docs / "traceability-matrix.md",
             "# Матрица\n\n## 6. Долги\n\n| x | https://gitlab.gboteam.ru/EAN/docs-o2new/-/blob/master/a.md |\n")
        assert selfcheck.check_api_matrix_refs(docs, strict=True) == ([], True)

    def test_catalog_api_field_format_and_redundancy(self, tmp_path):
        docs = _docs_with_service(tmp_path, "cards-core", n=1)
        cat = _catalog(tmp_path, [
            {"code": "cards-core", "key": "CC", "name": "a",
             "api": "https://gitlab.gboteam.ru/ECO_BE/ms-cards-core/-/tree/HEAD/api-specification"},
            {"code": "other", "key": "O", "name": "b",
             "api": "https://gitlab.gboteam.ru/ECO_BE/ms-other-core/-/tree/master/api-specification"},
            {"code": "third", "key": "T", "name": "c",
             "api": "https://gitlab.gboteam.ru/ECO_BE/ms-third-a/-/tree/HEAD/api-specification"},
        ])
        rep, ok = selfcheck.check_service_catalog(cat, docs)
        assert ok
        assert any(l.startswith("⚠ каталог сервисов: api у `cards-core` совпадает с адресом по правилу") for l in rep)
        assert any(l.startswith("⚠ каталог сервисов: api у `other` — имя ветки `master`") for l in rep)
        assert not any("`third`" in l and "⚠" in l for l in rep)
