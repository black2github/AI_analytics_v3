# Матрица трассировки

Реестр связей между артефактами комплекта и реестр выданных ID.

Как читать:

- **строка таблицы покрытия — функция (`FUN`)**: перечисляет экраны, данные, контроли и печатные формы, которые она задействует;
- **вторая таблица покрытия — процесс (`PROC`)**: перечисляет вызываемые подпроцессы, функции, вызовы контрактов (`CALL-EXT` / `CALL-INT`), платформенные функции, экраны, контроли, данные и печатные формы, задействованные в шагах процесса;
- связи собраны здесь из ссылок в телах документов; при расхождении матрица приводится в соответствие с телами;
- **нумерация по контурам**: функции и экраны Клиента — `FUN-CL-NN` / `SCR-CL-NN`, Банка — `FUN-BNK-NN` / `SCR-BNK-NN`, системные функции без пользовательского контура — `FUN-SYS-NN` (номер из двух цифр);
- ID выдаётся строкой реестра в том же изменении, что и первая карточка; авансовых ID нет;
- матрица обновляется **в том же MR**, что и добавление или изменение артефакта.

## 1. Покрытие функций

| Функция | Название | Роль | Экраны (SCR) | Данные (ENT/EXT) | Контроли (CTL) | Печатные формы (PRN) |
| ------- | -------- | ---- | ------------ | ---------------- | -------------- | -------------------- |
| FUN-SYS-01 | Функция обработки ошибки 404 | Системная функция | SCR-CL-01 | — | — | — |

## 2. Покрытие процессов

| Процесс | Название | Вызывает (PROC) | Функции (FUN) | Интеграции (CALL-EXT / CALL-INT) | Платформенные функции (PLT) | Экраны (SCR) | Контроли (CTL) | Данные (ENT/EXT) | ПФ (PRN) |
| ------- | -------- | --------------- | ------------- | -------------------------------- | --------------------------- | ------------ | -------------- | ---------------- | -------- |
| PROC-001 | Открытие счета с внешнего сайта | — | — | CALL-INT-003, CALL-INT-004, CALL-INT-005, CALL-INT-006, CALL-INT-007, CALL-INT-008 | PLT-004 | SCR-CL-01, SCR-CL-02, SCR-CL-03, SCR-CL-04 | CTL-GRP-1, CTL-GRP-2 | EXT-001 | — |

## BRD-1. BRD → SRS (покрытие требований реализацией)

Единственное место стыковки слоёв: строка — фича/US, в колонках — функциональные требования, сквозной сценарий и реализующие артефакты SRS. BRD реконструирован из SRS (reverse-from-SRS); BRD и SRS в телах документов друг на друга не ссылаются.

| Фича | US | FR | UC | Функции (FUN) | Экраны (SCR) | Процессы (PROC) | Контроли (CTL) | Печатные формы (PRN) |
| ---- | -- | -- | -- | ------------- | ------------ | --------------- | -------------- | -------------------- |
| F-CL-01 Ввод данных организации/ИП | US-01 | FR-01.1…01.11 | UC-01 | FUN-SYS-01 | SCR-CL-01, SCR-CL-02 | PROC-001 | CTL-GRP-1 | — |
| F-CL-02 Выбор типа счёта | US-02 | FR-02.1…02.3 | UC-01 | — | SCR-CL-01, SCR-CL-02 | PROC-001 | CTL-013, CTL-014 | — |
| F-CL-03 Регистрация и подтверждение телефона заявителя | US-03 | FR-03.1…03.7 | UC-01 | — | SCR-CL-03, SCR-CL-04 | PROC-001 | CTL-GRP-2 | — |
| F-CL-04 Удалённое открытие счёта по ссылке-приглашению | US-04 | FR-04.1…04.4 | UC-01 | — | SCR-CL-01, SCR-CL-02, SCR-CL-03 | PROC-001 | CTL-015 | — |
| F-CL-05 Авторизация и продолжение оформления | US-05 | FR-05.1…05.4 | UC-01 | — | SCR-CL-01, SCR-CL-02, SCR-CL-03, SCR-CL-04 | PROC-001 | — | — |

## BRD-2. BR → фича/UC

Гейт — 0 правил без связи.

| Правило | Применяется в | Реализуется в (SRS) |
| ------- | ------------- | ------------------- |
| BR-01 | F-CL-02 | CTL-014 |
| BR-02 | F-CL-02, UC-01 | SCR-CL-01, SCR-CL-02 (FLD-8 «Тип счёта») |
| BR-03 | F-CL-03, F-CL-04, UC-01 | CTL-015, CTL-034 |
| BR-05 | F-CL-01, UC-01 | SCR-CL-01 (FLD-7 «Город обслуживания») |
| BR-06 | F-CL-05 | PROC-001 (шаг 2.12.1), CALL-INT-004 |
| BR-07 | F-CL-01, UC-01 | SCR-CL-01, SCR-CL-02, SCR-CL-03, SCR-CL-04 (EV-1), DM-001 |
| ТР-01 | F-CL-02 | SCR-CL-01, SCR-CL-02 (FLD-8 «Тип счёта»), DM-001 |
| ТР-02 | F-CL-05, UC-01 | PROC-001 (шаг 2.12.1) |

## BRD-3. UC → фичи

Гейт — 0 UC без связи.

| UC | Фичи |
| -- | ---- |
| UC-01 Открытие первого счёта с внешнего сайта | F-CL-01, F-CL-02, F-CL-03, F-CL-04, F-CL-05 |

## BRD-4. PRN → фича/сценарий

Печатных форм в комплекте нет — гейт = 0.

## BRD-5. Гейты достаточности BRD

Комплект BRD достаточен, когда все счётчики = 0 (инвентарь SRS — из реестров `function/README.md`, `process/README.md`, `control/README.md`).

| Гейт | Значение |
| ---- | -------- |
| Функции без US | 0 (FUN-SYS-01 связана с F-CL-01, US-01) |
| Сценарные процессы без UC | 0 (PROC-001 связан с UC-01) |
| Доменные политики без BR | 0 (BR-01…BR-03, BR-05…BR-07, ТР-01, ТР-02; форматные и вычислимые проверки, в том числе ИНН на 9909, осознанно вне BR — остаются контролями и правилами форм SRS) |
| Печатные формы без связи | 0 (печатных форм в комплекте нет) |
| Сироты BRD (F/US/FR/BR/UC без связи с SRS) | 0 (все фичи, US, FR, правила и UC связаны в BRD-1, BRD-2) |

## 3. Покрытие: API ↔ SRS

Слоя API в комплекте нет.

## 4. Реестр ID

Все выданные ID комплекта; выданные ошибочно помечены и не переиспользуются.

| ID | Название | Файл | Ссылка на внешний репозиторий |
| -- | -------- | ---- | ----------------------------- |
| DM-000 | Модель данных | [srs/data-model/README.md](srs/data-model/README.md) | — |
| DM-001 | [ОНБ_В] Настраиваемые параметры | [srs/data-model/dictionaries.md](srs/data-model/dictionaries.md) | — |
| EXT-001 | Сведения о физическом лице для удалённого открытия счёта (через МП) | [srs/data-model/dictionaries.md](srs/data-model/dictionaries.md) | — |
| EXT-002 | Справочник доверенных систем | [srs/data-model/dictionaries.md](srs/data-model/dictionaries.md) | — |
| EXT-003 | [Локализация] Параметры браузера | [srs/data-model/dictionaries.md](srs/data-model/dictionaries.md) | — |
| EXT-004 | Заявка на открытие первого счета_2021 | [srs/data-model/dictionaries.md](srs/data-model/dictionaries.md) | — |
| EXT-005 | Подразделение Банка | [srs/data-model/dictionaries.md](srs/data-model/dictionaries.md) | — |
| EXT-006 | Справочник городов | [srs/data-model/dictionaries.md](srs/data-model/dictionaries.md) | — |
| EXT-007 | Сведения для создания заявки на открытие первого счета из внешней системы | [srs/data-model/dictionaries.md](srs/data-model/dictionaries.md) | — |
| EXT-008 | Сведения о заявке на открытие первого счета из внешней системы (лиде) | [srs/data-model/dictionaries.md](srs/data-model/dictionaries.md) | — |
| CTL-000 | [ОНБ_В] Группа контролей №1 | [srs/control/README.md](srs/control/README.md) | — |
| CTL-GRP-1 | При нажатии кнопки "Открыть счёт" | [srs/control/README.md](srs/control/README.md) | — |
| CTL-GRP-2 | При нажатии кнопки "Продолжить" | [srs/control/README.md](srs/control/README.md) | — |
| CTL-001 | Выберите организацию: обязательность заполнения | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-002 | Выберите организацию: проверка длины | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-003 | Краткое наименование: обязательность заполнения | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-004 | Краткое наименование: проверка длины | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-005 | ИНН: обязательность заполнения | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-006 | ИНН: проверка длины | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-007 | ИНН: проверка отсутствия недопустимых символов | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-008 | ИНН: проверка ключевания | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-009 | КПП: обязательность заполнения | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-010 | КПП: проверка длины | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-011 | КПП: проверка отсутствия недопустимых символов | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-012 | Город обслуживания: обязательность заполнения | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-013 | Тип счёта: обязательность заполнения | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-014 | Тип счёта: проверка на бизнес логику | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-015 | Согласен на обработку и передачу персональных данных (ввод данных организации/ИП): проверка на бизнес логику | [srs/control/cards-org.md](srs/control/cards-org.md) | — |
| CTL-016 | Фамилия: обязательность заполнения | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-017 | Фамилия: проверка длины | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-018 | Фамилия: проверка отсутствия недопустимых символов | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-019 | Фамилия: проверка допустимого расположения спецсимволов | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-020 | Имя: обязательность заполнения | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-021 | Имя: проверка длины | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-022 | Имя: проверка отсутствия недопустимых символов | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-023 | Имя: проверка допустимого расположения спецсимволов | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-024 | Отчество: проверка длины | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-025 | Отчество: проверка отсутствия недопустимых символов | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-026 | Отчество: проверка допустимого расположения спецсимволов | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-027 | Мобильный телефон: обязательность заполнения | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-028 | Мобильный телефон: проверка длины | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-029 | Мобильный телефон: проверка отсутствия недопустимых символов | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-030 | Email: обязательность заполнения | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-031 | Email: проверка длины | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-032 | Email: проверка отсутствия недопустимых символов | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-033 | Капча (ввод): обязательность заполнения | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CTL-034 | Согласен на обработку и передачу персональных данных (ввод данных заявителя): проверка на бизнес логику | [srs/control/cards-applicant.md](srs/control/cards-applicant.md) | — |
| CALL-000 | Вызовы контрактов | [srs/contract-call/README.md](srs/contract-call/README.md) | — |
| CALL-INT-000 | Вызовы внутренних контрактов | [srs/contract-call/internal/README.md](srs/contract-call/internal/README.md) | — |
| CALL-INT-001 | выдан ошибочно — описан как PLT-004, не переиспользовать | — | — |
| CALL-INT-002 | [ОНБ_2021] Метод поиска заявки ОНБ по идентификатору CRM | [srs/contract-call/internal/call-int-002-onb2021-find-request-by-crm-id.md](srs/contract-call/internal/call-int-002-onb2021-find-request-by-crm-id.md) | — |
| CALL-INT-003 | [ОНБ_2021] Метод проверки возможности удалённого открытия счёта | [srs/contract-call/internal/call-int-003-onb2021-remote-account-open-check.md](srs/contract-call/internal/call-int-003-onb2021-remote-account-open-check.md) | — |
| CALL-INT-004 | [ОНБ_КЗ] Метод определения профиля клиента | [srs/contract-call/internal/call-int-004-onbkz-client-profile.md](srs/contract-call/internal/call-int-004-onbkz-client-profile.md) | — |
| CALL-INT-005 | [СКС] Метод генерации коротких ссылок | [srs/contract-call/internal/call-int-005-scs-short-url.md](srs/contract-call/internal/call-int-005-scs-short-url.md) | — |
| CALL-INT-006 | uaa/clientuser/register - Первоначальная регистрация пользователя | [srs/contract-call/internal/call-int-006-uaa-clientuser-register.md](srs/contract-call/internal/call-int-006-uaa-clientuser-register.md) | — |
| CALL-INT-007 | uaa/clientuser/completeRegister - Завершение регистрации пользователя | [srs/contract-call/internal/call-int-007-uaa-clientuser-complete-register.md](srs/contract-call/internal/call-int-007-uaa-clientuser-complete-register.md) | — |
| CALL-INT-008 | uaa/clientuser/renewConfirm - Повторная отправка кода подтверждения | [srs/contract-call/internal/call-int-008-uaa-clientuser-renew-confirm.md](srs/contract-call/internal/call-int-008-uaa-clientuser-renew-confirm.md) | — |
| PLT-000 | Платформенные функции и проверки | [srs/platform-functions.md](srs/platform-functions.md) | — |
| PLT-001 | Метод определения размерности экрана | [srs/platform-functions.md](srs/platform-functions.md) | — |
| PLT-002 | ЭКО_Получение текста согласия | [srs/platform-functions.md](srs/platform-functions.md) | — |
| PLT-003 | Модальное окно "Первое место в рейтинге MW" | [srs/platform-functions.md](srs/platform-functions.md) | — |
| PLT-004 | Сервис подсказки по организациям и ИП | [srs/platform-functions.md](srs/platform-functions.md) | — |
| SCR-000 | Экранные формы | [srs/screen-form/README.md](srs/screen-form/README.md) | — |
| SCR-CL-01 | [ОНБ_В] ЭФ Клиента "Ввод данных организации/ИП с внешнего сайта" | [srs/screen-form/client/scr-cl-01-org-data.md](srs/screen-form/client/scr-cl-01-org-data.md) | — |
| SCR-CL-02 | [ОНБ_В] ЭФ Клиента "Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA" | [srs/screen-form/client/scr-cl-02-org-data-no-dadata.md](srs/screen-form/client/scr-cl-02-org-data-no-dadata.md) | — |
| SCR-CL-03 | [ОНБ_В] ЭФ Клиента "Ввод данных заявителя с внешнего сайта" | [srs/screen-form/client/scr-cl-03-applicant.md](srs/screen-form/client/scr-cl-03-applicant.md) | — |
| SCR-CL-04 | [ОНБ_В] ЭФ Клиента "Подтверждение номера телефона" | [srs/screen-form/client/scr-cl-04-phone-confirm.md](srs/screen-form/client/scr-cl-04-phone-confirm.md) | — |
| FUN-000 | Функции системы | [srs/function/README.md](srs/function/README.md) | — |
| FUN-SYS-01 | [ОНБ_В] Банк: Функция обработки ошибки 404 | [srs/function/system/fun-sys-01-handle-404-error.md](srs/function/system/fun-sys-01-handle-404-error.md) | — |
| PROC-000 | Процессы | [srs/process/README.md](srs/process/README.md) | — |
| PROC-001 | [ОНБ_В] Открытие счета с внешнего сайта | [srs/process/proc-001-open-account-from-external-site.md](srs/process/proc-001-open-account-from-external-site.md) | — |
| BR-000 | Бизнес-правила | [brd/business-rules.md](brd/business-rules.md) | — |
| BR-01 | ИП не оформляет счёт головного исполнителя ГК | [brd/business-rules.md](brd/business-rules.md) | — |
| BR-02 | Перечень предлагаемых типов счёта | [brd/business-rules.md](brd/business-rules.md) | — |
| BR-03 | Согласие до продолжения оформления | [brd/business-rules.md](brd/business-rules.md) | — |
| BR-04 | выдан ошибочно — не бизнес-правило, не переиспользовать | — | — |
| BR-05 | Города обслуживания при вводе с подсказками | [brd/business-rules.md](brd/business-rules.md) | — |
| BR-06 | Направление в сервис открытия счетов клиентам МСБ | [brd/business-rules.md](brd/business-rules.md) | — |
| BR-07 | Выключенная доступность сервиса | [brd/business-rules.md](brd/business-rules.md) | — |
| ТР-01 | Типы счёта, предлагаемые для выбора | [brd/business-rules.md](brd/business-rules.md) | — |
| ТР-02 | Маршрутизация после авторизации | [brd/business-rules.md](brd/business-rules.md) | — |
| F-CL-01 | Фича: Ввод данных организации/ИП (US-01) | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| US-01 | Ввод данных организации/ИП | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.1 | Открытие формы ввода данных организации | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.2 | Переход по несуществующему адресу | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.3 | Формы доступны при открытом сервисе | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.4 | Подсказки по организациям и ИП | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.5 | Ручной ввод реквизитов | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.6 | Ручной ввод при отключённых подсказках | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.7 | Города обслуживания при вводе с подсказками | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.8 | Ошибки проверки данных организации | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.9 | Выключенный сервис — переход на аутентификацию | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.10 | Города обслуживания при ручном вводе | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| FR-01.11 | Отказ иностранным юридическим лицам | [brd/features/f-cl-01-org-data.md](brd/features/f-cl-01-org-data.md) | — |
| F-CL-02 | Фича: Выбор типа счёта (US-02) | [brd/features/f-cl-02-account-type.md](brd/features/f-cl-02-account-type.md) | — |
| US-02 | Выбор типа счёта | [brd/features/f-cl-02-account-type.md](brd/features/f-cl-02-account-type.md) | — |
| FR-02.1 | Предлагаемые типы счёта | [brd/features/f-cl-02-account-type.md](brd/features/f-cl-02-account-type.md) | — |
| FR-02.2 | Счёт головного исполнителя ГК для ИП | [brd/features/f-cl-02-account-type.md](brd/features/f-cl-02-account-type.md) | — |
| FR-02.3 | Тип счёта при заключении двустороннего ДБС | [brd/features/f-cl-02-account-type.md](brd/features/f-cl-02-account-type.md) | — |
| F-CL-03 | Фича: Регистрация и подтверждение телефона заявителя (US-03) | [brd/features/f-cl-03-applicant-registration.md](brd/features/f-cl-03-applicant-registration.md) | — |
| US-03 | Регистрация и подтверждение телефона заявителя | [brd/features/f-cl-03-applicant-registration.md](brd/features/f-cl-03-applicant-registration.md) | — |
| FR-03.1 | Открытие формы данных заявителя | [brd/features/f-cl-03-applicant-registration.md](brd/features/f-cl-03-applicant-registration.md) | — |
| FR-03.2 | Регистрация и отправка кода | [brd/features/f-cl-03-applicant-registration.md](brd/features/f-cl-03-applicant-registration.md) | — |
| FR-03.3 | Завершение регистрации по коду | [brd/features/f-cl-03-applicant-registration.md](brd/features/f-cl-03-applicant-registration.md) | — |
| FR-03.4 | Повторный запрос кода | [brd/features/f-cl-03-applicant-registration.md](brd/features/f-cl-03-applicant-registration.md) | — |
| FR-03.5 | Неверный код подтверждения | [brd/features/f-cl-03-applicant-registration.md](brd/features/f-cl-03-applicant-registration.md) | — |
| FR-03.6 | Согласие на обработку персональных данных | [brd/features/f-cl-03-applicant-registration.md](brd/features/f-cl-03-applicant-registration.md) | — |
| FR-03.7 | Неверный код с картинки | [brd/features/f-cl-03-applicant-registration.md](brd/features/f-cl-03-applicant-registration.md) | — |
| F-CL-04 | Фича: Удалённое открытие счёта по ссылке-приглашению (US-04) | [brd/features/f-cl-04-remote-opening.md](brd/features/f-cl-04-remote-opening.md) | — |
| US-04 | Продолжение оформления удалённого открытия счёта | [brd/features/f-cl-04-remote-opening.md](brd/features/f-cl-04-remote-opening.md) | — |
| FR-04.1 | Проверка возможности удалённого открытия | [brd/features/f-cl-04-remote-opening.md](brd/features/f-cl-04-remote-opening.md) | — |
| FR-04.2 | Переход по короткой ссылке | [brd/features/f-cl-04-remote-opening.md](brd/features/f-cl-04-remote-opening.md) | — |
| FR-04.3 | Удалённое открытие невозможно | [brd/features/f-cl-04-remote-opening.md](brd/features/f-cl-04-remote-opening.md) | — |
| FR-04.4 | Короткая ссылка не сформирована | [brd/features/f-cl-04-remote-opening.md](brd/features/f-cl-04-remote-opening.md) | — |
| F-CL-05 | Фича: Авторизация и продолжение оформления (US-05) | [brd/features/f-cl-05-continue-after-auth.md](brd/features/f-cl-05-continue-after-auth.md) | — |
| US-05 | Сохранение данных при уходе и продолжение после авторизации | [brd/features/f-cl-05-continue-after-auth.md](brd/features/f-cl-05-continue-after-auth.md) | — |
| FR-05.1 | Сохранение данных организации при уходе | [brd/features/f-cl-05-continue-after-auth.md](brd/features/f-cl-05-continue-after-auth.md) | — |
| FR-05.2 | Продолжение после авторизации | [brd/features/f-cl-05-continue-after-auth.md](brd/features/f-cl-05-continue-after-auth.md) | — |
| FR-05.3 | Маршрутизация по профилю | [brd/features/f-cl-05-continue-after-auth.md](brd/features/f-cl-05-continue-after-auth.md) | — |
| FR-05.4 | Авторизация не пройдена | [brd/features/f-cl-05-continue-after-auth.md](brd/features/f-cl-05-continue-after-auth.md) | — |
| UC-01 | Use Case: Открытие первого счёта с внешнего сайта | [brd/use-cases/uc-01-open-account.md](brd/use-cases/uc-01-open-account.md) | — |
| VIS-001 | Концепция сервиса (Service Vision) | [service-vision.md](service-vision.md) | — |
| GLO-001 | Глоссарий домена | [glossary.md](glossary.md) | — |

## 5. Долги по ссылкам

| Ожидатель | Цель | Долг |
| --------- | ---- | ---- |
| DM-001, SCR-CL-01, SCR-CL-02, SCR-CL-03, SCR-CL-04 | — | нет целевого артефакта screen-form «[Профиль] ЭФ Клиента "Аутентификация по логину и паролю"» у владельца userProfile — требуется публикация/миграция владельцем |
| DM-001 | — | нет целевого артефакта vision «[ОНБ_2021] Сервис открытия 1-го счета клиента (онбординг)» у владельца ONB — требуется публикация/миграция владельцем |
| CTL-005, CTL-008, CTL-017, CTL-021, CTL-024, CTL-028, CTL-029, CTL-031, CTL-032 | — | нет целевого артефакта control «Контроли единых полей» — требуется заход create-controls |
| CALL-INT-000, CALL-INT-002 | — | нет целевого артефакта internal-contract «[ОНБ_2021] Метод поиска заявки ОНБ по идентификатору CRM» у владельца ONB — требуется публикация/миграция владельцем |
| CALL-INT-000, CALL-INT-003 | — | нет целевого артефакта internal-contract «[ОНБ_2021] Метод проверки возможности удалённого открытия счёта» у владельца ONB — требуется публикация/миграция владельцем |
| CALL-INT-000, CALL-INT-004 | — | нет целевого артефакта internal-contract «[ОНБ_КЗ] Метод определения профиля клиента» у владельца ONB_KZ — требуется публикация/миграция владельцем |
| CALL-INT-000, CALL-INT-005 | — | нет целевого артефакта internal-contract «[СКС] Метод генерации коротких ссылок» у владельца shortLinkDirectory — требуется публикация/миграция владельцем |
| CALL-INT-000, CALL-INT-006 | — | нет целевого артефакта internal-contract «uaa/clientuser/register - Первоначальная регистрация пользователя» у владельца UAA — требуется публикация/миграция владельцем |
| CALL-INT-000, CALL-INT-007 | — | нет целевого артефакта internal-contract «uaa/clientuser/completeRegister - Завершение регистрации пользователя» у владельца UAA — требуется публикация/миграция владельцем |
| CALL-INT-000, CALL-INT-008 | — | нет целевого артефакта internal-contract «uaa/clientuser/renewConfirm - Повторная отправка кода подтверждения» у владельца UAA — требуется публикация/миграция владельцем |
| CALL-INT-005, CALL-INT-007, PROC-001, SCR-CL-01, SCR-CL-02, SCR-CL-03, SCR-CL-04 | — | нет целевого артефакта screen-form «[ОНБ_2021] ЭФ Клиента "Выбор организации/ИП" в режиме создания» у владельца ONB — требуется публикация/миграция владельцем |
| CALL-INT-005, PROC-001 | EXT-001 | — |
| CALL-INT-005, PROC-001 | — | параметр Количество часов, за которое необходимо подтвердить контакты по заявке на удаленное открытие счета не зафиксирован — требуется дозаход create-data-model |
| CALL-INT-006, PROC-001, SCR-CL-03 | — | нет целевого артефакта process «[Профиль] Процесс регистрации пользователя Клиента» у владельца userProfile — требуется публикация/миграция владельцем |
| CALL-INT-007, SCR-CL-04 | EXT-002 | — |
| PLT-002, SCR-CL-01, SCR-CL-02, SCR-CL-03 | EXT-003 | — |
| SCR-CL-01, SCR-CL-02 | EXT-004 | — |
| SCR-CL-01, SCR-CL-03 | EXT-007 | — |
| SCR-CL-03 | EXT-008 | — |
| SCR-CL-01, SCR-CL-03 | — | нет целевого артефакта data-model «АС ППБ_СИП_Получение лида для открытия первого счёта» — требуется заход create-data-model |
| SCR-CL-01 | EXT-005 | — |
| SCR-CL-02 | EXT-006 | — |
| SCR-CL-01, PROC-001 | — | нет целевого артефакта process «[ОНБ_2021] Создать / изменить заявку и отправить в банк» у владельца ONB — требуется публикация/миграция владельцем |
| SCR-CL-03 | — | нет целевого артефакта screen-form «[Профиль] ЭФ Клиента "Регистрация"» у владельца userProfile — требуется публикация/миграция владельцем |
| PROC-001 | — | нет целевого артефакта vision «[ОНБ_КЗ] Сервис открытия 1го счёта клиентам МСБ» у владельца ONB_KZ — требуется публикация/миграция владельцем |
| PROC-001 | — | нет целевого артефакта process «[ОНБ_МСБ] Сквозной бизнес-процесс» у владельца ONB_KZ — требуется публикация/миграция владельцем |
| PROC-001 | — | нет целевого артефакта screen-form «[ОНБ_МСБ] 4. Выбор типа заявки» у владельца ONB_KZ — требуется публикация/миграция владельцем |

## 6. Артефакты вне трассировки

Причины неполноты артефактов комплекта.

| Артефакт | ID / путь | Причина неполноты |
| -------- | --------- | ----------------- |
| Карточки вызовов внутренних контрактов | CALL-INT-002…008 | постановка вызываемых методов — у владельцев вне комплекта; в карточках — параметры и обработка ответа из экранных форм и процесса |
| Платформенные функции | PLT-001…004 | постановка методов платформы — вне комплекта; в записях — места вызова и используемые параметры |
