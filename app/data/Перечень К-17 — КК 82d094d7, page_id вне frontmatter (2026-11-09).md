# Перечень К-17 на КК 82d094d7: идентификатор страницы Confluence вне frontmatter

Дата: 2026-11-09. Исполнитель: сессия «Правки прибора». Для постановки координатору КК — сам прибор ничего не чинит. Не коммитить (данные команды).

Прогон: `selfcheck.py --docs C:\tmp\kk-d\docs --sources C:\tmp\kk-d\sources` прибором из worktree `C:\tmp\canon-k17` (ветка канона meta/k17-page-id-all-docs, ещё не закоммичена). В скобках — откуда номер известен, то есть где он уже записан в своём доме. Без `--sources` — 79 строк в 46 файлах: 13 строк с номерами, известными только по шапкам страниц выгрузки, уходят в i-строку.

Отдельно — `srs/bc-issue/function/client/fun-cl-55-registry-import-mapping.md:83`: страница 2184430096 вне выгрузки (номера нет ни в шапках, ни в матрице, ни в выгрузке) — стоит в i-строке, не в ✗. Это настоящая отсылка к странице вне выгрузки; что с ней делать (долг или снятие), решит заход чистки.

## ✗ К-17 — построчно

Строк 92, файлов 51. Из них три README-реестра ЭФ (`srs/{bc-issue,bc-pin,bc-status}/screen-form/README.md`) — 29 строк (12 + 7 + 10); остальные 63 строки — в 48 файлах. Происхождение номера: frontmatter — 71, выгрузка — 14, матрица — 7.

### modules/widgets-rtl/README.md

- `modules/widgets-rtl/README.md:25` — `2166860957` (страница комплекта: матрица): **«[КК_Виджет_РЕКВ] Просмотр реквизитов карты» (2166860957)**
- `modules/widgets-rtl/README.md:36` — `2190357003` (страница комплекта: выгрузка): **«[КК_Виджет_РЕКВ] Скрипты/методы Клиента» (2190357003)**
- `modules/widgets-rtl/README.md:40` — `2211206691` (страница комплекта: выгрузка): **«[КК_Виджет_ПИН] Смена пин-кода» (2211206691)**
- `modules/widgets-rtl/README.md:129` — `2190357005 и ещё 1` (страница комплекта: frontmatter MOD-WIDGETS-RTL-004): - **OQ-299** — закрыт (владелец канона, 30.10): представление процессов скриптов — переходами ЭФ в `spec/scr-*`, эндпоинтами и разделом «Что делает» контрактов интерфейса (вариант 1, состав WID-01 фиксирован). «Дефект выгрузки cvv» дефектом не является: Шаг 0 и ветка невалидного токена в raw страниц …

### modules/widgets-rtl/spec/fun-01-pin-encrypt.md

- `modules/widgets-rtl/spec/fun-01-pin-encrypt.md:89` — `2209349612` (страница комплекта: frontmatter MOD-WIDGETS-RTL-FUN-01): \| Выгрузка Confluence сервиса \| `sources/confluence/[КК]-Корпоративные-Карты/[КК]-Виджеты/[КК]-Паспорт-границы-контуров-Экосистема---Розница-(операции-с-чувствительными-данными-карт)/[КК_Виджет_ПИН]-Смена-пин-кода/[КК_Виджет_ПИН]-Скриптыметоды-Клиента/[КК_Виджет_ПИН]-Клиент-Скрипт-ввода-ПИН-кода/[ …

### modules/widgets-rtl/spec/fun-02-token-exchange.md

- `modules/widgets-rtl/spec/fun-02-token-exchange.md:97` — `2393815022` (страница комплекта: frontmatter MOD-WIDGETS-RTL-FUN-02): \| Выгрузка Confluence сервиса \| `sources/confluence/[КК]-Корпоративные-Карты/[КК]-Виджеты/[КК]-Паспорт-границы-контуров-Экосистема---Розница-(операции-с-чувствительными-данными-карт)/[КК_Виджет]-Клиент-Метод-обмена-токенов.md` \| 2393815022 \| prod-2026-09, дата выгрузки 2026-09-08 \|
- `modules/widgets-rtl/spec/fun-02-token-exchange.md:99` — `2320353829` (страница комплекта: frontmatter MOD-WIDGETS-RTL-000): \| ЕПАА, «Интроспекция токена uaa в omni платформе» \| `sources/external/uaa-omni/all/` \| 2320353829 \| 2026-10-21 \|

### modules/widgets-rtl/spec/scr-01-pin-ef-index.md

- `modules/widgets-rtl/spec/scr-01-pin-ef-index.md:30` — `2251367197` (страница комплекта: frontmatter MOD-WIDGETS-RTL-SCR-01): \| Выгрузка Confluence сервиса \| `sources/confluence/[КК]-Корпоративные-Карты/[КК]-Виджеты/[КК]-Паспорт-границы-контуров-Экосистема---Розница-(операции-с-чувствительными-данными-карт)/[КК_Виджет_ПИН]-Смена-пин-кода/[КК_Виджет_ПИН]-ЭФ-Клиента.md` \| 2251367197 \| prod-2026-09, дата выгрузки 2026-09- …

### modules/widgets-rtl/spec/scr-02-pin-first-input.md

- `modules/widgets-rtl/spec/scr-02-pin-first-input.md:113` — `2275442932` (страница комплекта: frontmatter MOD-WIDGETS-RTL-SCR-02): \| Выгрузка Confluence сервиса \| `sources/confluence/[КК]-Корпоративные-Карты/[КК]-Виджеты/[КК]-Паспорт-границы-контуров-Экосистема---Розница-(операции-с-чувствительными-данными-карт)/[КК_Виджет_ПИН]-Смена-пин-кода/[КК_Виджет_ПИН]-ЭФ-Клиента/[КК_Виджет_ПИН]-ЭФ-Клиента-Первый-ввод-ПИН-кода.md` \| 22 …

### modules/widgets-rtl/spec/scr-03-pin-repeat-input.md

- `modules/widgets-rtl/spec/scr-03-pin-repeat-input.md:78` — `2275443033` (страница комплекта: frontmatter MOD-WIDGETS-RTL-SCR-03): \| Выгрузка Confluence сервиса \| `sources/confluence/[КК]-Корпоративные-Карты/[КК]-Виджеты/[КК]-Паспорт-границы-контуров-Экосистема---Розница-(операции-с-чувствительными-данными-карт)/[КК_Виджет_ПИН]-Смена-пин-кода/[КК_Виджет_ПИН]-ЭФ-Клиента/[КК_Виджет_ПИН]-ЭФ-Клиента-Повторный-ввод-ПИН-кода.md` \| …

### modules/widgets-rtl/spec/scr-04-pin-set-changed.md

- `modules/widgets-rtl/spec/scr-04-pin-set-changed.md:62` — `2295870599` (страница комплекта: frontmatter MOD-WIDGETS-RTL-SCR-04): \| Выгрузка Confluence сервиса \| `sources/confluence/[КК]-Корпоративные-Карты/[КК]-Виджеты/[КК]-Паспорт-границы-контуров-Экосистема---Розница-(операции-с-чувствительными-данными-карт)/[КК_Виджет_ПИН]-Смена-пин-кода/[КК_Виджет_ПИН]-ЭФ-Клиента/[КК_Виджет_ПИН]-ЭФ-Клиента-ПИН-код-установленизменен.md`  …

### modules/widgets-rtl/spec/scr-05-pin-change-refused.md

- `modules/widgets-rtl/spec/scr-05-pin-change-refused.md:64` — `2295154419` (страница комплекта: frontmatter MOD-WIDGETS-RTL-SCR-05): \| Выгрузка Confluence сервиса \| `sources/confluence/[КК]-Корпоративные-Карты/[КК]-Виджеты/[КК]-Паспорт-границы-контуров-Экосистема---Розница-(операции-с-чувствительными-данными-карт)/[КК_Виджет_ПИН]-Смена-пин-кода/[КК_Виджет_ПИН]-ЭФ-Клиента/[КК_Виджет_ПИН]-ЭФ-Клиента-Отказ-в-смене-ПИН-кода.md` \|  …

### modules/widgets-rtl/spec/scr-06-auth-error.md

- `modules/widgets-rtl/spec/scr-06-auth-error.md:74` — `2252439412` (страница комплекта: frontmatter MOD-WIDGETS-RTL-SCR-06): \| Выгрузка Confluence сервиса \| `sources/confluence/[КК]-Корпоративные-Карты/[КК]-Виджеты/[КК]-Паспорт-границы-контуров-Экосистема---Розница-(операции-с-чувствительными-данными-карт)/[КК_Виджет_ПИН]-Смена-пин-кода/[КК_Виджет_ПИН]-ЭФ-Клиента/[КК_Виджет_ПИН]-ЭФ-Клиента-Ошибка-авторизации.md` \| 2252 …

### modules/widgets-rtl/spec/scr-07-tech-error.md

- `modules/widgets-rtl/spec/scr-07-tech-error.md:61` — `2275443052` (страница комплекта: frontmatter MOD-WIDGETS-RTL-SCR-07): \| Выгрузка Confluence сервиса \| `sources/confluence/[КК]-Корпоративные-Карты/[КК]-Виджеты/[КК]-Паспорт-границы-контуров-Экосистема---Розница-(операции-с-чувствительными-данными-карт)/[КК_Виджет_ПИН]-Смена-пин-кода/[КК_Виджет_ПИН]-ЭФ-Клиента/[КК_Виджет_ПИН]-ЭФ-Клиента-Техническая-ошибка.md` \| 2275 …

### service-vision.md

- `service-vision.md:26` — `2166859634` (страница комплекта: выгрузка): Со страницы «[КК] Корпоративные Карты» (2166859634), дословно: «Сервис позволяет выпускать корпоративные карты и изменять их лимиты, а также блокировать карты. Дополнительно - получать различные отчеты в разрезе счетов и самих карт.»

### srs/bc-component/contract-call/external/README.md

- `srs/bc-component/contract-call/external/README.md:48` — `2166861013 и ещё 2` (страница комплекта: frontmatter CALL-EXT-032): **РКО Ф1 DBLink (frozen, PROM-5.7)** — 3 call-карточки CALL-EXT-032/033/034 (2166861013 — CALL-EXT-032, 2184433983 — CALL-EXT-033, 2184433984 — CALL-EXT-034); страницы введены заходом PROM-5.7, статус frozen (GBO-92191), вне ПРОМ-среза — подтверждено владельцем канона 31.10.
- `srs/bc-component/contract-call/external/README.md:52` — `2184433971` (страница комплекта: выгрузка): Страница «ЭКО_Корпоративные карты» (2184433971):

### srs/bc-component/contract-call/internal/README.md

- `srs/bc-component/contract-call/internal/README.md:35` — `2189331256` (страница комплекта: матрица): \| create-artifact (Недостающая цель ссылки) \| сервис signature «[ЭП] Сервис по работе с электронной подписью» (платформенный, `_meta/services.json`) \| базовые контракты «[ЭП] Универсальная функция серверной проверки ЭП» (страница владельца 2189331256) «[ЭП] Логика работы универсальной функции эле …
- `srs/bc-component/contract-call/internal/README.md:36` — `2189331001` (страница комплекта: матрица): \| create-artifact (Недостающая цель ссылки) \| сервис signature «[ЭП] Сервис по работе с электронной подписью» (платформенный, `_meta/services.json`) \| базовый контракт «[ЭП] Универсальная функция проверки электронной подписи» (страница владельца 2189331001) — комплект владельца не мигрирован, ссы …
- `srs/bc-component/contract-call/internal/README.md:37` — `2169861086` (страница комплекта: матрица): \| create-artifact (Недостающая цель ссылки) \| сервис notifications «[Уведомления] Сервис работы с уведомлениями» (платформенный, `_meta/services.json`) \| базовый контракт «[Уведомления] Метод отправки уведомления в Экосистеме пользователю Клиента» (страница владельца 2169861086) — комплект владел …
- `srs/bc-component/contract-call/internal/README.md:38` — `2169862216` (страница комплекта: матрица): \| create-artifact (Недостающая цель ссылки) \| сервис client-error-text-directory «[СпрОшибок] Справочник текстов ошибок отображаемых клиентам» (платформенный, `_meta/services.json`) \| базовый контракт «[СпрОшибок] Метод получения текста ошибки для клиента» (страница владельца 2169862216) — компле …
- `srs/bc-component/contract-call/internal/README.md:39` — `2169862216` (страница комплекта: матрица): \| create-artifact (Недостающая цель ссылки) \| сервис client-error-text-directory «[СпрОшибок] Справочник текстов ошибок отображаемых клиентам» (платформенный, `_meta/services.json`) \| базовый контракт «[СпрОшибок] Метод получения текста ошибки для клиента» (страница владельца 2169862216) — компле …

### srs/bc-component/contract-call/README.md

- `srs/bc-component/contract-call/README.md:43` — `2227445613` (страница комплекта: выгрузка): Страница «[КК] Интеграции» (2227445613):

### srs/bc-component/data-model/dictionaries.md

- `srs/bc-component/data-model/dictionaries.md:272` — `2184430056` (страница комплекта: frontmatter DM-001): Перенос страницы источника 2184430056 (draft). В исходных кодах строк 18, 21-23 использованы латиноязычные похожие символы — нормализованы в латиницу (К-30). Ссылки источника на страницы заменены именами карточек-держателей; замороженный контур [КК_B2B] — без карточки.

### srs/bc-component/process/proc-001-landing.md

- `srs/bc-component/process/proc-001-landing.md:22` — `2166860546` (страница комплекта: frontmatter PROC-001): Таблица шагов в источнике отсутствует — страница 2166860546 содержит только раздел «Назначение» и раздел «Схема» с подписью «Схема MS Visio:» без приложения; приложение недоступно. Шаги не синтезируются.

### srs/bc-component/screen-form/client/scr-cl-31-requests-journal.md

- `srs/bc-component/screen-form/client/scr-cl-31-requests-journal.md:452` — `2166860449` (страница комплекта: frontmatter SCR-CL-31): - [дефект среза — категория «дополнен текст» (решение 0.2)] в копии среза экспорта 4ef8138 шаг содержал склейку «то осуществляется_REQUEST)Удален (DELETE)»; полный текст шага перенесён дословно по sources/raw страницы 2166860449 (по решению владельца канона, заход 30.10.2026).

### srs/bc-issue/function/README.md

- `srs/bc-issue/function/README.md:52` — `2166859955` (страница комплекта: выгрузка): Страница «[КК_ВК] Функции Клиента» (2166859955):

### srs/bc-issue/process/proc-024-create-sign-send.md

- `srs/bc-issue/process/proc-024-create-sign-send.md:15` — `2166860046 и ещё 1` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 1.2 (шаг 1.2 страницы 2166860046); в процессе «(Этап 1)» — [PROC-022](proc-022-request-lifecycle.md), шаг 1.2 (шаг 1.2 страницы 2166860135).

### srs/bc-issue/process/proc-025-tessa-account-docs.md

- `srs/bc-issue/process/proc-025-tessa-account-docs.md:15` — `2166860046 и ещё 1` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.12 (шаг 2.12 страницы 2166860046); в процессе «(Этап 1)» — [PROC-022](proc-022-request-lifecycle.md), шаг 2.11 (шаг 2.11 страницы 2166860135).

### srs/bc-issue/process/proc-026-o2-dbs-esk-115.md

- `srs/bc-issue/process/proc-026-o2-dbs-esk-115.md:15` — `2166860046 и ещё 1` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.6 (шаг 2.6 страницы 2166860046); в процессе «(Этап 1)» — [PROC-022](proc-022-request-lifecycle.md), шаг 2.6 (шаг 2.6 страницы 2166860135); в шаге 1 среза указан шаг №2.7.

### srs/bc-issue/process/proc-027-accept-and-verify.md

- `srs/bc-issue/process/proc-027-accept-and-verify.md:15` — `2166860046 и ещё 1` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.1 (шаг 2.1 страницы 2166860046); в процессе «(Этап 1)» — [PROC-022](proc-022-request-lifecycle.md), шаг 2.1 (шаг 2.1 страницы 2166860135).

### srs/bc-issue/process/proc-028-export-operator.md

- `srs/bc-issue/process/proc-028-export-operator.md:15` — `2166860046 и ещё 1` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.31 (шаг 2.31 страницы 2166860046); в процессе «(Этап 1)» — [PROC-022](proc-022-request-lifecycle.md), шаг 2.15 (шаг 2.15 страницы 2166860135).

### srs/bc-issue/process/proc-029-esk-account-info.md

- `srs/bc-issue/process/proc-029-esk-account-info.md:15` — `2166860046 и ещё 1` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.10 (шаг 2.10 страницы 2166860046); в процессе «(Этап 1)» — [PROC-022](proc-022-request-lifecycle.md), шаг 2.9 (шаг 2.9 страницы 2166860135).

### srs/bc-issue/process/proc-030-knosis-statement.md

- `srs/bc-issue/process/proc-030-knosis-statement.md:15` — `2166860046 и ещё 1` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.5 (шаг 2.5 страницы 2166860046); в процессе «(Этап 1)» — [PROC-022](proc-022-request-lifecycle.md), шаг 2.5 (шаг 2.5 страницы 2166860135).

### srs/bc-issue/process/proc-031-rko-f1-upload.md

- `srs/bc-issue/process/proc-031-rko-f1-upload.md:15` — `2166860046 и ещё 1` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.9 (шаг 2.9 страницы 2166860046); в процессе «(Этап 1)» — [PROC-022](proc-022-request-lifecycle.md), шаг 2.8 (шаг 2.8 страницы 2166860135).

### srs/bc-issue/process/proc-032-abs-close-addendum.md

- `srs/bc-issue/process/proc-032-abs-close-addendum.md:15` — `2166860046` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.29 (шаг 2.29 страницы 2166860046).

### srs/bc-issue/process/proc-033-esk-card-info.md

- `srs/bc-issue/process/proc-033-esk-card-info.md:15` — `2166860046 и ещё 1` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.22 (шаг 2.22 страницы 2166860046); в процессе «(Этап 1)» [PROC-022](proc-022-request-lifecycle.md) вызова нет (страница 2166860135).

### srs/bc-issue/process/proc-034-esk-card-create.md

- `srs/bc-issue/process/proc-034-esk-card-create.md:15` — `2166860046 и ещё 1` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.19 (шаг 2.19 страницы 2166860046); в процессе «(Этап 1)» [PROC-022](proc-022-request-lifecycle.md) вызова нет (страница 2166860135).

### srs/bc-issue/process/proc-035-tessa-dossier.md

- `srs/bc-issue/process/proc-035-tessa-dossier.md:15` — `2166860046` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.28 (шаг 2.28 страницы 2166860046).

### srs/bc-issue/process/proc-037-abs-addendum-create.md

- `srs/bc-issue/process/proc-037-abs-addendum-create.md:15` — `2166860046` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.16 (шаг 2.16 страницы 2166860046).

### srs/bc-issue/process/proc-038-tessa-card-docs-upload.md

- `srs/bc-issue/process/proc-038-tessa-card-docs-upload.md:15` — `2166860046` (страница комплекта: frontmatter PROC-045): - **Оркестратор:** [PROC-045](proc-045-request-lifecycle-target.md) — вызывает процесс на шаге 2.21 (шаг 2.21 страницы 2166860046).

### srs/bc-issue/process/README.md

- `srs/bc-issue/process/README.md:32` — `2166860113 и ещё 5` (страница комплекта: frontmatter PROC-037): Остаток входного контура — Заход **z02** покрыт карточками PROC-029…PROC-036 (см. «Состав»): получение информации об открытии счёта и о выпуске карт из ЕСК, выписка в КНОСИС, выгрузка в РКО Ф1, закрытие доп. соглашения в АБС Ф1, создание заявки на выпуск карт в ЕСК, досье ТЕССА и параметры вызова за …

### srs/bc-issue/screen-form/README.md

- `srs/bc-issue/screen-form/README.md:9` — `2166860243` (страница комплекта: frontmatter SCR-BNK-09): \| SCR-BNK-09 \| Банк \| [Журнал заявок на выпуск карты и открытие счета](bank/scr-bnk-09-requests-journal/scr-bnk-09-main.md) \| `2166860243` \|
- `srs/bc-issue/screen-form/README.md:10` — `2166860263` (страница комплекта: frontmatter SCR-BNK-09.1): \| SCR-BNK-09.1 \| Банк \| [Примеры заполнения фильтров (для разработчиков)](bank/scr-bnk-09-requests-journal/scr-bnk-09.1-filter-fill-examples.md) \| `2166860263` \|
- `srs/bc-issue/screen-form/README.md:11` — `2166860264` (страница комплекта: frontmatter SCR-BNK-10): \| SCR-BNK-10 \| Банк \| [Просмотр заявки на выпуск карты и открытие счета](bank/scr-bnk-10-request-view.md) \| `2166860264` \|
- `srs/bc-issue/screen-form/README.md:12` — `2166860261` (страница комплекта: frontmatter SCR-BNK-11): \| SCR-BNK-11 \| Банк \| [Настройка скроллера Банка «Журнал заявок на выпуск карты и открытие счета»](bank/scr-bnk-11-requests-journal-scroller-settings.md) \| `2166860261` \|
- `srs/bc-issue/screen-form/README.md:13` — `2166860241` (страница комплекта: frontmatter SCR-BNK-16): \| SCR-BNK-16 \| Банк \| [Изменение статуса заявки](bank/scr-bnk-16-status-change.md) \| `2166860241` \|
- `srs/bc-issue/screen-form/README.md:14` — `2166860242` (страница комплекта: frontmatter SCR-BNK-17): \| SCR-BNK-17 \| Банк \| [Установка статуса выпуска КК](bank/scr-bnk-17-card-issue-status.md) \| `2166860242` \|
- `srs/bc-issue/screen-form/README.md:15` — `2166860176` (страница комплекта: frontmatter CALL-EXT-030): \| SCR-CL-19 \| Клиент \| [Заявка на выпуск карты — создание/редактирование](client/scr-cl-19-request-edit.md) \| `2166860176` \|
- `srs/bc-issue/screen-form/README.md:16` — `2166860206` (страница комплекта: frontmatter CALL-EXT-011): \| SCR-CL-20 \| Клиент \| [Подтверждение](client/scr-cl-20-confirmation.md) \| `2166860206` \|
- `srs/bc-issue/screen-form/README.md:17` — `2166860221 и ещё 4` (страница комплекта: frontmatter SCR-CL-21): \| SCR-CL-21 \| Клиент \| [Тексты согласий](client/scr-cl-21-consent-texts.md) \| `2166860221`/`2166860220`/`2166860217`/`2166860219`/`2166860218` \|
- `srs/bc-issue/screen-form/README.md:18` — `2166860168` (страница комплекта: frontmatter SCR-CL-22): \| SCR-CL-22 \| Клиент \| [Заявка на выпуск карты — просмотр](client/scr-cl-22-request-view.md) \| `2166860168` \|
- `srs/bc-issue/screen-form/README.md:19` — `2166860205` (страница комплекта: frontmatter SCR-CL-23): \| SCR-CL-23 \| Клиент \| [Ввод адреса](client/scr-cl-23-address-input.md) \| `2166860205` \|
- `srs/bc-issue/screen-form/README.md:20` — `2393138150` (страница комплекта: frontmatter SCR-CL-24): \| SCR-CL-24 \| Клиент \| [Сотрудники](client/scr-cl-24-employees.md) \| `2393138150` \|

### srs/bc-limits/function/README.md

- `srs/bc-limits/function/README.md:47` — `2166859665` (страница комплекта: выгрузка): > **Примечание.** Страница 2166859665 «[КК_ЛК] Клиент: Функции пакетной обработки заявок на управление лимитами» (35 строк) — оглавление-контейнер (TOC), не карточка; ссылки на 4 карточки пакетных функций (FUN-CL-16..19).

### srs/bc-limits/process/proc-006-create-sign-send.md

- `srs/bc-limits/process/proc-006-create-sign-send.md:15` — `2166859861` (страница комплекта: frontmatter PROC-005): - **Оркестратор:** [PROC-005](proc-005-request-lifecycle.md) — вызывает процесс на шаге 1.2 (шаг 1.2 страницы 2166859861).

### srs/bc-limits/process/proc-007-accept-and-verify.md

- `srs/bc-limits/process/proc-007-accept-and-verify.md:15` — `2166859861` (страница комплекта: frontmatter PROC-005): - **Оркестратор:** [PROC-005](proc-005-request-lifecycle.md) — вызывает процесс на шаге 2.1 (шаг 2.1 страницы 2166859861).

### srs/bc-limits/process/proc-008-execute-limit-change.md

- `srs/bc-limits/process/proc-008-execute-limit-change.md:15` — `2166859861` (страница комплекта: frontmatter PROC-005): - **Оркестратор:** [PROC-005](proc-005-request-lifecycle.md) — вызывает процесс на шаге 2.3 (шаг 2.3 страницы 2166859861); в шаге 1 среза указан шаг 2.4.

### srs/bc-limits/process/proc-009-tessa-dossier.md

- `srs/bc-limits/process/proc-009-tessa-dossier.md:15` — `2166859861` (страница комплекта: frontmatter PROC-005): - **Оркестратор:** [PROC-005](proc-005-request-lifecycle.md) — вызывает процесс на шаге 2.5 (шаг 2.5 страницы 2166859861); в шаге 1 среза указан шаг 2.4.

### srs/bc-pin/contract-call/README.md

- `srs/bc-pin/contract-call/README.md:42` — `2227445615` (страница комплекта: выгрузка): Страница «[КК_ПИН] Интеграции» (2227445615):

### srs/bc-pin/process/proc-043-pin-change-sequence-diagram.md

- `srs/bc-pin/process/proc-043-pin-change-sequence-diagram.md:16` — `2166861672` (страница комплекта: frontmatter PROC-042): - **Роль:** дочерняя страница [PROC-042](proc-042-pin-install.md) (ссылка со страницы 2166861672).

### srs/bc-pin/screen-form/README.md

- `srs/bc-pin/screen-form/README.md:9` — `2166861652` (страница комплекта: frontmatter SCR-BNK-12): \| SCR-BNK-12 \| Банк \| [Список операций по карте](bank/scr-bnk-12-2fa-operations-list.md) \| `2166861652` \|
- `srs/bc-pin/screen-form/README.md:10` — `2166861669` (страница комплекта: frontmatter SCR-BNK-13): \| SCR-BNK-13 \| Банк \| [Настройка скроллера Банка «Список операций по картам»](bank/scr-bnk-13-2fa-operations-list-scroller-settings.md) \| `2166861669` \|
- `srs/bc-pin/screen-form/README.md:11` — `2166861670` (страница комплекта: frontmatter SCR-BNK-14): \| SCR-BNK-14 \| Банк \| [Просмотр 2FA-операции](bank/scr-bnk-14-2fa-operation-view.md) \| `2166861670` \|
- `srs/bc-pin/screen-form/README.md:12` — `2274121416` (страница комплекта: frontmatter SCR-CL-25): \| SCR-CL-25 \| Клиент \| [Ошибка установки ПИН-кода](client/scr-cl-25-pin-install-error.md) \| `2274121416` \|
- `srs/bc-pin/screen-form/README.md:13` — `2295157126` (страница комплекта: frontmatter SCR-CL-26): \| SCR-CL-26 \| Клиент \| [Ввод кода подтверждения операции](client/scr-cl-26-otp-code-entry.md) \| `2295157126` \|
- `srs/bc-pin/screen-form/README.md:14` — `2295157138` (страница комплекта: frontmatter SCR-CL-27): \| SCR-CL-27 \| Клиент \| [Ошибка при подтверждении операции](client/scr-cl-27-otp-confirmation-error.md) \| `2295157138` \|
- `srs/bc-pin/screen-form/README.md:15` — `2251367195` (страница комплекта: frontmatter SCR-CL-28): \| SCR-CL-28 \| Клиент \| [ЭФ Клиента — индекс (TOC)](client/scr-cl-28-client-screen-forms-index.md) \| `2251367195` \|

### srs/bc-status/contract-call/external/README.md

- `srs/bc-status/contract-call/external/README.md:27` — `2166860733` (страница комплекта: frontmatter CALL-EXT-010): - Страница «[КК_БК] Параметры вызова процесса загрузки документов в ТЕССА» (2166860733) — главная страница [CALL-EXT-010](call-ext-010-tessa-dossier-upload.md): с 02.11 карточка перенесена из bc-component в bc-status (решение владельца: одна карточка — один вызов одного потребителя).

### srs/bc-status/function/README.md

- `srs/bc-status/function/README.md:50` — `2166860636` (страница комплекта: выгрузка): - Страница 2166860636 «[КК_БК] Системные функции» — TOC-контейнер, навигационная ссылка на 4 системные функции.
- `srs/bc-status/function/README.md:51` — `2166860640` (страница комплекта: выгрузка): - Страница 2166860640 «[КК_БК] Функции Банка» — источник формул раздела 2 банковских функций (матрица доступности), навигационная ссылка на 8 банковских функций.
- `srs/bc-status/function/README.md:52` — `2166860655` (страница комплекта: выгрузка): - Страница 2166860655 «[КК_БК] Функции Клиента» — источник формул раздела 2 клиентских функций; содержит таблицу «Доступность функций клиента от статуса заявки» (функция × 9 клиентских статусов), значения которой перенесены формулой в раздел 2 карточек функций.
- `srs/bc-status/function/README.md:56` — `2166860642 и ещё 1` (страница комплекта: выгрузка): - 2166860642, 2166860643 (GBO-64053, проверка ЭП заявки — банк) — разморозка после решения по GBO.
- `srs/bc-status/function/README.md:57` — `2166860656` (страница комплекта: матрица): - 2166860656 (GBO-29292, экспорт списка заявок — клиент) — задача введена тегом 07.11, карточки нет: долг в матрице, перенос решением владельца 07.11.2026.

### srs/bc-status/process/proc-014-request-lifecycle.md

- `srs/bc-status/process/proc-014-request-lifecycle.md:15` — `2166860755` (страница комплекта: frontmatter PROC-017): - **Роль:** вызывает подпроцессы [PROC-015 [КК_БК] Создать заявку на изменение статуса, подписать ЭП и отправить в Банк](proc-015-create-sign-send.md) (шаг 1.2), [PROC-016 [КК_БК] Принять и проверить заявку на изменение статуса](proc-016-accept-and-verify.md) (шаг 2.1), [PROC-018 [КК_БК] Создать дос …

### srs/bc-status/process/proc-015-create-sign-send.md

- `srs/bc-status/process/proc-015-create-sign-send.md:15` — `2166860688` (страница комплекта: frontmatter PROC-014): - **Оркестратор:** [PROC-014](proc-014-request-lifecycle.md) — вызывает процесс на шаге 1.2 (шаг 1.2 страницы 2166860688).

### srs/bc-status/process/proc-016-accept-and-verify.md

- `srs/bc-status/process/proc-016-accept-and-verify.md:15` — `2166860688` (страница комплекта: frontmatter PROC-014): - **Оркестратор:** [PROC-014](proc-014-request-lifecycle.md) — вызывает процесс на шаге 2.1 (шаг 2.1 страницы 2166860688).

### srs/bc-status/process/proc-017-execute-card-status-svfe.md

- `srs/bc-status/process/proc-017-execute-card-status-svfe.md:15` — `2166860755 и ещё 1` (страница комплекта: frontmatter PROC-017): - **Оркестратор:** [PROC-014](proc-014-request-lifecycle.md) — процесс инициируется на шаге №2.3 (шаг 1 страницы 2166860755); в шаге 2.3 страницы 2166860688 подпроцесс назван «[КК_БК] Выполнить блокировку карты в ПЦ».

### srs/bc-status/process/proc-018-tessa-dossier.md

- `srs/bc-status/process/proc-018-tessa-dossier.md:15` — `2166860688` (страница комплекта: frontmatter PROC-014): - **Оркестратор:** [PROC-014](proc-014-request-lifecycle.md) — вызывает процесс на шаге 2.4 (шаг 2.4 страницы 2166860688); в шаге 1 среза указан шаг 2.5.

### srs/bc-status/screen-form/README.md

- `srs/bc-status/screen-form/README.md:9` — `2166860557` (страница комплекта: frontmatter SCR-CL-16): \| SCR-CL-16 \| Клиент \| [Пакет заявок на изменение статуса карты — создание/редактирование](client/scr-cl-16-card-status-request-batch-edit/scr-cl-16-main.md) \| `2166860557` \|
- `srs/bc-status/screen-form/README.md:10` — `2166860586` (страница комплекта: frontmatter CALL-EXT-037): \| SCR-CL-17 \| Клиент \| [Заявка на изменение статуса карты — создание/редактирование](client/scr-cl-17-card-status-request-edit/scr-cl-17-main.md) \| `2166860586` \|
- `srs/bc-status/screen-form/README.md:11` — `2166860579` (страница комплекта: frontmatter SCR-CL-18): \| SCR-CL-18 \| Клиент \| [Заявка на изменение статуса КК — просмотр](client/scr-cl-18-card-status-request-view/scr-cl-18-main.md) \| `2166860579` \|
- `srs/bc-status/screen-form/README.md:12` — `2166860606` (страница комплекта: frontmatter SCR-BNK-06): \| SCR-BNK-06 \| Банк \| [Журнал заявок на изменение статуса карты](bank/scr-bnk-06-requests-journal/scr-bnk-06-main.md) \| `2166860606` \|
- `srs/bc-status/screen-form/README.md:13` — `2166860626` (страница комплекта: frontmatter SCR-BNK-06.1): \| SCR-BNK-06.1 \| Банк \| [Примеры заполнения фильтров (для разработчиков)](bank/scr-bnk-06-requests-journal/scr-bnk-06.1-filter-fill-examples.md) \| `2166860626` \|
- `srs/bc-status/screen-form/README.md:14` — `2166860625` (страница комплекта: frontmatter SCR-BNK-07): \| SCR-BNK-07 \| Банк \| [Настройка скроллера Банка «Журнал заявок на изменение статуса карты»](bank/scr-bnk-07-requests-journal-scroller-settings.md) \| `2166860625` \|
- `srs/bc-status/screen-form/README.md:15` — `2166860627` (страница комплекта: frontmatter SCR-BNK-08): \| SCR-BNK-08 \| Банк \| [Просмотр заявки на изменение статуса карты](bank/scr-bnk-08-request-view.md) \| `2166860627` \|
- `srs/bc-status/screen-form/README.md:16` — `2166860592 и ещё 1` (страница комплекта: frontmatter SCR-CL-32): \| SCR-CL-32 \| Клиент \| [Тексты согласий (контейнер)](client/scr-cl-32-consent-texts.md) \| `2166860592`, `2339485063` \|
- `srs/bc-status/screen-form/README.md:18` — `2166860627` (страница комплекта: frontmatter SCR-BNK-08): ЭФ Банка «Просмотр заявки на изменение статуса карты» (`2166860627`, ID SCR-BNK-08) — перенесена в z03.
- `srs/bc-status/screen-form/README.md:24` — `2166860668` (страница комплекта: выгрузка): \| `2166860668` \| [КК_БК] Функции Клиента: пакетная обработка заявок на блокировку — оглавление функций \| реестр функций зоны `[КК_БК]` (целевой артефакт функции — долг в [матрице](../../../traceability-matrix.md)); экранных форм не описывает, отдельной SCR-карточки не создаёт \|

### srs/README.md

- `srs/README.md:36` — `2166860385 и ещё 1` (страница комплекта: выгрузка): \| SCR-CL-06 \| (без файла) \| ЭФ Виджет «Карты к получению» — источник-заглушка (page 2166860385), контент перемещён на page 2169846685 вне скоупа; ID зарезервирован как долг (см. OQ-08) \|
- `srs/README.md:118` — `2166860626 и ещё 1` (страница комплекта: frontmatter SCR-BNK-06.1): Папка `scr-bnk-06-requests-journal/` (экран с дополнением) — оглавление в [`scr-bnk-06-requests-journal/README.md`](bc-status/screen-form/bank/scr-bnk-06-requests-journal/README.md). Классификация приложения 2166860626 (к `SCR-BNK-06` либо `SCR-BNK-07`) — см. OQ-127. ЭФ Банка «Просмотр заявки на изм …
- `srs/README.md:134` — `2166860261` (страница комплекта: frontmatter SCR-BNK-11): Папка `scr-bnk-09-requests-journal/` (экран с дополнением) — оглавление в [`scr-bnk-09-requests-journal/README.md`](bc-issue/screen-form/bank/scr-bnk-09-requests-journal/README.md). Настройка скроллера Банка к этой ЭФ (2166860261) — перенос в заход z02 серии ISS-03 (SCR-BNK-11). Зона `client/` — зах …

## i-строка (не блокирует)

i К-17: числа вида page_id вне множества страниц комплекта: 13, перечень до 10: srs/bc-component/contract-call/external/call-ext-001-card-operations-data.md:76 `9013027949`; srs/bc-issue/contract-call/external/call-ext-023-eko-accounts-for-cards.md:149 `046577411`; srs/bc-issue/contract-call/external/call-ext-023-eko-accounts-for-cards.md:149 `046577411`; srs/bc-issue/function/client/fun-cl-55-registry-import-mapping.md:83 `2184430096`; srs/bc-issue/ntf-notification.md:350 `6699000000`; srs/bc-issue/ntf-notification.md:399 `6699000000`; srs/bc-issue/screen-form/bank/scr-bnk-09-requests-journal/scr-bnk-09.1-filter-fill-examples.md:27 `1235434534`; srs/bc-limits/screen-form/bank/scr-bnk-03-requests-journal/scr-bnk-03.1-filter-fill-examples.md:27 `1235434534`; srs/bc-limits/screen-form/bank/scr-bnk-03-requests-journal/scr-bnk-03.1-filter-fill-examples.md:32 `1235434534`; srs/bc-status/ntf-notification.md:239 `7728053496`
