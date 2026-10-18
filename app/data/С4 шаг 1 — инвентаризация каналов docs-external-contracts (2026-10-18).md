# С4 шаг 1 — инвентаризация каналов docs-external-contracts (2026-10-18)

Срез С4, шаг 1 плана «README папок внешних АС и реестры docs-external-contracts, срезы С0–С5» (2026-10-18). Без правок файлов: по паспорту §1 каждой карточки — какие транспортные строки в нём есть и какой канал словаря шаблона (`contract-call.md`, раздел A) им соответствует. Решение владельца по таблице и развилкам — вход шага 2 (запись полей шапки).

Исполнитель — сессия «Правки прибора, акцепт и рутина». Снимок — `origin/trunk` `9367154` (рабочее дерево `C:\tmp\extc-trunk`). Карточек — 110 (`extint-*.md`, включая подкаталоги каналов Криптомодуля).

## Итог

- Канал определяется однозначно — **94** карточек: `rest` 48, `postmessage` 9, `online-adapter` 9, `suv` 9, `mq` 8, `kafka` 6, `file` 5.
- На решение — **16** карточек, пять развилок (А–Д) ниже.
- Синхронность: строка «Синхронность» в паспорте есть у 19 карточек (`sync` 13, `async` 6); у 90 нет — по плану на шаге 2 `sync` у них не ставится, утилита покажет ⚠; ещё у 1 — косвенно по тексту.
- Источник предложения: строки паспорта §1 (лейблы «Протокол взаимодействия», «Способ интеграции», «Тип (стиль) API», «Транспорт», «Тип запроса», «Тип сервиса», «Тип метода», «Формат сообщения», «Название топика/очереди»); если транспортных строк нет — токен канала в `title` вида «<АС>_<канал>_<название>»; ручные поправки — с основанием в таблице карточек. REST, указанный вместе с СУВ, онлайн-адаптером, MQ или Kafka, — способ вызова, не второй транспорт.

## Таблица «строка паспорта → канал»

Различные транспортные строки паспорта и предложенный канал (строки сокращены до 150 знаков).

| Строка паспорта (транспортные поля) | Карточек | Канал |
| --- | --- | --- |
| — (транспортных строк нет) | 6 | ?, `file`, `mq`, mq?, как у gpb-smev-001/002 |
| Протокол взаимодействия: Универсальный метод загрузки документов в досье: вызов платформенного процесса «Загрузить документы в досье» с набором входящ… | 1 | ? |
| Протокол взаимодействия: Файловый обмен | 3 | `file` |
| Протокол взаимодействия: Чтение файлов из сетевого каталога | 1 | `file` |
| Протокол взаимодействия: Kafka · Способ интеграции: PUB SUB · Формат сообщения: JSON · Название топика/очереди: ECO1.ClientBankToAUSN.V1 | 1 | `kafka` |
| Протокол взаимодействия: Kafka · Способ интеграции: PUB SUB · Формат сообщения: JSON · Название топика/очереди: USN.ClientBankToECO1.V1 | 1 | `kafka` |
| Протокол взаимодействия: Kafka · Способ интеграции: PUB SUB · Формат сообщения: JSON · Название топика/очереди: SLX.ClntModuleChangeManager.V1 | 1 | `kafka` |
| Протокол взаимодействия: СИП · Тип запроса:  | 1 | `kafka` |
| Протокол взаимодействия: Kafka · Способ интеграции: PUB SUB · Формат сообщения: JSON · Название топика/очереди: EC01.FeedBackResult.V1 | 1 | `kafka` |
| Протокол взаимодействия: Kafka · Способ интеграции: PUB SUB · Формат сообщения: JSON · Название топика/очереди: ECO1.FeedbackResultSurveyClient.V1 | 1 | `kafka` |
| Протокол взаимодействия: ОТСГДС | 3 | `mq`, mq? |
| Протокол взаимодействия: MQ (FAR-P) · Способ интеграции: ОТСГДС · Формат сообщения: XML · Название топика/очереди: Q.RKF.ECO.RS_PAYORD_CANCEL.01 | 1 | `mq` |
| Протокол взаимодействия: MQ (FAR\-P) · Способ интеграции: ОТСГДС · Формат сообщения: XML · Название топика/очереди: Q\.RKF\.ECO\_RUP\.RS\_KP\_RETAIL\.… | 1 | `mq` |
| Протокол взаимодействия: MQ (FAR\-P) · Способ интеграции: ОТСГДС · Формат сообщения: XML · Название топика/очереди: Q\.RKF\.ECO\.RS\_PAYORD\.01 | 1 | `mq` |
| Протокол взаимодействия: MQ (FAR\-P) · Способ интеграции: ОТСГДС · Формат сообщения: XML · Название топика/очереди: Q\.ECO\.RKF\.RQ\_PAYORD\.01 | 1 | `mq` |
| Протокол взаимодействия: Общебанковская транспортная сеть гарантированной доставки сообщений на основе Factor ESB (ОТСГДС), код в реестре АС - 645 · Т… | 1 | `mq` |
| Протокол взаимодействия: MQ · Способ интеграции: Kafka tls / АС "СИП" · Формат сообщения: XML · Название топика/очереди: [Полное описание](#описание-я… | 3 | mq? / kafka? |
| Протокол взаимодействия: Онлайн адаптер | 4 | `online-adapter` |
| Способ интеграции: Онлайн адаптер (синхронный вызов) · Тип (стиль) API: REST · Тип HTTP-метода (для REST): POST · Формат сообщения: application/x-www-… | 1 | `online-adapter` |
| Протокол взаимодействия: Онлайн-адаптер ЕСК (вызов процедуры `request`, XML в CLOB) | 1 | `online-adapter` |
| Протокол взаимодействия: Онлайн-адаптер ЕСК: вызов процедуры `Repr_Auth_Check(p_request clob) return clob`, где в `p_request` передаётся XML запроса, … | 1 | `online-adapter` |
| Протокол взаимодействия: Онлайн адаптер_REST | 1 | `online-adapter` |
| Протокол взаимодействия: REST · Транспорт: Онлайн адаптер · Тип запроса: POST | 1 | `online-adapter` |
| Протокол взаимодействия: XML (`OpenAccountService.xsd`), операция `getRkoContractEnum` | 1 | online-adapter? |
| Протокол взаимодействия: XML. Запрос — `QrcCommissionPaymentRequest`, ответ — `QrcCommissionPaymentResponse`; namespace ответа `urn:iso:std:iso:20022:… | 1 | online-adapter? |
| Способ интеграции: Прямое подключение через браузерный API · Тип (стиль) API: PostMessage (браузерный протокол сообщений) · Формат сообщения: JSON | 9 | `postmessage` |
| Протокол взаимодействия: REST · Тип запроса: POST | 11 | `rest` |
| Протокол взаимодействия: REST · Транспорт: HTTP\HTTPS · Тип запроса: POST | 6 | `rest` |
| Тип сервиса: REST · Тип метода: POST | 6 | `rest` |
| Тип сервиса: REST · Тип метода: GET | 3 | `rest` |
| Протокол взаимодействия: REST · Тип запроса: GET | 2 | `rest` |
| Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): POST · Формат сообщения: JSON | 2 | `rest` |
| Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): GET · Формат сообщения: BINARY | 2 | `rest` |
| Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): GET · Формат сообщения: JSON | 2 | `rest` |
| Протокол взаимодействия: REST, POST, JSON | 1 | `rest` |
| Протокол взаимодействия: REST · Тип HTTP-метода (для REST): GET | 1 | `rest` |
| Протокол взаимодействия: REST · Способ интеграции: Запрос-ответ (XML-документ передаётся в теле HTTP-запроса) · Формат сообщения: XML | 1 | `rest` |
| Протокол взаимодействия: REST · Транспорт: HTTP\HTTPS · Тип запроса: GET | 1 | `rest` |
| Протокол взаимодействия: REST (`POST`, JSON) | 1 | `rest` |
| Протокол взаимодействия: REST · Тип запроса: POST - для отправки файла | 1 | `rest` |
| Протокол взаимодействия: REST; POST HTTPS к сервису `api_cl_org_check.pl`; авторизация Basic Auth (`Authorization: base64(Логин_ТУЗ:Пароль_ТУЗ)`); тел… | 1 | `rest` |
| Протокол взаимодействия: REST | 1 | `rest` |
| Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): POST | 1 | `rest` |
| Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): PUT | 1 | `rest` |
| Протокол взаимодействия: REST (HTTP POST) · Тип запроса: POST | 1 | `rest` |
| Протокол взаимодействия: HTTP(S)/REST, JSON | 1 | `rest` |
| Протокол взаимодействия: REST, транспорт HTTP/HTTPS, формат обмена JSON; charset=utf-8 | 1 | `rest` |
| Протокол взаимодействия: REST (XML-тело, `POST`) | 1 | `rest` |
| Протокол взаимодействия: HTTP(S)/SOAP | 2 | rest? / soap? |
| Протокол взаимодействия: SOAP (HTTP POST), метод `SearchInCache` веб-сервиса `NSIEgripXML`, `Content-Type: text/xml`; ответ — SOAP-конверт с элементом… | 1 | rest? / soap? |
| Протокол взаимодействия: SOAP · Транспорт: HTTP · Тип запроса: POST | 1 | rest? / soap? |
| Протокол взаимодействия: SOAP · Тип запроса: POST | 1 | rest? / soap? |
| Протокол взаимодействия: СУВ | 5 | `suv` |
| Протокол взаимодействия: СУВ (XML `RequestQueryList`, получатель `CFT.BOX1`) | 3 | `suv` |
| Протокол взаимодействия: СУВ (XML `RequestQueryList`, получатель `CFT.RKO`) | 1 | `suv` |

## Решения владельца пилота 18.10

- **А — (а):** добавить канал `soap` («SOAP»). Карточки gpb-smev-001, gpb-smev-002, knosis-001,
  knosis-002, knosis-003 — `soap`; gpb-smev-003 (коды ошибок того же web-сервиса) — тоже `soap`.
  Нужна правка словаря: шаблон канона `contract-call.md`, раздел A, и таблица каналов утилиты
  `extint_registry.py` (analyzer и копия в каноне) — до шага 2.
- **Б — (б):** «ОТСГДС» — отдельный канал словаря (не `mq`). F1-006 и F1-014 («Протокол
  взаимодействия: ОТСГДС») — этот канал. **Открыто:** имя значения (`otsgds`?) и отображение
  («ОТСГДС»); куда относить карточки, где в паспорте или title есть и MQ, и ОТСГДС — F1-005
  (title «РКО Ф1_ОТСГДС_MQ_…»), F1-016 (title «РКО Ф1_ОТСГДС_MQ_…»), F1-017, F1-021, F1-022,
  F1-023 («MQ (FAR-P) | ОТСГДС»), khd-001 («сеть гарантированной доставки на основе Factor…»).
- **Г — (а):** F1-002 — `online-adapter` (паспорт страницы-источника); F1-004 — сверить по
  странице-источнику.
- **В, Д** — без решения: ждут ответа (В — аналитик или автор карточек BSK-002…004; Д — по
  каждой карточке).

## Развилки — решение владельца

**А. SOAP поверх HTTP (5 карточек):** `gpb-smev/extint-gpb-smev-001-put-documents.md`, `gpb-smev/extint-gpb-smev-002-get-documents.md`, `knosis/extint-knosis-001-egrip.md`, `knosis/extint-knosis-002-egrul.md`, `knosis/extint-knosis-003-universal-directory.md`. В словаре канала SOAP нет. (а) **рекомендую** — добавить канал `soap` («SOAP»): протокол и вид сообщений другой, слить с REST — потерять различие, которое видит потребитель; (б) отнести к `rest` — по транспорту HTTP. Тот же канал — `gpb-smev-003` (коды ошибок того же web-сервиса), если `gpb-smev-001/002` попадут сюда.

**Б. «ОТСГДС».** В `khd/extint-khd-001` строка паспорта прямо называет её «Общебанковская транспортная сеть гарантированной доставки сообщений на основе Factor…», у F1-017/021/022/023 — «MQ (FAR-P) | ОТСГДС». Значит, ОТСГДС — транспорт на MQ. (а) **рекомендую** — `mq` для F1-005 (по title уже `mq`), F1-006, F1-014; (б) отдельный канал `otsgds`.

**В. Два транспорта (BSK-002, BSK-003, BSK-004):** «Протокол взаимодействия: MQ | Способ интеграции: Kafka tls / АС «СИП»». Правило шаблона — канал запроса. Какой транспорт у запроса — из паспорта не следует; нужен ответ аналитика или владельца карточек (Самойленко, TEAMRKOUL-20977).

**Г. Вызовы РКО Ф1 с «XML» в §1 (F1-002, F1-004):** паспорт страницы-источника F1-002 — «Онлайн адаптер» (по MR !21 Друшлякова); в trunk §1 переписан как «XML». (а) **рекомендую** — `online-adapter` для F1-002; F1-004 — проверить по странице-источнику (title «Метод расчета комиссии в РКО Ф1»).

**Д. Без канала в словаре или без данных:** TESSA-001 (вызов платформенного процесса), crypto-module-021 (коды ошибок в `http/`, а текст говорит «только PostMessage»), F1-007 (паспорта транспорта нет; тело — «опрашивает входящую очередь» → `mq`?), gpb-smev-003 (как у семейства). Рекомендация: TESSA-001 — канал «—» до решения (⚠ утилиты, строка в реестре есть); crypto-module-021 — `rest` по каталогу либо перенос в `postmessage/` — решение владельца; F1-007 — `mq` после подтверждения аналитиком КиА; gpb-smev-003 — канал семейства.

Попутно: `epr/extint-epr-002` автоматически попала в `file` по слову «файла» в «POST — для отправки файла» — исправлено на `rest` (основание в таблице карточек).

## Для шага 2 (предварительно, не решение)

- `kind`: §2 и §3 (запрос и ответ) есть у 105 карточек — кандидаты `operation`; у 5 нет одного из разделов — кандидаты `format`, перечень на ревью готовлю на шаге 2.
- `sync`: из строки «Синхронность» — механика; без строки — не ставится (⚠).

## Карточки

| Карточка | Канал | Основание | Синхронность | Транспортные строки §1 |
| --- | --- | --- | --- | --- |
| `ausn/extint-ausn-001-taxpayers-chunked.md` | kafka | паспорт §1 | — | Протокол взаимодействия: Kafka · Способ интеграции: PUB SUB · Формат сообщения: JSON · Название топика/очереди… |
| `ausn/extint-ausn-002-chunk-acceptance.md` | kafka | паспорт §1 | — | Протокол взаимодействия: Kafka · Способ интеграции: PUB SUB · Формат сообщения: JSON · Название топика/очереди… |
| `bsk/extint-bsk-001-igk-check.md` | rest | паспорт §1 | sync | Протокол взаимодействия: REST, POST, JSON |
| `bsk/extint-bsk-002-paydocs.md` | mq? / kafka? | два транспорта: MQ и Kafka tls / АС «СИП» — развилка В | — | Протокол взаимодействия: MQ · Способ интеграции: Kafka tls / АС "СИП" · Формат сообщения: XML · Название топик… |
| `bsk/extint-bsk-003-paydocs-check.md` | mq? / kafka? | два транспорта: MQ и Kafka tls / АС «СИП» — развилка В | — | Протокол взаимодействия: MQ · Способ интеграции: Kafka tls / АС "СИП" · Формат сообщения: XML · Название топик… |
| `bsk/extint-bsk-004-paydocs-check-status.md` | mq? / kafka? | два транспорта: MQ и Kafka tls / АС «СИП» — развилка В | — | Протокол взаимодействия: MQ · Способ интеграции: Kafka tls / АС "СИП" · Формат сообщения: XML · Название топик… |
| `cdn/extint-cdn-001-public-ips-list.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип HTTP-метода (для REST): GET |
| `crm-brk/extint-crm-brk-001-client-profile.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Способ интеграции: Запрос-ответ (XML-документ передаётся в теле HTTP-запроса) … |
| `crm-infor/extint-crm-infor-001-client-managers-topic.md` | kafka | паспорт §1 | — | Протокол взаимодействия: Kafka · Способ интеграции: PUB SUB · Формат сообщения: JSON · Название топика/очереди… |
| `crypto-module/http/extint-crypto-module-001-validate-signatures.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `crypto-module/http/extint-crypto-module-002-initialize-key-container.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `crypto-module/http/extint-crypto-module-003-generate-certificate.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `crypto-module/http/extint-crypto-module-004-system-info.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `crypto-module/http/extint-crypto-module-005-logs.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `crypto-module/http/extint-crypto-module-006-verify-signature.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `crypto-module/http/extint-crypto-module-007-initialize-and-sign.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `crypto-module/http/extint-crypto-module-008-sign-data.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `crypto-module/http/extint-crypto-module-009-api-version.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: GET |
| `crypto-module/http/extint-crypto-module-010-module-version.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: GET |
| `crypto-module/http/extint-crypto-module-011-certificates.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `crypto-module/http/extint-crypto-module-021-error-codes.md` | ? | в каталоге http/, в тексте — «применимо только для PostMessage»; kind: format | — | — |
| `crypto-module/postmessage/extint-crypto-module-012-postmessage-module-version.md` | postmessage | паспорт §1 | — | Способ интеграции: Прямое подключение через браузерный API · Тип (стиль) API: PostMessage (браузерный протокол… |
| `crypto-module/postmessage/extint-crypto-module-013-postmessage-api-version.md` | postmessage | паспорт §1 | — | Способ интеграции: Прямое подключение через браузерный API · Тип (стиль) API: PostMessage (браузерный протокол… |
| `crypto-module/postmessage/extint-crypto-module-014-postmessage-generate-certificate.md` | postmessage | паспорт §1 | — | Способ интеграции: Прямое подключение через браузерный API · Тип (стиль) API: PostMessage (браузерный протокол… |
| `crypto-module/postmessage/extint-crypto-module-015-postmessage-initialize-key-container.md` | postmessage | паспорт §1 | — | Способ интеграции: Прямое подключение через браузерный API · Тип (стиль) API: PostMessage (браузерный протокол… |
| `crypto-module/postmessage/extint-crypto-module-016-postmessage-sign-data.md` | postmessage | паспорт (таблица без §1) | — | Способ интеграции: Прямое подключение через браузерный API · Тип (стиль) API: PostMessage (браузерный протокол… |
| `crypto-module/postmessage/extint-crypto-module-017-postmessage-system-info.md` | postmessage | паспорт §1 | — | Способ интеграции: Прямое подключение через браузерный API · Тип (стиль) API: PostMessage (браузерный протокол… |
| `crypto-module/postmessage/extint-crypto-module-018-postmessage-logs.md` | postmessage | паспорт §1 | — | Способ интеграции: Прямое подключение через браузерный API · Тип (стиль) API: PostMessage (браузерный протокол… |
| `crypto-module/postmessage/extint-crypto-module-019-postmessage-certificates.md` | postmessage | паспорт §1 | — | Способ интеграции: Прямое подключение через браузерный API · Тип (стиль) API: PostMessage (браузерный протокол… |
| `crypto-module/postmessage/extint-crypto-module-020-postmessage-extension-version.md` | postmessage | паспорт §1 | — | Способ интеграции: Прямое подключение через браузерный API · Тип (стиль) API: PostMessage (браузерный протокол… |
| `cryptopro-dss/extint-cryptopro-dss-001-authorize-certificate.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Транспорт: HTTP\HTTPS · Тип запроса: GET |
| `cryptopro-dss/extint-cryptopro-dss-002-operator-access-token.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Транспорт: HTTP\HTTPS · Тип запроса: POST |
| `cryptopro-dss/extint-cryptopro-dss-003-delegated-access-token.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Транспорт: HTTP\HTTPS · Тип запроса: POST |
| `cryptopro-dss/extint-cryptopro-dss-004-create-signature-operation.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Транспорт: HTTP\HTTPS · Тип запроса: POST |
| `cryptopro-dss/extint-cryptopro-dss-005-confirm-signature-operation.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Транспорт: HTTP\HTTPS · Тип запроса: POST |
| `cryptopro-dss/extint-cryptopro-dss-006-get-signed-document.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Транспорт: HTTP\HTTPS · Тип запроса: POST |
| `cryptopro-dss/extint-cryptopro-dss-007-upload-document-package.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Транспорт: HTTP\HTTPS · Тип запроса: POST |
| `dadata/extint-dadata-001-party-suggest.md` | rest | паспорт §1 | sync | Протокол взаимодействия: REST (`POST`, JSON) |
| `epaa/extint-epaa-001-oauth2-token.md` | online-adapter | паспорт §1 | sync? | Способ интеграции: Онлайн адаптер (синхронный вызов) · Тип (стиль) API: REST · Тип HTTP-метода (для REST): POS… |
| `epr/extint-epr-001-send-file.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `epr/extint-epr-002-create-recognition-task.md` | rest | REST POST; слово «файла» — предмет передачи, не канал | — | Протокол взаимодействия: REST · Тип запроса: POST - для отправки файла |
| `epr/extint-epr-003-get-recognition-results.md` | kafka | паспорт §1 | — | Протокол взаимодействия: СИП · Тип запроса:  |
| `epr/extint-epr-004-create-print-form.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST · Тип запроса: POST |
| `esk/extint-esk-001-request-115.md` | suv | паспорт §1 | async | Протокол взаимодействия: СУВ (XML `RequestQueryList`, получатель `CFT.RKO`) |
| `esk/extint-esk-002-check-relevance.md` | online-adapter | паспорт §1 | sync | Протокол взаимодействия: Онлайн-адаптер ЕСК (вызов процедуры `request`, XML в CLOB) |
| `esk/extint-esk-003-signing-authority.md` | online-adapter | паспорт §1 | sync | Протокол взаимодействия: Онлайн-адаптер ЕСК: вызов процедуры `Repr_Auth_Check(p_request clob) return clob`, гд… |
| `esk/extint-esk-004-org-preliminary-checks.md` | rest | паспорт §1 | sync | Протокол взаимодействия: REST; POST HTTPS к сервису `api_cl_org_check.pl`; авторизация Basic Auth (`Authorizat… |
| `esk/extint-esk-005-client-employee-search.md` | rest | паспорт §1 | sync | Протокол взаимодействия: REST |
| `esk/extint-esk-006-suv-product-registration-cr.md` | suv | паспорт §1 | async | Протокол взаимодействия: СУВ |
| `esk/extint-esk-007-address-type.md` | suv | паспорт §1 | — | Протокол взаимодействия: СУВ |
| `esk/extint-esk-008-io-client-individual.md` | suv | паспорт §1 | — | Протокол взаимодействия: СУВ |
| `esk/extint-esk-009-io-client-corporate.md` | suv | паспорт §1 | — | Протокол взаимодействия: СУВ |
| `f1/extint-f1-001-open-account.md` | suv | паспорт §1 | async | Протокол взаимодействия: СУВ (XML `RequestQueryList`, получатель `CFT.BOX1`) |
| `f1/extint-f1-002-dbs-list.md` | online-adapter? | паспорт страницы-источника — «Онлайн адаптер» (MR !21); в trunk §1 — «XML» | sync | Протокол взаимодействия: XML (`OpenAccountService.xsd`), операция `getRkoContractEnum` |
| `f1/extint-f1-003-balance-check.md` | online-adapter | паспорт §1 | sync | Протокол взаимодействия: Онлайн адаптер |
| `f1/extint-f1-004-commission-calc.md` | online-adapter? | §1 — только «XML»; как у прочих вызовов РКО Ф1 — проверить по источнику | sync | Протокол взаимодействия: XML. Запрос — `QrcCommissionPaymentRequest`, ответ — `QrcCommissionPaymentResponse`; … |
| `f1/extint-f1-005-account-reservation.md` | suv | паспорт §1 | async | Протокол взаимодействия: СУВ (XML `RequestQueryList`, получатель `CFT.BOX1`) |
| `f1/extint-f1-005-crypto-pro-license.md` | mq | title | — | Протокол взаимодействия: ОТСГДС |
| `f1/extint-f1-006-bs2-list.md` | suv | паспорт §1 | async | Протокол взаимодействия: СУВ (XML `RequestQueryList`, получатель `CFT.BOX1`) |
| `f1/extint-f1-006-cancel-account-reserve.md` | mq? | ОТСГДС — см. развилка Б | — | Протокол взаимодействия: ОТСГДС |
| `f1/extint-f1-007-tmg-dictionaries-for-control-and-accept.md` | mq? | тело: «опрашивает входящую очередь»; паспорта транспорта нет | — | — |
| `f1/extint-f1-008-planned-balance.md` | online-adapter | паспорт §1 | — | Протокол взаимодействия: Онлайн адаптер |
| `f1/extint-f1-009-accounts-list.md` | online-adapter | паспорт §1 | — | Протокол взаимодействия: Онлайн адаптер |
| `f1/extint-f1-010-account-tariff.md` | online-adapter | паспорт §1 | — | Протокол взаимодействия: Онлайн адаптер |
| `f1/extint-f1-011-queue-document-info.md` | mq | title | — | — |
| `f1/extint-f1-012-historical-queue-documents-csv.md` | file | title «РКО Ф1_FILE_…»; CSV-реестр | — | — |
| `f1/extint-f1-013-check-available.md` | online-adapter | паспорт §1 | — | Протокол взаимодействия: Онлайн адаптер_REST |
| `f1/extint-f1-014-get-reference.md` | mq? | ОТСГДС — см. развилка Б | — | Протокол взаимодействия: ОТСГДС |
| `f1/extint-f1-015-commission-payment.md` | suv | паспорт §1 | — | Протокол взаимодействия: СУВ |
| `f1/extint-f1-016-create-payment-order-chargeback.md` | mq | title | — | — |
| `f1/extint-f1-017-payment-order-chargeback-receipt.md` | mq | паспорт §1 | — | Протокол взаимодействия: MQ (FAR-P) · Способ интеграции: ОТСГДС · Формат сообщения: XML · Название топика/очер… |
| `f1/extint-f1-018-ped-register-file.md` | file | паспорт §1 | — | Протокол взаимодействия: Файловый обмен |
| `f1/extint-f1-019-reconciliation-incoming-file.md` | file | паспорт §1 | — | Протокол взаимодействия: Файловый обмен |
| `f1/extint-f1-020-reconciliation-outgoing-file.md` | file | паспорт §1 | — | Протокол взаимодействия: Файловый обмен |
| `f1/extint-f1-021-kp-retail-status-mq.md` | mq | паспорт §1 | — | Протокол взаимодействия: MQ (FAR\-P) · Способ интеграции: ОТСГДС · Формат сообщения: XML · Название топика/оче… |
| `f1/extint-f1-022-payment-receipt-mq.md` | mq | паспорт §1 | — | Протокол взаимодействия: MQ (FAR\-P) · Способ интеграции: ОТСГДС · Формат сообщения: XML · Название топика/оче… |
| `f1/extint-f1-023-payment-create-mq.md` | mq | паспорт §1 | — | Протокол взаимодействия: MQ (FAR\-P) · Способ интеграции: ОТСГДС · Формат сообщения: XML · Название топика/оче… |
| `fns-my-signature/extint-fns-my-signature-001-authorization.md` | rest | паспорт §1 | — | Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): POST · Формат сообщения: JSON |
| `fns-my-signature/extint-fns-my-signature-002-customer-search.md` | rest | паспорт §1 | — | Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): POST · Формат сообщения: JSON |
| `fns-my-signature/extint-fns-my-signature-003-certificate-file.md` | rest | паспорт §1 | — | Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): GET · Формат сообщения: BINAR… |
| `fns-my-signature/extint-fns-my-signature-004-workflow-data.md` | rest | паспорт §1 | — | Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): GET · Формат сообщения: JSON |
| `fns-my-signature/extint-fns-my-signature-005-create-workflow.md` | rest | паспорт §1 | — | Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): POST |
| `fns-my-signature/extint-fns-my-signature-006-workflow-documents.md` | rest | паспорт §1 | — | Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): GET · Формат сообщения: JSON |
| `fns-my-signature/extint-fns-my-signature-007-delete-workflow.md` | rest | паспорт §1 | — | Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): PUT |
| `fns-my-signature/extint-fns-my-signature-008-signatures.md` | rest | паспорт §1 | — | Способ интеграции: GPB API · Тип (стиль) API: REST · Тип HTTP-метода (для REST): GET · Формат сообщения: BINAR… |
| `gpb-smev/extint-gpb-smev-001-put-documents.md` | rest? / soap? | SOAP поверх HTTP — развилка А | — | Протокол взаимодействия: HTTP(S)/SOAP |
| `gpb-smev/extint-gpb-smev-002-get-documents.md` | rest? / soap? | SOAP поверх HTTP — развилка А | — | Протокол взаимодействия: HTTP(S)/SOAP |
| `gpb-smev/extint-gpb-smev-003-error-codes.md` | как у gpb-smev-001/002 | коды ошибок web-сервиса idbank_common; kind: format | — | — |
| `khd/extint-khd-001-smft-payment-events.md` | mq | паспорт §1 | — | Протокол взаимодействия: Общебанковская транспортная сеть гарантированной доставки сообщений на основе Factor … |
| `knosis/extint-knosis-001-egrip.md` | rest? / soap? | SOAP поверх HTTP — развилка А | sync | Протокол взаимодействия: SOAP (HTTP POST), метод `SearchInCache` веб-сервиса `NSIEgripXML`, `Content-Type: tex… |
| `knosis/extint-knosis-002-egrul.md` | rest? / soap? | SOAP поверх HTTP — развилка А | sync | Протокол взаимодействия: SOAP · Транспорт: HTTP · Тип запроса: POST |
| `knosis/extint-knosis-003-universal-directory.md` | rest? / soap? | SOAP поверх HTTP — развилка А | — | Протокол взаимодействия: SOAP · Тип запроса: POST |
| `knosis/extint-knosis-004-bic-directory.md` | file | паспорт §1 | — | Протокол взаимодействия: Чтение файлов из сетевого каталога |
| `mdm/extint-mdm-001-clean-service-do-clean.md` | rest | паспорт §1 | — | Протокол взаимодействия: REST (HTTP POST) · Тип запроса: POST |
| `mdm/extint-mdm-002-suggestions-suggest-party.md` | online-adapter | паспорт §1 | — | Протокол взаимодействия: REST · Транспорт: Онлайн адаптер · Тип запроса: POST |
| `mflash/extint-mflash-001-user-auth.md` | rest | паспорт §1 | — | Тип сервиса: REST · Тип метода: POST |
| `mflash/extint-mflash-002-create-flash.md` | rest | паспорт §1 | — | Тип сервиса: REST · Тип метода: POST |
| `mflash/extint-mflash-003-flash-list.md` | rest | паспорт §1 | — | Тип сервиса: REST · Тип метода: GET |
| `mflash/extint-mflash-004-prepare-upload.md` | rest | паспорт §1 | — | Тип сервиса: REST · Тип метода: POST |
| `mflash/extint-mflash-005-upload-part.md` | rest | паспорт §1 | — | Тип сервиса: REST · Тип метода: POST |
| `mflash/extint-mflash-006-file-status.md` | rest | паспорт §1 | — | Тип сервиса: REST · Тип метода: GET |
| `mflash/extint-mflash-007-prepare-download.md` | rest | паспорт §1 | — | Тип сервиса: REST · Тип метода: POST |
| `mflash/extint-mflash-008-download-file.md` | rest | паспорт §1 | — | Тип сервиса: REST · Тип метода: GET |
| `mflash/extint-mflash-009-delete.md` | rest | паспорт §1 | — | Тип сервиса: REST · Тип метода: POST |
| `mro/extint-mro-001-kafka-feedback-result.md` | kafka | паспорт §1 | — | Протокол взаимодействия: Kafka · Способ интеграции: PUB SUB · Формат сообщения: JSON · Название топика/очереди… |
| `nbo/extint-nbo-001-kafka-feedback-result-survey.md` | kafka | паспорт §1 | — | Протокол взаимодействия: Kafka · Способ интеграции: PUB SUB · Формат сообщения: JSON · Название топика/очереди… |
| `payment-hub/extint-payment-hub-001-get-charges.md` | rest | паспорт §1 | — | Протокол взаимодействия: HTTP(S)/REST, JSON |
| `sbp/extint-sbp-001-qr-registration.md` | rest | паспорт §1 | sync | Протокол взаимодействия: REST, транспорт HTTP/HTTPS, формат обмена JSON; charset=utf-8 |
| `stoplist/extint-stoplist-001-organization-check.md` | rest | паспорт §1 | sync | Протокол взаимодействия: REST (XML-тело, `POST`) |
| `tessa/extint-tessa-001-upload.md` | ? | вызов платформенного процесса «Загрузить документы в досье» — в словаре нет | async | Протокол взаимодействия: Универсальный метод загрузки документов в досье: вызов платформенного процесса «Загру… |
