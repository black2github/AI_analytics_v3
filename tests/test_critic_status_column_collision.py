# tests/test_critic_status_column_collision.py
#
# Свой столбец «status» в таблице источника (1.9.13; нашлось при разборе сигналов
# сторожа на выгрузке КК 1.9.11, страницы «[DEV] Примеры заполнения фильтров»).
# Экспортёр дописывает служебный столбец «status» в конец; критик искал ПЕРВЫЙ
# столбец с этим именем — столбец источника, его значения не похожи на ±ID, и
# apply/reject пропускали таблицу целиком: строки-вставки оставались в ПРОМ.
# Стало: критик берёт ПОСЛЕДНИЙ столбец «status». Пары: срабатывание (reject/apply
# по таблице со своим «status») и НЕсрабатывание (обычный служебный столбец,
# таблица только со своим «status» без правок).

from app.content_extractor import create_critic_extractor
from app.scripts.CI.critic import process_text_until_stable

TASK = "GBO-7"
GREEN = "rgb(0,128,0)"
CMAP = {"#008000": TASK}


def _md(rows):
    body = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows)
    html = f"<table><tbody><tr><th>Поле</th><th>status</th></tr>{body}</tbody></table>"
    return create_critic_extractor(CMAP).extract(html)


ROWS = [("a", "ACTIVE"),
        (f'<span style="color: {GREEN};">b</span>', f'<span style="color: {GREEN};">NEW</span>')]


class TestCollision:
    def test_reject_drops_inserted_row_and_keeps_source_column(self):
        r = process_text_until_stable(_md(ROWS), "reject", None)[0]
        assert r.strip() == "| Поле | status |\n| --- | --- |\n| a | ACTIVE |"

    def test_apply_keeps_row_and_drops_service_column(self):
        a = process_text_until_stable(_md(ROWS), "apply", TASK)[0]
        assert a.strip() == "| Поле | status |\n| --- | --- |\n| a | ACTIVE |\n| b | NEW |"

    def test_deleted_row(self):
        rows = [("a", "ACTIVE"),
                (f'<s><span style="color: {GREEN};">c</span></s>',
                 f'<s><span style="color: {GREEN};">OLD</span></s>')]
        md = _md(rows)
        assert "| c | OLD |" in process_text_until_stable(md, "reject", None)[0]
        assert "OLD" not in process_text_until_stable(md, "apply", TASK)[0]

    # --- НЕсрабатывание ---

    def test_regular_service_column(self):
        html = (f'<table><tbody><tr><th>Поле</th><th>Знач</th></tr><tr><td>a</td><td>1</td></tr>'
                f'<tr><td><span style="color: {GREEN};">b</span></td>'
                f'<td><span style="color: {GREEN};">2</span></td></tr></tbody></table>')
        md = create_critic_extractor(CMAP).extract(html)
        assert process_text_until_stable(md, "reject", None)[0].strip() == \
            "| Поле | Знач |\n| --- | --- |\n| a | 1 |"

    def test_source_status_column_without_edits_untouched(self):
        md = _md([("a", "ACTIVE"), ("b", "CLOSED")])
        assert md.strip() == "| Поле | status |\n| --- | --- |\n| a | ACTIVE |\n| b | CLOSED |"
        assert process_text_until_stable(md, "reject", None)[0] == md
