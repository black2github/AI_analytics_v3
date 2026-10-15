---
id: CALL-INT-000
title: 'Вызовы внутренних контрактов'
type: contract-call
service: onboarding-external
version: prod-2026-09
---

# Вызовы внутренних контрактов

Карточки вызовов методов **других сервисов Экосистемы** и платформенных методов **со спецификацией**. В карточке — использование в этом сервисе (место вызова, параметры и обработка ответа). Постановка базового контракта — у владельца.

Платформенные функции без спецификации вызова — записи `PLT-NNN` в [platform-functions.md](../../platform-functions.md).

## Реестр вызовов

| ID | Вызываемый контракт (владелец) | Базовый контракт | Процесс / место в сервисе | Карточка |
|---|---|---|---|---|
| CALL-INT-001 | выдан ошибочно — описан как платформенная функция [PLT-004 Сервис подсказки по организациям и ИП](../../platform-functions.md#plt-004-сервис-подсказки-по-организациям-и-ип), не переиспользовать | — | — | — |
| CALL-INT-002 | [ОНБ_2021] Метод поиска заявки ОНБ по идентификатору CRM (сервис ОНБ_2021) | постановка владельца вне комплекта | [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](../../screen-form/client/scr-cl-01-org-data.md), [EV-1. Открытие формы](../../screen-form/client/scr-cl-01-org-data.md#ev-1-открытие-формы), шаг 2 | [call-int-002-onb2021-find-request-by-crm-id.md](call-int-002-onb2021-find-request-by-crm-id.md) |
| CALL-INT-003 | [ОНБ_2021] Метод проверки возможности удалённого открытия счёта (сервис ОНБ_2021) | постановка владельца вне комплекта | [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](../../screen-form/client/scr-cl-01-org-data.md) и [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](../../screen-form/client/scr-cl-02-org-data-no-dadata.md), кнопка "Открыть счёт"; [PROC-001 Открытие счета с внешнего сайта](../../process/proc-001-open-account-from-external-site.md), шаг №1а | [call-int-003-onb2021-remote-account-open-check.md](call-int-003-onb2021-remote-account-open-check.md) |
| CALL-INT-004 | [ОНБ_КЗ] Метод определения профиля клиента (сервис ОНБ_КЗ) | постановка владельца вне комплекта | [PROC-001 Открытие счета с внешнего сайта](../../process/proc-001-open-account-from-external-site.md), шаг 1.9.1; анализ ответа на шаге 2.12.1 | [call-int-004-onbkz-client-profile.md](call-int-004-onbkz-client-profile.md) |
| CALL-INT-005 | [СКС] Метод генерации коротких ссылок (сервис СКС) | постановка владельца вне комплекта | [PROC-001 Открытие счета с внешнего сайта](../../process/proc-001-open-account-from-external-site.md), шаг №2а | [call-int-005-scs-short-url.md](call-int-005-scs-short-url.md) |
| CALL-INT-006 | uaa/clientuser/register - Первоначальная регистрация пользователя (UAA) | постановка владельца вне комплекта | шаг №4 процесса [Профиль] Процесс регистрации пользователя Клиента; [SCR-CL-03 ЭФ Клиента «Ввод данных заявителя с внешнего сайта»](../../screen-form/client/scr-cl-03-applicant.md), кнопка "Продолжить", шаг 2; [PROC-001 Открытие счета с внешнего сайта](../../process/proc-001-open-account-from-external-site.md), шаг 1.10 (Шаг №3а) | [call-int-006-uaa-clientuser-register.md](call-int-006-uaa-clientuser-register.md) |
| CALL-INT-007 | uaa/clientuser/completeRegister - Завершение регистрации пользователя (UAA) | постановка владельца вне комплекта | [SCR-CL-04 ЭФ Клиента «Подтверждение номера телефона»](../../screen-form/client/scr-cl-04-phone-confirm.md); [PROC-001 Открытие счета с внешнего сайта](../../process/proc-001-open-account-from-external-site.md), шаги 1.14, 2.8 | [call-int-007-uaa-clientuser-complete-register.md](call-int-007-uaa-clientuser-complete-register.md) |
| CALL-INT-008 | uaa/clientuser/renewConfirm - Повторная отправка кода подтверждения (UAA) | постановка владельца вне комплекта | [SCR-CL-04 ЭФ Клиента «Подтверждение номера телефона»](../../screen-form/client/scr-cl-04-phone-confirm.md), кнопка "Запросить повторно"; [PROC-001 Открытие счета с внешнего сайта](../../process/proc-001-open-account-from-external-site.md), шаги 1.17, 2.5 | [call-int-008-uaa-clientuser-renew-confirm.md](call-int-008-uaa-clientuser-renew-confirm.md) |
