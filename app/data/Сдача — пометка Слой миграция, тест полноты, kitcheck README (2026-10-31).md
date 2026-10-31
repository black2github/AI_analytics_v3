# Сдача: пометка `Слой: миграция`, тест полноты, kitcheck README (2026-10-31)

Постановка: `app/data/Постановка для сессии прибора — пометка Слой миграция, тест полноты, kitcheck README (2026-10-31).md`
(трек rules, п. 2, шаг 5). Решение по развилке — вариант (а) сессии трека skillCore/rules от 31.10:
`card_source.py` без пометки, комментарий у `SOURCE_CHECKS` по факту. Исполнитель — сессия «Правки прибора, акцепт
и рутина». Ветка прибора `feat/layer-marks` от `main` 27223143 (worktree `C:/tmp/analyzer-layers`); коммит analyzer —
по слову владельца.

## Что сделано

| Файл | Изменение |
| --- | --- |
| `source_inventory.py`, `source_coverage.py`, `raw_oracle.py`, `kitcheck/checks/source_profile.py` | второй строкой файла, под строкой с путём, — `# Слой: миграция` |
| `normalize_tables.py` | то же, с оговоркой в той же строке: «нормализатор сырых HTML-таблиц; `--check` — проверки карточки ядра (`kitcheck/checks/card_*`), работает без выгрузки» |
| `kitcheck/checks/card_run.py` | комментарий у `SOURCE_CHECKS`: «реестр запускается всегда; сверка с источником (`source_cell_completeness`, `source_comparison`) — только при `--sources` (`src_text` не None), миграционный слой»; пометки модуля нет (ядро) |
| `kitcheck/checks/card_source.py` | без изменений — смешанный модуль, ядро (в нём `check_outside_template_section` и член `FILE_CHECKS` `_fc_source_page_refs_and_columns`) |
| `kitcheck/README.md` | «Устройство»: слой модуля — по строке `Слой:` второй строкой файла, перечень и поведение без выгрузки — README прибора канона, раздел «Слои прибора»; «Как добавить проверку», п. 7: проверка с источником получает текст через `_SourceCtx.src_text` и сама молчит при `src_text is None`, слой — у функции, пометку несёт только модуль, целиком работающий с выгрузкой |
| `tests/test_layer_marks.py` (новый) | явный список пяти модулей с комментарием «дом — таблица «Слои прибора»…»; (а) каждый несёт пометку второй строкой; (б) ни один другой `app/scripts/CI/*.py`, `kitcheck/*.py`, `kitcheck/checks/*.py` строки `Слой: миграция` не содержит; (в) список указывает на существующие файлы — 7 тестов |

Факт для развилки (из кода, `main` 27223143): `SOURCE_CHECKS` запускается в `run_check` и без `--sources`; из девяти
проверок реестра источник нужен двум, семь читают только карточку.

## Приёмка

- Тест полноты падает, если снять пометку с `raw_oracle.py` (1 failed: `test_migration_module_marked_on_second_line[raw_oracle.py]`)
  и если поставить её на `selfcheck.py` (1 failed: `test_core_modules_not_marked`, `['selfcheck.py']`) — проверено руками,
  файлы восстановлены.
- Полный набор: 2268 passed, 58 failed + 4 errors — список падений построчно совпадает с базлайном (62 давних); плюс 7 —
  новые тесты.
- `selfcheck.py` без `--sources` и `--raw`, вывод до/после правок — байт в байт:

  | Комплект | Код | Итог |
  | --- | --- | --- |
  | `C:/doc-as-code/EAN/docs-account-opening-request` (`--docs .`, только чтение) | 2/2 | 129 файлов, ✓ 75, ✗ 47, ⚠ 7 |
  | эталон прибора stand | 2/2 | 160, ✓ 138, ✗ 4, ⚠ 18 |
  | эталон прибора lkmp | 0/0 | 113, ✓ 107, ✗ 0, ⚠ 6 |
  | эталон прибора kk | 2/2 | 342, ✓ 312, ✗ 8, ⚠ 22 |

  Эталона `output/open-add-account/docs` из постановки в репозитории нет — заменён полигоном по слову владельца.
- Сверка с таблицей «Слои прибора» (`C:/tmp/canon-layers/_meta/tools/README.md`, 05628bf): помеченные в приборе
  `normalize_tables.py`, `source_inventory.py`, `source_coverage.py`, `raw_oracle.py`, `kitcheck/checks/source_profile.py` —
  совпадают со строками «миграция» таблицы; `scan_*` — только в каноне; `selfcheck.py`, `SOURCE_CHECKS`, `card_source.py` —
  ядро со смешанной ветвью, без пометки.

## Что учесть

- `raw_oracle.py` в каноне НЕТ: он едет в бандле (`build_bundle.py`, рядом с `critic.py`), `selfcheck --raw` ищет его
  там. Пометка дойдёт до команд со следующей сборкой бандла; отдельную сборку ради комментария не делаю. Строке
  `raw_oracle.py` таблицы канона, возможно, нужна оговорка «лежит в бандле экспортёра».
- Копия в канон — после коммита analyzer: ветка `meta/layer-marks` от `origin/master` в отдельном worktree; файлы
  `normalize_tables.py`, `source_inventory.py`, `source_coverage.py`, `kitcheck/checks/source_profile.py`,
  `kitcheck/checks/card_run.py`, `kitcheck/README.md` плюс пометка в трёх `scan_*` прямо в каноне. Сверка общих файлов:
  шесть копируемых совпадают с `origin/master` канона (138bdfa) по блобам до правки.
