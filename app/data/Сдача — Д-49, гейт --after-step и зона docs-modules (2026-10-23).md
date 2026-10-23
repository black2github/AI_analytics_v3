# Сдача: Д-49 — гейт переноса `--after-step`, статус OQ в двух формах, зона `docs/modules/`

Дата: 2026-10-23. Исполнитель — сессия «Правки прибора, акцепт и рутина».
Постановка: `app/data/Постановка параллельной сессии — Д-49, гейт --after-step и зона docs-modules (2026-10-23).md`.
База: analyzer `3f5be18c`. Канон — ветка `meta/d49-tool`: см. раздел «Канон» (заводится после вливания С1).

## Итог

- **Части A, B, C1–C7 сделаны** в analyzer, не закоммичено (коммит — по слову владельца).
- **Тесты:** новые `tests/test_transfer_gate_after_step.py` (25) и `tests/test_d49_zone.py` (18).
  Полный набор `tests/` (без `test_rag_pipeline.py` — ошибка сбора, не прибор; прогнан до
  проверки корня сборки, после неё — наборы гейта, 68 прошли): новый прибор —
  1855 прошли, 59 упали, 4 ошибки; чистый `HEAD` (`git worktree`) — 1816 прошли, 59 упали,
  4 ошибки; **списки упавших совпадают полностью** — все падения предсуществующие (приложение:
  агент, загрузчик Confluence, пробелы фрагментов; в приборе — только
  `test_selfcheck.py::test_overdue_debt_propagates`).
- **Golden master** (снимок `C:\tmp\tool-golden`, 43 вывода, HEAD против нового): отличаются 2,
  оба ожидаемые — ниже. Стенд: ИТОГО `файлов 160 — ✓ 142, ✗ 0, ⚠ 18; вердикт: OK` до и после,
  отчёты побайтно равны.
- **Полигон — копия клона КК** `C:\tmp\kk-d49` (оригинал не тронут, ветка не переключалась):
  полный гейт 45 блокеров → 16, лёгкий режим — 9 блокеров (8 ссылок на служебные файлы и
  `archive/` в корне сборки), повтор с `--baseline` — «новых 0».
- **Отклонения от постановки** — раздел «Отличия и находки»: время лёгкого режима 35–41 с, а
  не ≤ 30 с (валидатор платформы ~26 с); ссылок при переезде зоны 41, а не 28 (15 обратных — из
  зоны в `docs/`); **дополнение по решению владельца пилота 23.10** — лёгкий режим сам проверяет
  корень сборки (✗ TRF-01), иначе `docs/archive/` уезжал бы в корень незамеченным.

## Таблица A / B / C1–C7

| Часть | Где, функция | Строка отчёта (дословно) | Тесты | Копия КК |
| --- | --- | --- | --- | --- |
| A, режим | `transfer_gate.run_gate(after_step=True)`, ключ `--after-step` | `i [ПРИБОР] selfcheck не гонялся (режим --after-step), вердикт прибора — в сдаче`; итог `ИТОГ: ФОРМА НЕ ПЕРЕНОСИМА: блокеров N (новых M), предупреждений W` / `ИТОГ: ФОРМА ПЕРЕНОСИМА (новых M), предупреждений W`; шапка `--report`: `Режим: после захода (--after-step) — …` | `test_after_step_skips_selfcheck_and_prints_form_verdict`, `test_full_mode_verdict_unchanged`, `test_report_header_mode_line` | `ФОРМА НЕ ПЕРЕНОСИМА: блокеров 9 (новых 1), предупреждений 3` (до проверки корня — 8) |
| A, понижения | `Gate.downgrade`, закрытый список `_AFTER_STEP_DOWNGRADE` | CORE-20 «открытые вопросы» ✗ → `i … (проверяется полным гейтом перед переносом)`; SDLC-05 ⚠ → i; SDLC-04 «раздела нет» ✗ → ⚠ | пары: `test_core20_…`, `test_sdlc05_…`, `test_sdlc04_…`; НЕ понижаются: `test_broken_relative_link_not_downgraded` (TRF-03, SDLC-08), `test_core20_debt_reading_rule_not_downgraded`, `test_downgrade_closed_list_keeps_validator_sdlc04` | CORE-20 «203» — i |
| A, корень сборки (решение владельца 23.10) | `check_staged_root` — только `--after-step`; в полном режиме корень проверяет selfcheck на сборке | `✗ [TRF-01] в корне целевой раскладки посторонние каталоги и файлы: archive/ — в корне репозитория документации только разделы комплекта (brd/, srs/, nfr/, tasks/, modules/) и markdown; перенести внутрь раздела или удалить`; иначе `✓ [TRF-01] в корне целевой раскладки только разделы комплекта и markdown` | `test_after_step_root_junk_dir_blocks`, НЕсрабатывание: `…_root_standard_dirs_pass` (brd, nfr, tasks, files, modules), `…_root_api_not_doubled` (api/ — свой TRF-03), `test_full_mode_root_left_to_selfcheck` | ✗ `archive/` — новый блокер (новых 1 к прошлому отчёту) |
| A, `--out` | `run_gate` | `✗ [TRF-01] --out не применим в режиме --after-step: лёгкий гейт проверяет форму после захода, перенос — только полным гейтом` | `test_after_step_out_rejected` | — |
| A, `--baseline` | `read_baseline`, `baseline_delta`, `_blocker_key` | под итогом `новых блокеров M: [крит] …` и `ушло K (относительно <файл>)`; без ключа — `(новых —)`; нет таблицы — `✗ --baseline: в <файл> нет таблицы гейта …` | `test_baseline_same_blockers_new_zero`, `…_new_and_gone`, `…_number_change_is_same_blocker`, `…_identifier_digits_distinguish_blockers`, `…_without_table` | `новых 0, ушло 0` (повтор лёгкого) |
| B | `review_guards.OQ_STATUS_RE` (один дом), `oq_status_class`; гейт импортирует оба | — (меняется число в CORE-20) | `test_oq_status_both_forms`, `test_oq_without_status_line_still_open`, `test_oq_regex_single_home` | открытых 304 → 207 (198 «открыт» + 9 «частично»), без долга — 203 |
| C1 | `kitcheck/md.in_module_zone`, `_kit_md(zone=…)`; перепись `selfcheck` | `i мини-комплектов зоны: 1 (docs/modules/widgets-rtl, файлов 14)` | `test_in_module_zone_and_kit_md`, `test_zone_files_outside_census_and_registry`, `test_kit_without_zone_has_no_zone_lines`, `test_zone_relative_links_checked`, `test_zone_branch_form_counted` | ИТОГО `374 — ✓ 344, ✗ 4, ⚠ 26` как на оригинале + i-строка |
| C1, разметка | `source_profile.check_subservice_mapping` | `✗ разметка: … не размечен «вне Экосистемы», а файл лежит в мини-комплекте зоны docs/modules/ — зона только для страниц вне Экосистемы` | `test_mapping_zone_page_in_docs_modules_ok`, `…_in_srs_still_flagged`, `…_ecosystem_page_in_zone_flagged` | 13 ✗ разметки, которые давал прибор HEAD на копии, ушли |
| C2 | `kitcheck/checks/zone.check_module_zone` | `⚠ мини-комплект вне docs/ — переносом не переезжает (Д-49), перенести в docs/modules/<имя>/: modules/widgets-rtl` | `test_old_place_next_to_docs_warns_once_and_root_stays_legit`, `test_docs_repo_layout_no_old_place_warning` | оригинал КК — одна строка ⚠; копия — нет |
| C3 | то же | `⚠ мини-комплект без паспорта границы (module-kit-readme.md): docs/modules/<имя>/ — нет README.md` | `test_zone_kit_without_readme_warns` | нет (README есть) |
| C4 | `source_coverage._under_modules` (уже смотрел `output/modules`) | сообщение пробела: `… дом — мини-комплект docs/modules/<имя>/` | `test_coverage_zone_page_covered_under_docs_modules`, `…_old_place_still_covers`, `…_zone_page_in_srs_is_gap` | покрытие то же (339 из 615) |
| C5 | `normalize_tables` — порог «ссылка вне docs/» | — (ссылка в `docs/modules/` — цель внутри комплекта) | `test_clean_link_into_docs_modules_ok`, `test_clean_link_to_sources_still_flagged` | — |
| C6 | `link_debts.check` — долг формы 1 на цель зоны | `⚠ долг <FROM> «<имя>» — цель в зоне «вне Экосистемы» покрыта мини-комплектом (docs/modules/…): долг формы 1 не заводится — снять строку, в карточке — ссылка на файл мини-комплекта (Д-49)`; не покрыта — `… цель — мини-комплект docs/modules/<имя>/ (Д-49)` | `test_debt_on_zone_target_covered_by_docs_modules`, `…_not_covered_points_to_docs_modules` | — |
| C7 | `transfer_gate.check_transfer_conditions` (SDLC-08) | каталоги `modules/**` в перечне «без README-реестра» не участвуют; типы зоны — в `i [TRF-04]` | `test_zone_spec_without_readme_not_flagged_sdlc08`, `test_card_dir_without_readme_outside_zone_still_flagged`, `test_docs_repo_modules_dir_is_standard` | `modules` в SDLC-08 нет |

## Полигон — числа

Копия клона КК (`ec5ef3b`), в копии — коммит `f3c4c4d` «полигон Д-49»: `modules/widgets-rtl/` →
`docs/modules/widgets-rtl/`, ссылки пересчитаны по фактической цели (скрипт
`move_zone.py` в каталоге сессии), пустой каталог `modules/` удалён.

| Прогон | Время | Итог |
| --- | --- | --- |
| полный гейт, прибор HEAD, зона на старом месте | 116 с | NOT READY — блокеров 45 (28 — `E_LOCAL_LINK_OUTSIDE_REPOSITORY` на `modules/`, CORE-20 «304») |
| полный гейт, новый прибор, зона в `docs/modules/`, `--baseline` к прошлому | 104 с | NOT READY — блокеров 16 (новых 5), ушло 34 |
| лёгкий `--after-step` (до проверки корня) | 35–37 с (свободная машина) | ФОРМА НЕ ПЕРЕНОСИМА — блокеров 8 |
| лёгкий, повтор с `--baseline` | 35 с | новых 0, ушло 0 |
| лёгкий с проверкой корня, `--baseline` к первому | 41 с | блокеров 9 (новых 1: `archive/`), ушло 0 |
| лёгкий без валидатора (`--no-validator`, для раскладки времени) | 8,7 с | — |
| selfcheck копии (новый прибор) | 70 с | `374 — ✓ 344, ✗ 4, ⚠ 26; БРАК` = оригинал |

Пять «новых» полного режима — не регресс: CORE-20 сменил перечень (203 вместо 304 — другой текст
строки) и четыре файла зоны ссылаются на служебный `open-questions.md` в корне — валидатор увидел их,
когда зона вошла в `docs/`.

**Оставшиеся ✗ лёгкого режима на КК — список долгов формы для координатора** (1–8 — ссылки из
комплекта на служебные файлы рабочего репозитория, в docs-репозиторий они не переезжают; 9 —
посторонний каталог в корне сборки):

1. `README.md:205` → `../open-questions.md`
2. `README.md:206` → `../inventory.md`
3. `README.md:207` → `../migration-plan.md`
4. `srs/README.md:30` → `../../open-questions.md`
5. `modules/widgets-rtl/README.md:114` → `../../../open-questions.md`
6. `modules/widgets-rtl/interface/mod-widgets-rtl-001-pin-input.md:24` → `../../../../open-questions.md`
7. `modules/widgets-rtl/interface/mod-widgets-rtl-002-pin-send.md:24` → то же
8. `modules/widgets-rtl/spec/scr-05-pin-change-refused.md:15` → то же
9. `archive/` в корне комплекта — в целевой раскладке каталог в корне репозитория документации
   (✗ TRF-01 «корень целевой раскладки»): перенести внутрь раздела или удалить

⚠ лёгкого режима: SDLC-04 «раздел пуст при 13 описаниях методов», SDLC-08 «30 каталогов без
README-реестра» (среди них `archive/…`), FMT-01 «пример .txt разбирается».

## Golden master — отличия

| Вывод | Было | Стало | Почему |
| --- | --- | --- | --- |
| `kk__transfer_gate` | `✗ [CORE-20] … без долга: 265 (OQ-01 (без строки «Статус»), …)`; `переведены: 3 (… без строки …)` | `… без долга: 177 (OQ-22, OQ-23, …)`; `переведены: 2 (OQ-41, OQ-44)` | часть B: обе формы статуса и класс по первому слову (снимок КК старше) |
| `lkmp__transfer_gate_json_report` | — | поля `"after_step": false`, `"new_blockers": null` | новые поля JSON |

Остальные 41 вывод (selfcheck в обоих профилях, link_debts, matrix_sync, source_coverage, гейт и
утилиты канона по шести комплектам) — без отличий.

## Отличия от постановки и находки

1. **Время лёгкого режима — 35–37 с, не ≤ 30 с.** Без валидатора платформы режим идёт 8,7 с;
   ~26 с — сам валидатор (копия платформы, не правится). В гейте добавлен кэш шапок файлов
   (четыре прохода по комплекту читали одни и те же файлы: ~1550 чтений → ~390, −4 с). Дальше
   ускорять можно только валидатор — вне контура.
2. **При переезде зоны пересчитываются 41 ссылка, не 28.** Из `docs/` в зону — 26 (23 вида
   `../../../../../modules/`, одна `../../../../modules/`, две в матрице `../modules/`); **из зоны —
   15**: 7 на карточки `docs/` (паспорт границы и контракты интерфейса, `../../docs/…`) и 8 на
   служебный `open-questions.md` в корне (глубина пересчитывается, чтобы ссылка в src не
   сломалась, но в docs-репозиторий файл не переезжает — это 4 из 9 долгов формы). Сверено
   повторно на свежей копии клона скриптом `app/data/kk-zone-move-links.py`: 41 = 26 + 7 + 8,
   результат совпадает с полигоном файл в файл. Механическая замена строки
   `../../../../../modules/` → `../../../../modules/` их не покрывает — в сообщение координатору
   КК (С3) нужно добавить и обратные ссылки — для команды подготовлен скрипт
   `app/data/kk-zone-move-links.py` (пересчёт по фактической цели, `git mv`, `--dry-run`).
3. **Корень сборки в лёгком режиме — сделано по решению владельца пилота 23.10.** В целевой
   раскладке `docs/archive/` становится каталогом в корне репозитория; полный гейт видит это
   через selfcheck на сборке (`✗ корень репозитория: посторонние файлы ×1 (archive)`), а лёгкий
   selfcheck не гоняет. Теперь лёгкий режим проверяет корень сам: каталог вне `brd/ srs/ nfr/
   tasks/ modules/` (и служебных `files/ img/ examples/ assets/ images/`) или не-markdown файл —
   ✗ TRF-01; `api/` не дублируется (свой TRF-03). В полном режиме строки нет — там корень
   сторожит selfcheck, иначе один дефект давал бы два блокера (тест). Это расширение закрытого
   списка отличий режимов из постановки — в норму С1 (протокол, «Гейт формы») стоит вписать.
4. **Классификация статуса OQ — по первому слову, не подстрокой.** Подстрока «открыт» находилась в
   «переоткрыть» внутри пояснения закрытых записей (КК: 7 записей «закрыт (…; переоткрыть при …)»).
   Гейт берёт класс тем же правилом, что сторож B9; «частично» — открыт (асимметрия). Расхождение
   «207 у гейта / 198 у B9» — ровно эти 9 «частично».
5. **Понижение CORE-20 — только проверка «открытые вопросы».** CORE-20 по форме раздела долгов (имя
   раздела, нераспознанные строки, правило чтения в README) — форма матрицы, остаётся ✗ в лёгком
   режиме (тест на НЕсрабатывание).
6. **Тексты Д-46 о доме зоны** переписаны на `docs/modules/<имя>/` (сообщение покрытия, разметки,
   долга); в `test_d46_zone.py` обновлены две проверки текста.
7. **Сторож разметки подсервисов** раньше давал ✗ на каждую страницу зоны в `docs/`; теперь
   страница «вне Экосистемы» в `docs/modules/` — норма, а страница Экосистемы в зоне — ✗ (тест).

## Файлы analyzer (не закоммичено)

- `app/scripts/CI/transfer_gate.py` — `--after-step`, `--baseline`, `Gate.downgrade`, кэш шапок,
  статус OQ, исключение `modules/` из SDLC-08, шапка и ключи;
- `app/scripts/CI/selfcheck.py` — перепись без зоны, `_kc_module_zone`, `zone_cards` в разметку;
- `app/scripts/CI/kitcheck/md.py` — `in_module_zone`, `_kit_md(zone=…)`;
- `app/scripts/CI/kitcheck/checks/zone.py` — новый (C1 i-строка, C2, C3);
- `app/scripts/CI/kitcheck/checks/review_guards.py` — `OQ_STATUS_RE`, `oq_status_class`;
- `app/scripts/CI/kitcheck/checks/source_profile.py`, `links.py`, `artifacts.py`;
- `app/scripts/CI/source_coverage.py`, `link_debts.py`, `normalize_tables.py`;
- `tests/test_transfer_gate_after_step.py`, `tests/test_d49_zone.py` — новые; `tests/test_d46_zone.py`.

## Канон

Ждёт «С1 влит» (`meta/d49-gate-after-step`): затем ветка `meta/d49-tool` от `master` в отдельном
рабочем дереве, копии прибора, раздел `transfer_gate.py` в `_meta/tools/README.md`, сверка
`tr -d '\r'`, SF ✓, команды владельцу.
