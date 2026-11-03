# Постановка прибору — transfer_gate не передаёт опись inventory.md в selfcheck на staged-копии (гейт 5.4 КК r07 NOT READY) (2026-11-02)

Кому: сессия «Правки прибора, акцепт и рутина». От: «Точки расширения эталона». Срочность: блокирует гейт 5.4 КК (приёмка 03.11 15:00): r07 — NOT READY, 8 блокеров «ПРИБОР», все ложные.

## Сигнал (координатор КК, 02.11 ночь-3)

- Прямой selfcheck дерева exec/5.4-close @ 67ee675b (master f9c18404 + fixlist; канон 90d4714): 400 файлов, ✓ 374, ✗ 0, ⚠ 26 — вердикт OK.
- transfer_gate на том же дереве (coord `sandbox/transfer-gate-PROM-5.4-r07.md`, базлайн r06): selfcheck внутри гейта ✗ 15, блокеров 8 — 038 + FUN-CL-21 (бывшая С-4); 011/036/SCR-CL-20 и 037/SCR-CL-17 (С-6); 030 + SCR-CL-19 (С-7); 024, 025, 027 + 040 (С-11); строка ИТОГО. Это ровно те ложные ✗, которые снимают доводы (25)(б), копия страницы метода и задача 5 — все они читают опись.
- Воспроизведение координатора: копия `docs/` в каталог без `inventory.md` → ✗ 15 тот же набор; тот же `docs/` на месте → ✗ 0.

## Диагноз (по коду analyzer main ffda7216)

1. `app/scripts/CI/kitcheck/checks/card_run.py` читает опись тремя местами как `docs_root.parent / "inventory.md"`: `_copy_method_page_contour` (строка 480), `_page_outside_subservice` (499, 507). `docs_root` — это `docs`, переданный в `selfcheck.run` (`_run(files, src, docs, …)`, selfcheck.py 483/535/561).
2. `app/scripts/CI/transfer_gate.py`: `stage_kit(docs, staged)` копирует содержимое `docs/` в корень временного каталога (`tempfile.mkdtemp`), `run_selfcheck` вызывает `sc.run(staged, sources, strict=strict)` (780–783). `inventory.md` лежит в корне репозитория рядом с `docs/` и в staged не попадает; `staged.parent` — системный temp. Опись не найдена → `_inventory_req_types` отдаёт пусто → доводы не срабатывают.
3. Та же ошибка адреса в режиме репозитория документации (`detect_layout` → `docs = src_root`, docs_repo): опись в корне = `docs_root`, а прибор смотрит в `docs_root.parent` — родитель репозитория. Прямой прогон «на месте» в КК (`<root>/docs`) — единственная раскладка, где адрес верен; поэтому selfcheck ✗ 0, а гейт — ✗ 15.
4. `source_coverage.py` уже умеет верно: `find_kit_file(output, name)` ищет в `output`, затем `output.parent`, плюс ключ `--inventory`. Домов два — это и есть дефект.

## Целевое поведение

- Один локатор файла комплекта для kitcheck: опись ищется в `docs_root`, затем `docs_root.parent` (как `find_kit_file`), с явным переопределением: `selfcheck.run(…, inventory: Optional[Path] = None)` → `run_check(…, inventory=…)` → в card_run одна функция `_inventory_path(docs_root, inventory)` вместо трёх `docs_root.parent / "inventory.md"`. CLI selfcheck — ключ `--inventory` (как у source_coverage). Где локатор живёт (kitcheck/fs или общий модуль) — ваше решение; домов у адреса описи должно остаться один.
- `transfer_gate.run_selfcheck` передаёт в selfcheck опись источника: `find_kit_file(docs, "inventory.md")` от `--src` (для `<root>/docs` — `<root>/inventory.md`; для docs-repo — `<root>/inventory.md` = docs). Опись в staged-копию не копировать: она не часть переносимого комплекта (стенд — целевой репозиторий без sources/). Если гейт где-то ещё запускает kitcheck-проверки на staged (например, `--after-step`) — тот же параметр.
- Без описи нигде — поведение прежнее (доводы не срабатывают, ✗ остаётся): асимметрия ошибок, лишний ✗ лучше молчаливого снятия.

## Тесты

1. Гейт: комплект `<root>/docs` + `<root>/inventory.md` (строка integration с титулом «Копия [КК] …» и строка «вне SRS: базовый контракт …»), карточка вызова с доп. страницей-копией и чужими маркерами → гейт даёт те же ✗/✓ по selfcheck, что прямой `selfcheck.run(<root>/docs, …)` (сейчас расходятся).
2. Режим репозитория документации (матрица в корне, `inventory.md` в корне) — опись найдена.
3. НЕсрабатывание: комплект без `inventory.md` → ✗ как раньше; явный `--inventory` на несуществующий путь — ✗ с внятной строкой, не краш.
4. Эталон C:/tmp/tool-golden — 0 отличий (там прогон прямой); регресс — без новых падений.

## Репро и ожидание

Снимок master КК f9c18404 через `git archive` (дерево -exec не трогать) + канон 90d4714: до правки transfer_gate selfcheck ✗ 15 / прямой ✗ 0; после — оба ✗ 0, блокеров 0 (остаётся ⚠ SDLC-08 — 32 каталога без README-реестра, как в r06). После сдачи координатор перегоняет r08 — ожидание READY.

## Сдача

Мне: хеш analyzer (коммит по правилам сессии), ветка канона `meta/transfer-gate-inventory` от master 90d4714 (коммит/push/MR — владелец, сообщение файлом C:/tmp/msg-*.txt), числа ✗ гейт/прямой до и после на снимке f9c18404, список новых тестов. Версию бандла поднять вместе с этим (хвост raw_oracle dfca0725) — если владелец даст слово в вашем чате.
