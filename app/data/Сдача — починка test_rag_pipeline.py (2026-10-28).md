# Сдача: починка `tests/test_rag_pipeline.py`

Дата: 2026-10-28. Постановка — «Постановка — починка test_rag_pipeline.py, тест не собирается с марта 2026
(2026-10-28)» (analyzer c911f6d8). Исполнитель — сессия «Правки прибора, акцепт и рутина». Не закоммичено —
коммит по слову владельца.

## Итог

Тест собирается и проходит: **7 passed** из 7, ни один случай не удалён. Код `app/services/*` и
`app/rag_pipeline.py` не менялся — правился только тест. Сеть не трогается: прогон с запретом
`socket.connect` — 7 passed, попыток соединения 0.

## Что изменено

| Случай | Было | Стало |
|---|---|---|
| импорт | `build_context` (закомментирована в `a45cae87`) | убран; остальные имена — те же |
| `test_build_context_basic` | подмены в `app.rag_pipeline` (`get_vectorstore`, `get_platform_services`) не действовали — шёл в настоящий поиск | подмены в `app.services.context_builder`: эмбеддинги, `get_bool_env` (включён только шаг «документы сервиса»), запросы, `unified_service_search`, `count_tokens`, имя типа; проверяется, что документ сервиса попал в контекст с заголовком и что поиск получил `service_code`, `exclude_page_ids` и запросы |
| `test_prepare_search_queries_with_text` | подмена `app.rag_pipeline.extract_key_queries` | `app.services.context_builder.extract_key_queries` |
| `test_prepare_search_queries_empty_text`, `test_fast_deduplicate_documents` | — | без изменений (подмен нет) |
| `test_analyze_text_success` | `build_context` и `chain.run` | `build_context_optimized` и `chain.invoke` — код перешёл на LCEL (пометка в коде «ИСПРАВЛЕНО: замена run() на invoke()»); подмены в `app.services.analysis_service`; добавлена проверка аргументов сборки контекста |
| `test_analyze_pages_success` | `get_page_content_by_id`, `build_context`, `chain.run`, `count_tokens` в `app.rag_pipeline` | страница — `app.page_cache.get_page_data_cached` (так её берёт код, импорт внутри функции), имя типа — `template_type_analysis.get_template_name_by_type`, промпт передаётся явно (файл промпта не читается), `invoke`; добавлена проверка, что анализируемая страница исключена из контекста |
| `test_analyze_pages_no_content` | подменял только `get_page_content_by_id` — определение сервиса шло в настоящий реестр | `get_page_data_cached` → `None`, сервис подменён; проверяется пустой результат и то, что LLM не вызывается |

Переводы строк (CRLF) сохранены.

## Широкий прогон

До правки (полный `pytest tests`, 2026-10-28): 61 failed, 2118 passed, 5 errors; среди ошибок —
`ERROR tests/test_rag_pipeline.py` (сбор). После правки (тот же набор, рабочее дерево поверх c911f6d8):
**60 failed, 2126 passed, 4 errors**. По спискам `FAILED`/`ERROR` новых падений нет. Ушли два:
`ERROR tests/test_rag_pipeline.py` (эта задача, +7 passed) и `test_transfer_gate_after_step.py::test_oq_regex_single_home`
(исправлен в c911f6d8, +1 passed). Строки журнала `ERROR app.page_cache…` в выводе — сообщения логгера из
других давних тестов, которые ходят в Confluence; их текст сменился с «нет соединения» на «нет страницы»
(сеть в этот прогон была доступна). На результаты тестов это не влияет.

Давние падения RAG-части и маршрутов к задаче не относятся и не чинились: `tests/test_agent.py` (4 ошибки
настройки), `tests/test_routes/test_content_extractor.py`, `test_loader.py`, `test_service_summary.py`,
`test_table_lists.py`, `test_spacing_fixes.py`, `test_table_header_order_fix.py`, `test_confluence_loader.py`,
`test_config_endpoint.py`, `test_context_retrieval_agent.py` и др. (закрытая сеть, устаревшие подмены).
