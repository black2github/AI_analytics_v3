# -*- coding: utf-8 -*-
"""extint_registry --check: содержимое потребителя в базовом контракте и ID карточек в ручной
части README папки АС (шаблон contract-call.md, раздел A, решение владельца 2026-11-08)."""
from pathlib import Path

from app.scripts.CI import extint_registry as er

HEAD = "https://gitlab.gboteam.ru/EAN/docs-svc/-/blob/HEAD/srs/contract-call/external/call-ext-001-x.md"
POINTER = "Потребители — в разделе «Потребители» и в docs сервисов"


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(s1_rows: str = "", s1_tail: str = "", s2_rules: str = "GUID", s4_head: str = "Коды результата и отказов",
         s4_body: str = "| Код | Описание |\n|---|---|\n| 0 | Успех |\n| 9 | Отказ |\n") -> str:
    return ("---\nid: EXTINT-ABC-001\ntitle: 'Операция'\ntype: external-integration\nkind: operation\n"
            "channel: rest\nsync: sync\n---\n\n# EXTINT-ABC-001. Операция\n\n## 1. Краткое описание\n\n"
            "| Поле | Значение |\n|---|---|\n| Внешняя система | АБЦ |\n" + s1_rows + "\n" + s1_tail
            + "\n## 2. Входные параметры\n\n| Код параметра | Наименование параметра | Тип | Обяз. | Кратность "
            "| Правила заполнения |\n|---|---|---|---|---|---|\n"
            f"| `RequestID` | Ид запроса | Строка | Да | [1] | {s2_rules} |\n\n"
            "## 3. Исходящие параметры и коды результата\n\nНет.\n\n"
            f"## 4. {s4_head}\n\n{s4_body}\n## 5. Примеры обмена\n\nНет.\n\n"
            "## Потребители\n\n| Сервис (`code` каталога) | Локальный ID | Карточка вызова |\n|---|---|---|\n"
            f"| svc | CALL-EXT-001 | [CALL-EXT-001. Вызов]({HEAD}) |\n")


def repo_with(tmp_path: Path, text: str, readme_about: str = "| Система | АБЦ |") -> Path:
    repo = tmp_path / "repo"
    w(repo / "abc/extint-abc-001-op.md", text)
    w(repo / "abc/files/spec.txt", "документ владельца")
    w(repo / "abc/README.md",
      "---\nid: EXTINT-ABC-000\ntitle: 'АБЦ — базовые контракты внешней АС'\ntype: external-integration-registry\n"
      "---\n\n# EXTINT-ABC-000. АБЦ\n\nНазначение.\n\n## О системе\n\n| Поле | Значение |\n|---|---|\n"
      f"{readme_about}\n\n## Операции\n\n| ID | Название | Канал | Синхронность | Карточка |\n|---|---|---|---|---|\n"
      "| EXTINT-ABC-001 | Операция | REST | sync | [extint-abc-001-op.md](extint-abc-001-op.md) |\n")
    w(repo / "README.md", "# Внешние интеграции\n\n## Реестр систем\n\n| Система | Папка | README | Карточек |\n"
                          "|---|---|---|---|\n| АБЦ | [`abc/`](abc/) | [README](abc/README.md) | 1 |\n")
    return repo


def out(repo: Path) -> str:
    lines, _bad = er.check(repo, limit=0)
    return "\n".join(lines)


# ---------------------------------------------------------------- несрабатывание

def test_clean_base_contract_silent(tmp_path):
    """Указатель, «Документация» → files/, перечень кодов в §4, константа владельца — без сигналов."""
    t = card(s1_rows=f"| Где используется | {POINTER} |\n| Документация | [spec.txt](files/spec.txt) |\n",
             s2_rules="= application/json")
    lines, bad = er.check(repo_with(tmp_path, t), limit=0)
    assert not bad, lines
    text = "\n".join(lines)
    assert "§1" not in text and "§4" not in text, text
    assert "i содержимое потребителя в base" in text and "«Где используется» 1, «Документация» 1" in text, text


def test_pointer_with_bold_label_and_quotes_variant_silent(tmp_path):
    t = card(s1_rows='| **Где используется:** | Потребители — в разделе "Потребители" и в docs сервисов. |\n')
    assert "§1 «Где используется»" not in out(repo_with(tmp_path, t))


def test_short_pointer_accepted(tmp_path):
    """Короткая прежняя форма указателя — тоже указатель (решение 2026-11-08)."""
    t = card(s1_rows="| Где используется | Потребители — в разделе «Потребители». |\n")
    assert "§1 «Где используется»" not in out(repo_with(tmp_path, t))


def test_pointer_with_extra_text_flagged(tmp_path):
    """НЕсрабатывание послабления: указатель с добавкой — уже не указатель."""
    t = card(s1_rows=f"| Где используется | {POINTER}; ссылки из [EXTINT-ABC-002](x.md) |\n")
    assert "§1 «Где используется» — не указатель шаблона" in out(repo_with(tmp_path, t))


def test_documentation_external_url_accepted(tmp_path):
    """Внешняя документация владельца вне Confluence — законна (шаблон, раздел A)."""
    t = card(s1_rows="| Документация | [Описание](https://dss.cryptopro.ru/docs/articles/x.html) |\n")
    assert "§1 «Документация»" not in out(repo_with(tmp_path, t))


def test_documentation_confluence_url_flagged(tmp_path):
    t = card(s1_rows="| Документация | [Страница](https://confluence.int.example.ru/pages/viewpage.action?pageId=1) |\n")
    assert "§1 «Документация» без ссылки на файл" in out(repo_with(tmp_path, t))


def test_steps_word_without_notation_silent(tmp_path):
    """§4 без нотации **Шаг N.** — перечни кодов, слово «шаг» в тексте владельца — не сигнал."""
    t = card(s4_body="Повтор через 5 секунд, шаг повтора — 3 попытки.\n")
    assert "§4 шаги" not in out(repo_with(tmp_path, t))


def test_readme_about_without_ids_silent(tmp_path):
    t = card(s1_rows=f"| Где используется | {POINTER} |\n")
    assert "ID карточек в ручной части README" not in out(repo_with(tmp_path, t, "| Каналы | REST по HTTPS |"))


# ---------------------------------------------------------------- срабатывание

def test_used_with_consumer_content(tmp_path):
    t = card(s1_rows="| Где используется | [PROC-004 Процесс передачи](../x.md) |\n")
    text = out(repo_with(tmp_path, t))
    assert "§1 «Где используется» — не указатель шаблона" in text, text
    assert "abc/extint-abc-001-op.md:17: [PROC-004 Процесс передачи]" in text, text   # номер строки файла


def test_documentation_without_file(tmp_path):
    t = card(s1_rows="| Документация | SVFE. cardInfo-v50.docx |\n")
    assert "§1 «Документация» без ссылки на файл в files/" in out(repo_with(tmp_path, t))


def test_documentation_link_to_missing_file(tmp_path):
    t = card(s1_rows="| Документация | [spec](files/нет такого.txt) |\n")
    assert "(файла по ссылке в files/ нет)" in out(repo_with(tmp_path, t))


def test_documentation_link_outside_files(tmp_path):
    t = card(s1_rows="| Документация | [Документация](README.md#документация) |\n")
    assert "§1 «Документация» без ссылки на файл в files/" in out(repo_with(tmp_path, t))


def test_passport_label_subheading(tmp_path):
    t = card(s1_tail="### Где используется\n\n- функция потребителя\n")
    assert "§1 подраздел с лейблом паспорта" in out(repo_with(tmp_path, t))


def test_consumer_steps_in_s4(tmp_path):
    t = card(s4_body="**Шаг 1.** Формируется запрос.\n\n**Шаг 2.** Ответ проходит ФЛК.\n")
    text = out(repo_with(tmp_path, t))
    assert "§4 шаги потребителя (нотация **Шаг N.**) — в функцию или процесс потребителя" in text, text
    assert "op.md:31: **Шаг 1.**" in text and "op.md:33: **Шаг 2.**" in text, text


def test_old_s4_title_warned(tmp_path):
    t = card(s4_head="Обработка ошибок и повторные вызовы")
    text = out(repo_with(tmp_path, t))
    assert "⚠ §4 прежний заголовок «Обработка ошибок и повторные вызовы» — «Коды результата и отказов» при " \
           "переделке карточки" in text, text


def test_new_s4_title_silent(tmp_path):
    """НЕсрабатывание: норма заголовка §4 — «Коды результата и отказов» (решение владельца 2026-11-08)."""
    assert "§4 прежний заголовок" not in out(repo_with(tmp_path, card(s4_head="Коды результата и отказов")))


def test_assignment_rules_info_only(tmp_path):
    """«=» в «Правилах заполнения» — только i-строка: константу владельца от присвоения по форме не отличить."""
    t = card(s1_rows=f"| Где используется | {POINTER} |\n", s2_rules="= **ECO1**<br>Константа АС")
    lines, bad = er.check(repo_with(tmp_path, t), limit=0)
    text = "\n".join(lines)
    assert "i правил-присвоений в base: 1" in text and "`RequestID` — = **ECO1**" in text, text
    assert not bad, lines


def test_readme_about_card_ids_warned(tmp_path):
    t = card(s1_rows=f"| Где используется | {POINTER} |\n")
    text = out(repo_with(tmp_path, t, "| Каналы | СИП (EXTINT-ABC-001, EXTINT-ABC-002) |"))
    assert "⚠ ID карточек в ручной части README («О системе»)" in text, text
    assert "abc/README.md:15: EXTINT-ABC-001, EXTINT-ABC-002" in text, text


def test_registry_tables_ids_not_counted(tmp_path):
    """Выводимая таблица «Операции» несёт ID по построению — не сигнал."""
    t = card(s1_rows=f"| Где используется | {POINTER} |\n")
    assert "ID карточек в ручной части README" not in out(repo_with(tmp_path, t))


def test_signals_do_not_break_on_non_base_type(tmp_path):
    """Карточка не external-integration (переходный тип) сторожем содержимого не проверяется."""
    t = card(s1_rows="| Где используется | функция потребителя |\n").replace(
        "type: external-integration", "type: contract-call")
    assert "§1 «Где используется»" not in out(repo_with(tmp_path, t))


# ---------------------------------------------------------------- папка АС по форме

def test_sandbox_dir_not_as(tmp_path):
    """Рабочий sandbox/ исполнителя (без карточек и README реестра) — не папка АС: i-строка, не ⚠."""
    t = card(s1_rows=f"| Где используется | {POINTER} |\n")
    repo = repo_with(tmp_path, t)
    w(repo / "sandbox/legacy-boundary-inventory.md", "# Опись\n")
    lines, bad = er.check(repo, limit=0)
    text = "\n".join(lines)
    assert "i каталогов пропущено: 1 (sandbox)" in text, text
    assert "ИТОГО: АС 1," in text and "sandbox/" not in text.replace("(sandbox)", ""), text
    assert not bad, lines


def test_as_dir_with_registry_readme_only_still_as(tmp_path):
    """НЕсрабатывание: папка АС с одним README реестра без карточек — по-прежнему АС."""
    t = card(s1_rows=f"| Где используется | {POINTER} |\n")
    repo = repo_with(tmp_path, t)
    w(repo / "xyz/README.md", "---\nid: EXTINT-XYZ-000\ntitle: 'XYZ'\ntype: external-integration-registry\n---\n\n"
                              "# EXTINT-XYZ-000. XYZ\n")
    lines, _bad = er.check(repo, limit=0)
    text = "\n".join(lines)
    assert "ИТОГО: АС 2," in text and "каталогов пропущено" not in text, text
    assert "папки нет в реестре: xyz/" in text, text   # АС учтена сверкой корневого реестра


def test_write_skips_sandbox(tmp_path):
    t = card(s1_rows=f"| Где используется | {POINTER} |\n")
    repo = repo_with(tmp_path, t)
    w(repo / "sandbox/notes.md", "# x\n")
    report, code = er.write(repo)
    assert code == 0, report
    assert any(r.startswith("i каталогов пропущено: 1 (sandbox)") for r in report), report
    assert "sandbox" not in (repo / "README.md").read_text(encoding="utf-8")
