# Постановка: починить `tests/test_rag_pipeline.py` — тест не собирается с марта 2026

Дата: 2026-10-28. Область — RAG-часть analyzer (`app/services/`, `app/rag_pipeline.py`), не прибор `app/scripts/CI`.
Коммит — по слову владельца.

## Проблема

Полный прогон `pytest tests` падает на сборе модуля:

```text
ImportError: cannot import name 'build_context' from 'app.services.context_builder'
```

История:

- тест пришёл в первом коммите репозитория `6b2d8b76` (2025-12-07, «Переключился с версии v2…») и с тех пор
  не менялся;
- функция `build_context` закомментирована в `a45cae87` (2026-03-25, «стабильно работающая версия 0.50.0»,
  автор git `black`), рабочая — `build_context_optimized`.

Импорт — не единственное устаревшее место. Тест писался под раскладку, где всё лежало в `app/rag_pipeline.py`,
и все `@patch` нацелены на `app.rag_pipeline.<имя>`. Сейчас код в `app/services/context_builder.py` и
`app/services/analysis_service.py`, а имена ищутся там:

| Подменяемое имя | В `app.rag_pipeline` | Где определено сейчас |
|---|---|---|
| `get_embeddings_model` | импорт есть | `app/llm_interface.py` |
| `get_vectorstore` | импорт есть | `app/embedding_store.py` |
| `get_platform_services` | нет | `app/service_registry.py` |
| `extract_key_queries` | нет | `app/semantic_search.py` |
| `build_chain` | определено | `app/rag_pipeline.py` |
| `build_context` | нет | нигде (закомментировано) |
| `resolve_service_code_by_user` | нет | `app/service_registry.py` |
| `get_page_content_by_id` | импорт есть | `app/confluence_loader.py` |
| `resolve_service_code_from_pages_or_user` | нет | `app/service_registry.py` |

Подмена в `app.rag_pipeline` не действует на код, который взял имя через свой `from … import`. Если починить
только импорт, тест соберётся, но часть случаев пойдёт в настоящие хранилище, LLM или Confluence. Тогда он
либо упадёт, либо (хуже) пройдёт по живым данным.

## Что сделать

1. Убрать `build_context` из импорта. Тесты `test_analyze_text_success` и `test_analyze_pages_success` подменяют
   `build_context` — сверить, что сейчас вызывают `analyze_text` и `analyze_pages` в `analysis_service.py`
   (видимо, `build_context_optimized`), и подменять это.
2. Перенацелить каждый `@patch` на модуль, где имя ищется при вызове: для `build_context_optimized` —
   `app.services.context_builder.<имя>`, для `analyze_*` — `app.services.analysis_service.<имя>`.
3. Сверить сигнатуры: `analyze_text(text, prompt_template=None, service_code=None)`, `analyze_pages(page_ids,
   prompt_template=None, …)`. В `analysis_service.py` два определения `analyze_pages*` (`analyze_pages` и
   `analyze_pages_multi_pass`); тест покрывает первое.
4. Если случай проверяет поведение, которого в коде больше нет, — удалить его с пояснением в сдаче, а не
   подгонять под новое поведение молча.

## Ограничители

- Тест не ходит в сеть, к LLM и в векторное хранилище: при прогоне без переменных окружения и без доступа к
  Confluence все случаи проходят.
- Код `app/services/*` и `app/rag_pipeline.py` не меняется — правится только тест. Если без правки кода не
  обойтись, сначала вопрос владельцу.
- Широкий прогон до и после правки: новых падений нет. В репозитории есть другие давние падения в RAG/маршрутах
  (`tests/test_agent.py`, `tests/test_routes/*`, `test_table_lists.py` и др.) — к этой задаче не относятся,
  в сдаче перечислить без починки.

## Сдача

Файл «Сдача — …» в `app/data`: дифф теста, число случаев (прошли / удалены с причиной), вывод
`pytest tests/test_rag_pipeline.py`, сравнение широкого прогона до и после.
