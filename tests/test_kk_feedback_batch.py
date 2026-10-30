# tests/test_kk_feedback_batch.py
"""КК feedback 16.10: FB-16 (ячейка-ссылка на Confluence не потеря; гомоглиф
дословно из текста источника помилован; К-26 — только уровни при совпадении
текста = ⚠), FB-19 (амнистия длинных строк по объединению страниц карточки),
FB-20 (помилование тега с гомоглифом), FB-21 (raw/ не индексируется)."""
from pathlib import Path

from app.scripts.CI import selfcheck
from app.scripts.CI.kitcheck.checks.card_run import check_file
from app.scripts.CI.kitcheck.checks.card_source import check_source_tables
from app.scripts.CI.kitcheck.checks.card_steps import check_step_body_structure


def test_confluence_url_cell_is_not_a_loss():
    # FB-16.1: значение источника — живая ссылка на Confluence; перенос запрещён
    src = ("Текст.\n\n| Система | Описание |\n|---|---|\n"
           "| АБС РКО Ф1 | Cм. внутр. Сonfluence [https://confluence.int.gazprombank.ru/pages/1](https://confluence.int.gazprombank.ru/pages/1) |\n"
           "| ЭКО | Сервис карт |\n")
    card = "| Система | Описание |\n|---|---|\n| АБС РКО Ф1 | — |\n| ЭКО | Сервис карт |\n"
    rep, ok = check_source_tables(card, src)
    assert ok, rep
    assert any("ячейки-ссылки на Confluence ×1" in r for r in rep), rep
    # НЕсрабатывание: обычное значение по-прежнему потеря
    card2 = "| Система | Описание |\n|---|---|\n| АБС РКО Ф1 | — |\n"
    rep, ok = check_source_tables(card2, src)
    assert not ok and any("отсутствуют" in r for r in rep), rep


# FB-41 КК (2026-10-28): ячейка целиком URL Confluence — та же отсылка, что у FB-16; перенос URL
# запрещён сторожем отсылков, полнота его не требует. Страница 2184433380, карточка call-ext-005.
_URL = "https://confluence.gboteam.ru/x/Ngo5Ag"
_CARD41 = "| Параметр | Значение |\n|---|---|\n| Протокол | REST |\n| Документация | — |\n"


def _src41(value):
    return ("Текст.\n\n| Параметр | Значение |\n|---|---|\n| Протокол | REST |\n"
            f"| Документация | {value} |\n")


def test_fb41_markdown_link_with_url_text_is_not_a_loss():
    # (а) [url](url) — значение ячейки само URL
    rep, ok = check_source_tables(_CARD41, _src41(f"[{_URL}]({_URL})"))
    assert ok, rep
    assert any("ячейки-ссылки на Confluence ×1" in r for r in rep), rep


def test_fb41_bare_url_is_not_a_loss():
    # (б) голый URL без markdown
    rep, ok = check_source_tables(_CARD41, _src41(_URL))
    assert ok, rep
    assert any("ячейки-ссылки на Confluence ×1" in r for r in rep), rep


def test_fb41_titled_link_still_needs_its_title():
    # (в) НЕсрабатывание: у [Название](url) название — содержание, переносится (FB-38)
    src = _src41(f"[Описание представления]({_URL})")
    rep, ok = check_source_tables(_CARD41, src)
    assert not ok and any("отсутствуют" in r for r in rep), rep
    card = _CARD41.replace("| Документация | — |", "| Документация | Описание представления |")
    rep, ok = check_source_tables(card, src)
    assert ok, rep
    assert not any("ячейки-ссылки на Confluence" in r for r in rep), rep


def test_fb41_url_only_cell_outside_confluence_still_a_loss():
    # (г) НЕсрабатывание: ссылка-только-URL не на Confluence — поведение прежнее
    gl = "https://gitlab.example.ru/group/repo"
    rep, ok = check_source_tables(_CARD41, _src41(f"[{gl}]({gl})"))
    assert not ok and any("отсутствуют" in r for r in rep), rep


def test_homoglyph_verbatim_in_source_text_pardoned(tmp_path):
    # FB-16.2 / FB-20: слово с гомоглифом стоит в тексте источника (не в литерале)
    src = "---\ntitle: X\n---\n\nМетод getCardFeeСounters возвращает список.\n"  # кириллическая С
    card = tmp_path / "c.md"
    card.write_text("# К\n\nВызов getCardFeeСounters по расписанию.\n", encoding="utf-8")
    rep, ok = check_file(card, source_text=src)
    assert ok, "\n".join(rep)
    assert any("помилованы" in ln and "из источника" in ln for ln in rep)
    # НЕсрабатывание: гомоглифа в источнике нет — по-прежнему брак
    card.write_text("# К\n\nВызов getСardFeeCounters по расписанию.\n", encoding="utf-8")
    rep, ok = check_file(card, source_text=src)
    assert not ok and any("К-30" in ln for ln in rep)


def test_step_level_shift_is_not_defect_but_flattening_is():
    # FB-16.3: выгрузка несёт список с базовым отступом (li1/li2); карточка
    # с той же вложенностью от нулевого уровня — не дефект, i-строка
    src = ("---\ntitle: X\n---\n\n**Шаг 3.** Проверки:\n\n    * правило один\n        * подусловие\n\n"
           "**Шаг 4.** Конец.\n")
    card_shift = ("# Ф\n\n**Шаг 3.** Проверки:\n\n- правило один\n  - подусловие\n\n"
                  "**Шаг 4.** Конец.\n")
    rep, ok = check_step_body_structure(card_shift, src)
    assert ok, rep
    assert not any("✗" in r for r in rep), rep
    # сдвиг базового уровня при наличии нулевого уровня в теле шага
    src2 = ("---\ntitle: X\n---\n\n**Шаг 3.** Проверки:\n\n    * правило один\n        * подусловие\n\n"
            "Примечание.\n\n* итог\n\n**Шаг 4.** Конец.\n")
    card2 = ("# Ф\n\n**Шаг 3.** Проверки:\n\n- правило один\n  - подусловие\n\n"
             "Примечание.\n\n- итог\n\n**Шаг 4.** Конец.\n")
    rep, ok = check_step_body_structure(card2, src2)
    assert ok, rep
    # НЕсрабатывание послабления: уплощение вложенности — по-прежнему ✗
    card_flat = ("# Ф\n\n**Шаг 3.** Проверки:\n\n- правило один\n- подусловие\n\n"
                 "**Шаг 4.** Конец.\n")
    rep, ok = check_step_body_structure(card_flat, src)
    assert not ok and any("структура тел шагов расходится" in r for r in rep), rep


def test_step_structure_checked_against_main_card_before_group(tmp_path):
    # FB-16.3 (fun-sys-16 КК): вторая карточка группы (intc) несёт свои абзацы
    # под тем же номером шага — объединение группы ложно расходится с источником;
    # К-26 сверяет главную карточку, объединение — только если главная не прошла
    from app.scripts.CI.kitcheck.checks.card_run import run_check
    src = tmp_path / "src.md"
    src.write_text("---\ntitle: 'Ф'\nconfluence_page_id: '111222'\n---\n\n"
                   "**Шаг 5.** Вызов метода.\n\nРезультат сохраняется.\n\n**Шаг 6.** Конец.\n",
                   encoding="utf-8")
    main = tmp_path / "fun.md"
    main.write_text("---\nid: FUN-SYS-16\ntitle: 'Ф'\ntype: function\n---\n\n# Ф\n\n"
                    "**Шаг 5.** Вызов метода.\n\nРезультат сохраняется.\n\n**Шаг 6.** Конец.\n",
                    encoding="utf-8")
    intc = tmp_path / "intc.md"
    intc.write_text("---\nid: INTC-004\ntitle: 'К'\ntype: internal-contract\n---\n\n# К\n\n"
                    "**Шаг 5.** Параметры.\n\nа\n\nб\n\nв\n\nг\n\n**Шаг 6.** Ответ.\n\nд\n",
                    encoding="utf-8")
    rep, ok = run_check([main, intc], src)
    assert not any("структура тел шагов расходится" in r for r in rep), rep


def test_long_line_amnesty_by_extra_pages(tmp_path):
    # FB-19: дословный абзац дочерней страницы карточки не «сплющенный перечень»
    long_par = "Пользователь подтверждает согласие на обработку персональных данных " * 10
    main_src = "---\ntitle: X\n---\n\nНазначение.\n"
    child_src = f"---\ntitle: Y\n---\n\n{long_par}\n"
    card = tmp_path / "c.md"
    card.write_text(f"# К\n\n{long_par}\n", encoding="utf-8")
    rep, ok = check_file(card, source_text=main_src)
    assert not ok and any("видимой длиной" in ln for ln in rep)
    rep, ok = check_file(card, source_text=main_src, amnesty_text=child_src)
    assert ok, "\n".join(rep)
    assert not any("видимой длиной" in ln for ln in rep)


def test_index_sources_skips_raw(tmp_path):
    # FB-21: архив sources/raw/ при индексации пропускается — дублей нет
    def w(p: Path, pid: str):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\ntitle: 'Т'\nconfluence_page_id: '{pid}'\n---\n\nтекст\n", encoding="utf-8")
    root = tmp_path / "sources"
    w(root / "confluence/a.md", "111222")
    w(root / "raw/a.md", "111222")
    idx, dups = selfcheck.index_sources(root)
    assert set(idx) == {"111222"} and dups == {}
    assert idx["111222"] == root / "confluence/a.md"
