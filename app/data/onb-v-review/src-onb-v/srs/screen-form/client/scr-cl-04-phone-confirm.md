---
id: SCR-CL-04
title: '[ОНБ_В] ЭФ Клиента "Подтверждение номера телефона"'
type: screen-form
service: onboarding-external
version: prod-2026-09
confluence_page_ids: ['2188264158']
---

# ЭФ Клиента «Подтверждение номера телефона»

## 1. Назначение

ЭФ предназначена для подтверждения номера телефона нового пользователя клиента банка

**Как перейти:**

Перейти на ЭФ пользователь Клиента может:

- по кнопке "Продолжить" с [SCR-CL-03 ЭФ Клиента «Ввод данных заявителя с внешнего сайта»](scr-cl-03-applicant.md)
- По кнопке браузера "Вперед" с [SCR-CL-03 ЭФ Клиента «Ввод данных заявителя с внешнего сайта»](scr-cl-03-applicant.md)

## 2. Реестр полей

Правила полей — раздел 4 (FLD-N); открытие и реакции полей — раздел 5 (EV-N); кнопки — раздел 6 (B-N); сообщения — раздел 7 (MSG-N).

| № | Блок | Поле | Тип | Обяз. |
|---|---|---|---|---|
| 0 | — | FLD-1 «Баннер MW» | Гиперссылка | Да |
| 1 | — | FLD-2 «Заголовок» | Заголовок | Да |
| 2 | — | FLD-3 «Информация» | Текст | Да |
| 3 | — | FLD-4 «Код подтверждения» | Текст | Да |
| 4 | — | FLD-5 «Таймер» | Текст | Да |



## 4. Правила полей

### FLD-1. «Баннер MW»

- **Тип:** Гиперссылка
- **Способ заполнения:** Автоматически
- **Обязательность:** Да
- **Видимость:**
  - **Если** [PLT-001 Метод определения размерности экрана](../../platform-functions.md#plt-001-метод-определения-размерности-экрана).«XS» (не равно) != true **или** [PLT-001 Метод определения размерности экрана](../../platform-functions.md#plt-001-метод-определения-размерности-экрана).«S» (не равно) != true,
  - **то** отображается в верхней части ЭФ,
  - **иначе** отображается по тапу на иконку в нижней части ЭФ
  - Данный баннер должен отображаться на всех страницах авторизации.
- **Логика установки значения:** = "Лучший цифровой банк для корпоративных клиентов<br>ТОП-1 в рейтинге Markswebb"
- **Действие:** Кликабельный баннер с информацией о рейтинге MarksWebb. По нажатию на баннер открывается модальное окно: [PLT-003 Модальное окно "Первое место в рейтинге MW"](../../platform-functions.md#plt-003-модальное-окно-первое-место-в-рейтинге-mw)

### FLD-2. «Заголовок»

- **Тип:** Заголовок
- **Способ заполнения:** Автоматически
- **Обязательность:** Да
- **Видимость:** Название поля на ЭФ не отображается
- **Логика установки значения:** = "Введите код"

### FLD-3. «Информация»

- **Тип:** Текст
- **Формат:** +7 9NN ••• •• NN
- **Способ заполнения:** Автоматически
- **Обязательность:** Да
- **Видимость:** Название поля на ЭФ не отображается
- **Логика установки значения:** = "Код подтверждения отправлен на номер " + [SCR-CL-03 ЭФ Клиента «Ввод данных заявителя с внешнего сайта»](scr-cl-03-applicant.md).«Мобильный телефон» в формате, указанном выше

### FLD-4. «Код подтверждения»

- **Тип:** Текст
- **Способ заполнения:** Вручную
- **Обязательность:** Да
- **Видимость:** Название поля на ЭФ не отображается

### FLD-5. «Таймер»

- **Тип:** Текст
- **Способ заполнения:** Автоматически
- **Обязательность:** Да
- **Логика установки значения:**
  - ="Запросить повторно через" + ММ:СС
  - ММ:СС - таймер, отображает через какое время доступна повторная отправка кода подтверждения. ММ:СС = [CALL-INT-006 uaa/clientuser/register - Первоначальная регистрация пользователя](../../contract-call/internal/call-int-006-uaa-clientuser-register.md).«confirmationRequest.lifeTime» (после повторного запроса — [CALL-INT-008 uaa/clientuser/renewConfirm - Повторная отправка кода подтверждения](../../contract-call/internal/call-int-008-uaa-clientuser-renew-confirm.md).«lifeTime») - время, прошедшее с момента последнего запроса кода подтверждения


## 5. События

| ID | Триггер | Суть реакции |
|---|---|---|
| EV-1 | Открытие формы | Открытие ЭФ или переход по redirect url на [Профиль] ЭФ Клиента "Аутентификация по логину и паролю" по настройке сервиса; очистка введенных ранее данных при переходе кнопкой браузера "Вперед" |
| EV-2 | Изменение FLD-4 «Код подтверждения» | Инициируется нажатие B-2 «Условное продолжить» при вводе 6 цифр |


### EV-1. Открытие формы

- **Если** [[Настраиваемые параметры] ОНБ_В](../../data-model/dictionaries.md#настраиваемые-параметры).«onboardingExternal.enabled» == TRUE
- **то** ЭФ открывается и доступна пользователю в соответствии с описанной логикой
- **иначе** осуществляется переход по redirect url на [Профиль] ЭФ Клиента "Аутентификация по логину и паролю"

- **Если** переход на ЭФ осуществляется по нажатию кнопки браузера "Вперед",
- **то** очистить введенные ранее данные

### EV-2. Изменение FLD-4 «Код подтверждения»

- **Если** в поле FLD-4 «Код подтверждения» введено 6 цифр,
- **то** инициируется нажатие кнопки [B-2 «Условное продолжить»](#b-2-условное-продолжить)


## 6. Кнопки

### B-1. «Войти в ГПБ Бизнес-Онлайн» (в шапке справа)

- **Видимость:**
  - **Если** [PLT-001 Метод определения размерности экрана](../../platform-functions.md#plt-001-метод-определения-размерности-экрана).«S» или [PLT-001 Метод определения размерности экрана](../../platform-functions.md#plt-001-метод-определения-размерности-экрана).«XS» == true.
  - **то** кнопка отображается по тапу на иконку в правом верхнем углу
  - **иначе** отображается
- **При нажатии:**
  - **Логика отображения текста по нажатию:**
    - **Если** [PLT-001 Метод определения размерности экрана](../../platform-functions.md#plt-001-метод-определения-размерности-экрана).«XS» == true
    - **то** текст открывается в виде нижней шторки
    - **иначе** в виде модального окна
  - Открывается модальное окно/нижняя шторка "Предупреждение об уходе" — [MSG-1](#7-сообщения).

### B-2. «Условное продолжить»

- **Видимость:** Кнопка не отображается никогда
- **При нажатии:**
  - Вызывается метод [CALL-INT-007 uaa/clientuser/completeRegister - Завершение регистрации пользователя](../../contract-call/internal/call-int-007-uaa-clientuser-complete-register.md) Входящие параметры вызова заполняются следующим образом:
    - [CALL-INT-007 uaa/clientuser/completeRegister - Завершение регистрации пользователя](../../contract-call/internal/call-int-007-uaa-clientuser-complete-register.md).«Метод регистрации» = "EXTERNAL_SITE"
    - [CALL-INT-007 uaa/clientuser/completeRegister - Завершение регистрации пользователя](../../contract-call/internal/call-int-007-uaa-clientuser-complete-register.md).«Идентификатор запроса на регистрацию» = исходящие параметры метода [CALL-INT-006 uaa/clientuser/register - Первоначальная регистрация пользователя](../../contract-call/internal/call-int-006-uaa-clientuser-register.md).«Идентификатор запроса на подтверждение», вызванного на [SCR-CL-03 ЭФ Клиента «Ввод данных заявителя с внешнего сайта»](scr-cl-03-applicant.md)
    - [CALL-INT-007 uaa/clientuser/completeRegister - Завершение регистрации пользователя](../../contract-call/internal/call-int-007-uaa-clientuser-complete-register.md).«СМС-код подтверждения регистрации» = FLD-4 «Код подтверждения»
    - [CALL-INT-007 uaa/clientuser/completeRegister - Завершение регистрации пользователя](../../contract-call/internal/call-int-007-uaa-clientuser-complete-register.md).«Уникальный идентификатор приложения в IDP» = Уникальный идентификатор приложения в IDP в соответствии со справочником "[Справочник доверенных систем](../../data-model/dictionaries.md#реестр)"
  - **Шаг 1.1.**
    - **Если** исходящие параметры метода содержат [CALL-INT-007 uaa/clientuser/completeRegister - Завершение регистрации пользователя](../../contract-call/internal/call-int-007-uaa-clientuser-complete-register.md).«Системный код ошибки»
    - **то** выводится сообщение об ошибке, соответствующее значению кода, полученного в исходящих параметрах метода [CALL-INT-007 uaa/clientuser/completeRegister - Завершение регистрации пользователя](../../contract-call/internal/call-int-007-uaa-clientuser-complete-register.md).«Системный код ошибки» и осуществляется переход на шаг 3
    - **иначе** осуществляется переход на шаг 2
  - **Шаг 2.** Осуществляется переход по redirect url с передачей данных об организации на [ОНБ_2021] ЭФ Клиента "Выбор организации/ИП" в режиме создания
    - **Логика формирования redirect url:**
      - {{ссылка на[ОНБ_2021] ЭФ Клиента "Выбор организации/ИП" в режиме создания}}?source={{константа "LANDING_PAGE"}}&partnersite={{partnersite}}&promotion={{promotion}}&org={{org}}&inn={{inn}}&kpp={{kpp}}&city={{city}}&type={{type}}&saleRequestId={{saleRequestId}}&bilateralContract={{bilateralContract}}&idSale={{idSale}}
      - где:
        - **Если** [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Краткое наименование» == пусто
        - **то**
          - {{partnersite}}
            - **Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Сайт партнёра»
            - **то** {{partnersite}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Сайт партнёра»
            - **иначе** тег для передачи параметра не формируется
          - {{promotion}}
            - **Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Акция»
            - **то** {{promotion}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Акция»
            - **иначе** тег для передачи параметра не формируется
          - {{org}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Выберите организацию»
          - {{inn}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ИНН»
          - {{kpp}}
            - **Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«КПП» не пусто
            - **то** {{kpp}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«КПП»
            - **иначе** тег для передачи параметра не формируется
          - {{city}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Город обслуживания»
          - {{type}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Тип счёта», цифра, соответствующая значению в поле:
            - 1 - Расчётный счёт
            - 2 - Счёт исполнителя ГК
            - 3 - Счёт головного исполнителя ГК
            - 4 - Счёт участника закупок
          - {{saleRequestId}}
            - **Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID заявки на продажу в АС CRM Infor» не пусто,
            - **то** {{saleRequestId}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID заявки на продажу в АС CRM Infor»
            - **иначе** тег для передачи параметра не формируется
          - {{bilateralContract}}
            - **Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Заключение двустороннего ДБС» не пусто,
            - **то** {{bilateralContract}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Заключение двустороннего ДБС»
            - **иначе** тег для передачи параметра не формируется
          - {{idSale}}
            - **Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID записи сведений по заявке во внешней системе» не пусто,
            - **то** {{idSale}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID записи сведений по заявке во внешней системе»
            - **иначе** тег для передачи параметра не формируется
        - **иначе**
          - {{partnersite}}
            - **Если** [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Сайт партнёра»
            - **то** {{partnersite}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Сайт партнёра»
            - **иначе** тег для передачи параметра не формируется
          - {{promotion}}
            - **Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Акция»
            - **то** {{promotion}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Акция»
            - **иначе** тег для передачи параметра не формируется
          - {{org}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Краткое наименование»
          - {{inn}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«ИНН»
          - {{kpp}}
            - **Если** [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«КПП» не пусто
            - **то** {{kpp}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«КПП»
            - **иначе** тег для передачи параметра не формируется
          - {{city}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Город обслуживания»
          - {{type}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Тип счёта», цифра, соответствующая значению в поле:
            - 1 - Расчётный счёт
            - 2 - Счёт исполнителя ГК
            - 3 - Счёт головного исполнителя ГК
            - 4 - Счёт участника закупок
          - {{saleRequestId}}
            - **Если** [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«ID заявки на продажу в АС CRM Infor» не пусто,
            - **то** {{saleRequestId}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«ID заявки на продажу в АС CRM Infor»
            - **иначе** тег для передачи параметра не формируется
          - {{bilateralContract}}
            - **Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Заключение двустороннего ДБС» не пусто,
            - **то** {{bilateralContract}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Заключение двустороннего ДБС»
            - **иначе** тег для передачи параметра не формируется
          - {{idSale}}
            - **Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID записи сведений по заявке во внешней системе» не пусто,
            - **то** {{idSale}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID записи сведений по заявке во внешней системе»
            - **иначе** тег для передачи параметра не формируется
  - **Шаг 3.** Процесс завершен

### B-3. «Запросить повторно» (под полем FLD-4 «Код подтверждения»)

- **Видимость:**
  - **Если** время FLD-5 «Таймер» истекло,
  - **то** отображается,
  - **иначе** не отображается.
- **При нажатии:**
  - Вызывается метод [CALL-INT-008 uaa/clientuser/renewConfirm - Повторная отправка кода подтверждения](../../contract-call/internal/call-int-008-uaa-clientuser-renew-confirm.md), параметры вызова заполняются следующим образом:
  - [CALL-INT-008 uaa/clientuser/renewConfirm - Повторная отправка кода подтверждения](../../contract-call/internal/call-int-008-uaa-clientuser-renew-confirm.md).«Идентификатор запроса на подтверждение» = исходящие параметры метода [CALL-INT-006 uaa/clientuser/register - Первоначальная регистрация пользователя](../../contract-call/internal/call-int-006-uaa-clientuser-register.md).«Идентификатор запроса на подтверждение», вызванного на [SCR-CL-03 ЭФ Клиента «Ввод данных заявителя с внешнего сайта»](scr-cl-03-applicant.md)
  - **Если** запрос выполнен успешно и СМС с кодом подтверждения отправлен пользователю,
  - **то** пользователь остаётся на ЭФ, FLD-5 «Таймер» начинает отсчёт заново, кнопка не отображается до истечения времени FLD-5 «Таймер»
  - **иначе** пользователь остаётся на ЭФ, сообщение не выводится

### B-4. «Назад» (в левом верхнем углу карточки)

- **Видимость:**
  - **Если** [PLT-001 Метод определения размерности экрана](../../platform-functions.md#plt-001-метод-определения-размерности-экрана).«XS» == true
  - **то** отображается в виде иконки «<» (угловая стрелка влево)
  - **иначе** отображается в виде иконки «←» (стрелка влево)
- **При нажатии:** Осуществляется переход на [SCR-CL-03 ЭФ Клиента «Ввод данных заявителя с внешнего сайта»](scr-cl-03-applicant.md)

### B-5. «Обновить» (кнопка браузера)

- **Видимость:** всегда (кнопка браузера)
- **При нажатии:** Осуществляется переход на [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md)


## 7. Сообщения

| ID | Тип | Показ | Содержание |
|---|---|---|---|
| MSG-1 | Модальное окно | B-1 «Войти в ГПБ Бизнес-Онлайн» | "Предупреждение об уходе"<br>заголовок: "Покинуть страницу?"<br>текст: "Мы сохраним введённые данные. После авторизации в своем аккаунте, вы сможете продолжить заполнение заявки"<br>кнопки:<br>* "Сохранить и уйти" - при нажатии: осуществляется переход по redirect url с передачей данных об организации на [Профиль] ЭФ Клиента "Аутентификация по логину и паролю" для дальнейшей передачи данных об организации на [ОНБ_2021] ЭФ Клиента "Выбор организации/ИП" в режиме создания<br>&nbsp;&nbsp;&nbsp;&nbsp;**Логика формирования redirect url:** {{ссылка на [Профиль] ЭФ Клиента "Аутентификация по логину и паролю"}}?redirect_uri={{ссылка на[ОНБ_2021] ЭФ Клиента "Выбор организации/ИП" в режиме создания}}&source={{константа "LANDING_PAGE"}}&partnersite={{partnersite}}&promotion={{promotion}}&org={{org}}&inn={{inn}}&kpp={{kpp}}&city={{city}}&type={{type}}&saleRequestId={{saleRequestId}}&bilateralContract={{bilateralContract}}&idSale={{idSale}}где:<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Краткое наименование» == пусто<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то**<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{partnersite}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Сайт партнёра»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{partnersite}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Сайт партнёра»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{promotion}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Акция»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{promotion}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Акция»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{org}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Выберите организацию»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{inn}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ИНН»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{kpp}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«КПП» не пусто<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{kpp}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«КПП»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{city}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Город обслуживания»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{type}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Тип счёта», цифра, соответствующая значению в поле:<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* 1 - Расчётный счёт<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* 2 - Счёт исполнителя ГК<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* 3 - Счёт головного исполнителя ГК<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* 4 - Счёт участника закупок<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{saleRequestId}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID заявки на продажу в АС CRM Infor» не пусто,<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{saleRequestId}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID заявки на продажу в АС CRM Infor»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{bilateralContract}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Заключение двустороннего ДБС» не пусто,<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{bilateralContract}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Заключение двустороннего ДБС»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{idSale}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID записи сведений по заявке во внешней системе» не пусто,<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{idSale}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID записи сведений по заявке во внешней системе»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе**<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{partnersite}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Сайт партнёра»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{partnersite}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Сайт партнёра»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{promotion}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Акция»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{promotion}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Акция»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{org}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Краткое наименование»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{inn}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«ИНН»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{kpp}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«КПП» не пусто<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{kpp}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«КПП»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{city}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Город обслуживания»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{type}} = значение параметра [SCR-CL-02 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»](scr-cl-02-org-data-no-dadata.md).«Тип счёта», цифра, соответствующая значению в поле:<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* 1 - Расчётный счёт<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* 2 - Счёт исполнителя ГК<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* 3 - Счёт головного исполнителя ГК<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* 4 - Счёт участника закупок<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{saleRequestId}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID заявки на продажу в АС CRM Infor» не пусто,<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{saleRequestId}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID заявки на продажу в АС CRM Infor»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{bilateralContract}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Заключение двустороннего ДБС» не пусто,<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{bilateralContract}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«Заключение двустороннего ДБС»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;* {{idSale}}<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**Если** [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID записи сведений по заявке во внешней системе» не пусто,<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**то** {{idSale}} = значение параметра [SCR-CL-01 ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»](scr-cl-01-org-data.md).«ID записи сведений по заявке во внешней системе»<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;**иначе** тег для передачи параметра не формируется<br>* "Нет, остаться" - модальное окно закрывается, переход не осуществляется |
| MSG-2 | Информер | B-2 «Условное продолжить», шаг 1.1 | сообщение, соответствующее значению [CALL-INT-007 uaa/clientuser/completeRegister - Завершение регистрации пользователя](../../contract-call/internal/call-int-007-uaa-clientuser-complete-register.md).«Системный код ошибки» |




