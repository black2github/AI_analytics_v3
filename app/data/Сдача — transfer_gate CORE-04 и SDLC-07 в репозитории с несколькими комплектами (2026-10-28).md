# Сдача: transfer_gate — CODEOWNERS и манифест в корне репозитория (CORE-04, SDLC-07)

Дата: 2026-10-28. Постановка — «Постановка для сессии «Правки прибора» — transfer_gate CORE-04 и SDLC-07 в
репозитории с несколькими комплектами, CODEOWNERS в корне git (2026-10-28)» (analyzer a17c7198). Исполнитель —
сессия «Правки прибора, акцепт и рутина».

## Итог

Исполнено по пунктам 1–4 постановки. Не закоммичено: коммит analyzer — по слову владельца, ветка канона —
по его командам.

## Что сделано (analyzer `app/scripts/CI/transfer_gate.py`)

- `repo_root_for(kit)`: корень домена (`kitcheck.checks._common.domain_context`), иначе вершина git
  (`git -C <kit> rev-parse --show-toplevel`; git не ответил — подъём по родителям до каталога с `.git`),
  ничего — сам комплект.
- `check_target_repo`, режим `in_place`: корень совпадает с комплектом — прежний код без изменений (тексты ✓/✗
  те же). Комплект в подкаталоге — `_check_codeowners`:
  - файл ищется в `CODEOWNERS`, `docs/CODEOWNERS`, `.gitlab/CODEOWNERS` корня, первый непустой;
  - разбор строк с секциями GitLab (`[Имя]`, `^[Имя]`, `[Имя][N]`, владельцы секции по умолчанию);
  - правило, покрывающее каталог комплекта (кроме `*`, `**`, `/*`, `/**`) — ✓ с правилом и владельцами;
    сравнение — gitignore в упрощённом виде (ведущий или внутренний `/` — от корня, `/` и `/**` в конце —
    каталог, имя без `/` — каталог на любом уровне, `fnmatch` по компонентам);
  - только правило по умолчанию — ⚠ с перечнем правил `*` всех секций (секции GitLab действуют все сразу:
    у цифрового рубля их четыре — Analytics/Backend/Frontend/QA, показывать одну было бы неверно);
  - файла нет — ✗ с перечнем трёх мест; подкаталожный файл упоминается как «не читает и не засчитывается»;
  - корневой есть и подкаталожный есть — i «можно удалить».
- SDLC-07: манифест корня — как раньше; манифест комплекта в подкаталоге — i «манифест комплекта
  `<путь>/gpb-manifest.json`: name=…, title=…» (без `name`/`title` — перечень полей).
- `--out` не тронут. Шапка модуля — уточнение «в его корне, как их читает GitLab».

**Толкование, на которое прошу взглянуть.** Постановка: «Манифеста нет ни в корне, ни в комплекте — ⚠ как
сейчас». Случай «в корне нет, в комплекте есть» не описан; оставлено ⚠ на отсутствие манифеста корня (стандарт
repo-topology §3 требует его у репозитория) плюс i-строка манифеста комплекта. Если нужно без ⚠ — одна правка.

## Тесты

`tests/test_transfer_gate.py`: +9 — (а) корневой CODEOWNERS с правилом на каталог, настоящий `git init` — ✓;
(б) только `*` — ⚠ с текстом про правило по умолчанию и секцией; (в) только `branches/CODEOWNERS` — ✗, мёртвый
файл не засчитан; (г) `.gitlab/CODEOWNERS` и шаблон `branches/**` — ✓; (д) корневой и подкаталожный — ✓ + i
«можно удалить»; (е) манифест комплекта — i-строка, манифест корня печатается; (ж) без git и домена — подъём
останавливается на `--src`, прежний ✗; корень домена без git — ✓; разбор шаблонов (`_co_covers`, 8 случаев).
Оба файла гейта (`test_transfer_gate.py`, `test_transfer_gate_after_step.py`): 77 passed.

Широкий прогон `pytest tests` (рабочее дерево): 61 failed, 2118 passed, 5 errors — давние падения RAG-части,
маршрутов, Confluence-загрузчика и т. п. (сеть закрыта); `tests/test_rag_pipeline.py` не собирается с марта —
отдельная постановка в `app/data` (2026-10-28). Сверка со списком на чистом HEAD (worktree): новое падение
одно — `test_transfer_gate_after_step.py::test_oq_regex_single_home`; остальные «только на правке» — модули,
которые в worktree не собрались (нет untracked-окружения основного дерева).

`test_oq_regex_single_home` — хрупкий тест, не дефект: он сравнивал регулярку гейта (модуль
`kitcheck.checks.review_guards`, импорт через `sys.path` прибора) с регуляркой из
`app.scripts.CI.kitcheck.checks.review_guards` — другого объекта модуля; `is` держался только на кеше
`re.compile`. Показано на HEAD без правки: после `re.purge()` — `False`. Новый импорт `_common` в гейте и
больший набор модулей в полном прогоне вытесняли кеш. Тест исправлен по смыслу «единственный дом»: сравнение
с тем же объектом модуля, что импортирует гейт; проверено с очисткой кеша перед тестом — passed.

## Golden и одиночные репозитории

- Golden (`C:/tmp/tool-golden`, прибор HEAD a17c7198 в отдельном worktree против рабочего дерева): **0 отличий
  из 43** (в эталоне — `transfer_gate` по базам и lk-mp).
- Живой прогон гейта «до/после» на одиночных репозиториях — **построчно без изменений**: `docs-account-opening-request`
  (полигон, NOT READY 62/4), `docs-bank-client` (23/4), `docs-branches` (13/3), `docs-file-storage`.

## Живые прогоны docs-common-dictionary (trunk 999325d)

`--src C:\doc-as-code\EAN\docs-common-dictionary\branches` — ИТОГ прежний (NOT READY — блокеров 3, предупреждений 1:
блокеры не про владельцев). Строки CORE-04/SDLC-07:

```text
| i к сведению | CORE-04 | владельцы документации | branches/CODEOWNERS GitLab не читает (владельцев назначает только файл в корне репозитория, docs/ или .gitlab/) — можно удалить |
| i к сведению | SDLC-07 | манифест | манифест комплекта branches/gpb-manifest.json: name=branches, title=Справочник филиалов и подразделений |
| ✓ пройдено | CORE-04 | владельцы документации | CODEOWNERS в репозитории документации (CODEOWNERS корня репозитория): комплект branches покрыт правилом «/branches/» — @atrushin @eshefer @admitrichev |
| ✓ пройдено | SDLC-07 | манифест | gpb-manifest.json разбирается; поля: automatedSystemCode, confluenceUrl, description, emailDevOps, emailItLeader, emailOperations, emailTechDevLeader, jiraDevComponent, jiraDevProject, name, projectCodeDevOps, teamInfo, title, type, valueStreamMaintainer — обязательный состав сверить вручную по требованиям платформы |
```

До правки: ✓ CORE-04 засчитывался по мёртвому `branches/CODEOWNERS`, манифест — комплекта, а не репозитория.

`--src …\currency` — NOT READY: блокеров 9 → 8, предупреждений 6 → 6:

```text
| ⚠ предупреждение | CORE-04 | владельцы документации | владельцы комплекта currency назначены только правилом по умолчанию «* @eshefer» [Default] — добавить строку для каталога комплекта «/currency/» в CODEOWNERS корня репозитория |
| ✓ пройдено | SDLC-07 | манифест | gpb-manifest.json разбирается; поля: automatedSystemCode, confluenceUrl, … — обязательный состав сверить вручную по требованиям платформы |
```

До правки: ✗ CORE-04 «CODEOWNERS в …\currency отсутствует», ⚠ SDLC-07 «gpb-manifest.json в …\currency нет».

Попутно — доменная ветка на `docs-digital-ruble\digital-ruble-payment` (README домена с таблицей сервисов):
✗ CORE-04 → ⚠ «только правилом по умолчанию» (четыре секции, у каждой `*`), ⚠ SDLC-07 → ✓ (манифест корня);
блокеров 592 → 591. Владельцам цифрового рубля — тот же совет: строка `/digital-ruble-payment/` и т. п. в
секции аналитики.

## Для владельцев docs-common-dictionary (их файл не правился)

| Подкаталог | Строка в корневом CODEOWNERS | Свой CODEOWNERS (мёртвый) | Свой манифест |
|---|---|---|---|
| currency | **нет** | нет | нет |
| fatf | **нет** | нет | нет |
| swift | **нет** | нет | нет |
| authorized-person, role-template | есть | нет | нет |
| bank-client, branch-services-classifier, branches, countries, country-call-codes, document-type, error-message, goz-activity-type, mobile-app, okfs, okopf, services, short-link, types-doc, types-doc-eco | есть | да | да |

Расхождение с постановкой: подкаталожных `CODEOWNERS` не десять, а **пятнадцать** (последняя строка таблицы).

## Канон

Ветка `meta/codeowners-repo-root` в worktree `C:\tmp\canon-co` от origin/master `9f98362` (копия гейта в каноне до
правки совпадала с analyzer HEAD): `_meta/tools/transfer_gate.py` (копия analyzer, CRLF), `_meta/tools/README.md` (абзац о
режиме репозитория документации — фраза про корень git, `docs/`, `.gitlab/`, домен и ⚠ правила по умолчанию),
`_meta/migration/reference.md` (около строки 284 — фраза постановки). Реестр структурных фактов ✓ по 7 фактам.
Сообщение коммита — `C:\tmp\canon-co-commit.txt` (для всех команд: проблема, затем что меняется). Коммит и push — владелец.
