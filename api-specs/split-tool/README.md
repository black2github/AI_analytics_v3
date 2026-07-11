# Доменный сплит спеки business-cards

Раскладывает `api-specs/business-cards-client.yaml` (фактически JSON) на доменные
папки для удобного анализа/редактирования, **без изменения результата генерации кода**:
после `redocly bundle` собранная спека структурно идентична исходной (проверено
порядко-независимым сравнением).

## Структура вывода (`api-specs/business-cards-split/`)

```
openapi.yaml              точка входа: info/servers/security + $ref на paths и schemas
paths/<domain>/*.yaml     по файлу на каждый path item (79 шт.)
components/
  common/*.yaml           схемы, используемые >1 доменом (59 — обёртки, фильтры, paging)
  <domain>/*.yaml         схемы, приватные для одного домена (144)
```

Домены: `issuance` (card-issue), `limits` (set-limits, batch-set-limits),
`blocking` (blocking, batch-blocking), `reports`, `misc`, `request-misc`.
Маппинг path → домен задан в `split_spec.py` (`REQUEST_MAP` / `path_domain`).

## Рабочий цикл

```bash
# 1. (Пере)разложить из исходника
python api-specs/split-tool/split_spec.py

# 2. Редактировать/анализировать удобные мелкие файлы в business-cards-client-split/

# 3. Собрать обратно единый файл для генератора кода
npx @redocly/cli bundle api-specs/business-cards-client-split/openapi.yaml -o api-specs/business-cards-client.json

# 3b. Либо собрать единую спеку в YAML (для просмотра целиком)
npx @redocly/cli bundle api-specs/business-cards-client-split/openapi.yaml -o api-specs/business-cards-client.bundled.yaml --ext yaml
```

## Замечания

- `redocly lint` показывает 2 ошибки + 3 предупреждения — они **предсуществующие**
  (тот же набор у исходного файла): `securitySchemes` названа `Bearer`, а `security`
  ссылается на `Authorization`; поле `name` недопустимо для `http`-схемы. Сплит их
  не добавляет и не чинит — воспроизводит спеку as-is.
- Сплиттер обрабатывает только `$ref` вида `#/components/schemas/...` — в этой спеке
  других ссылок нет. При появлении ref на parameters/responses скрипт нужно расширить.
