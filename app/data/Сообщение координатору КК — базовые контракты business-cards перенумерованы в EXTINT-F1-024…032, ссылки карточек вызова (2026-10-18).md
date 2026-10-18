# Координатору КК: базовые контракты business-cards в docs-external-contracts получили номера EXTINT-F1-024…032

Дата: 2026-10-18. От владельца канона. Касается карточек вызова внешних АС в комплекте
`src-business-cards` (`docs/srs/bc-component/contract-call/external/`).

## Что произошло

MR `!37` в общий репозиторий базовых контрактов `EAN/docs-external-contracts` (карточки Ф1 и
SVFE для корпоративных карт) ждал вливания с 29.09. За это время номера EXTINT-F1-008…016 в
trunk заняли другие команды (справки и копии, очереди РКО, ОТСГДС). Карточки business-cards
перенумерованы на первые свободные номера, содержание не менялось:

| Было | Стало | Файл в `f1/` |
| --- | --- | --- |
| EXTINT-F1-008 | EXTINT-F1-024 | `extint-f1-024-card-operations-data.md` |
| EXTINT-F1-009 | EXTINT-F1-025 | `extint-f1-025-account-operations-data.md` |
| EXTINT-F1-010 | EXTINT-F1-026 | `extint-f1-026-client-cards.md` |
| EXTINT-F1-011 | EXTINT-F1-027 | `extint-f1-027-payment-systems.md` |
| EXTINT-F1-012 | EXTINT-F1-028 | `extint-f1-028-client-accounts.md` |
| EXTINT-F1-013 | EXTINT-F1-029 | `extint-f1-029-corp-cards-client.md` |
| EXTINT-F1-014 | EXTINT-F1-030 | `extint-f1-030-card-operations-rest.md` |
| EXTINT-F1-015 | EXTINT-F1-031 | `extint-f1-031-account-report-rest.md` |
| EXTINT-F1-016 | EXTINT-F1-032 | `extint-f1-032-payment-systems-rest.md` |

EXTINT-SVFE-001 (`svfe/extint-svfe-001-card-tariffs-metrics.md`) номер не менял.

## Что нужно поправить в комплекте КК

Две вещи, одним MR, после того как `!37` влит (сообщу отдельно):

1. **Номера и имена файлов** в карточках вызова: 28 упоминаний EXTINT-F1-008…016 и ссылки на
   файлы по таблице выше. Трогать только упоминания контрактов business-cards: номера
   F1-008…016 в trunk теперь принадлежат чужим контрактам, и если где-то в комплекте есть
   ссылка на них по новому смыслу, её менять нельзя.
2. **Ветка в адресах.** Все 24 ссылки комплекта на `docs-external-contracts` ведут на
   `/-/blob/master/…`, а ветки `master` в этом репозитории нет, по умолчанию там `trunk`.
   Ссылки битые уже сейчас. По правилу адресации адрес должен быть стабильным: заменить
   `/-/blob/master/` на `/-/blob/HEAD/`. Это касается и ссылок на F1-002 и F1-003, которые не
   перенумеровывались.

Найти все места (из корня клона `src-business-cards`):

```powershell
Get-ChildItem -Path docs -Recurse -Filter *.md | Select-String -Pattern "docs-external-contracts/-/blob/master/|EXTINT-F1-0(0[89]|1[0-6])\b" | Select-Object Path, LineNumber, Line
```

После команды: ожидается около 50 строк в карточках `call-ext-*.md` каталога
`contract-call/external` и, возможно, в README этого каталога и в матрице трассировки.

Проверка после правки — та же команда поиска: вывод должен быть пустым. Доступность адресов
в GitLab самопроверка не проверяет, поэтому две-три ссылки стоит открыть в браузере.

## Вопросы

Строкой FB-NN в `feedback.md` комплекта, как обычно.
