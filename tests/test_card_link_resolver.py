# tests/test_card_link_resolver.py
#
# Фаза 3 перехода к location-независимому doc_id (см.
# app/scripts/CI/design-smart-link-doc-id.md, §4-6):
#   • резолвер {{...}}-first: смарт-ссылка {{SERVICE: label}} → url из манифеста
#     (lookup_by_doc_id); неразрешённая {{...}} остаётся для плагина (Фаза 4);
#   • изолированная ветка относительных путей (Вариант B): относительная ссылка →
#     путь цели от расположения карточки → lookup_by_path → url; иначе расплющивание.
#
# Модули CI используют sibling-импорты — добавляем каталог в sys.path.

import subprocess
import sys
from pathlib import Path

import pytest

_CI_DIR = Path(__file__).resolve().parent.parent / "app" / "scripts" / "CI"
if str(_CI_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_DIR))

from card_link_resolver import ManifestIndex, resolve_links_in_card  # noqa: E402


def _card(doc_id, url, name="T"):
    return {"name": name, "kind": "card", "doc_id": doc_id, "url": url}


class TestSmartLinkResolution:
    def test_smart_link_redirected_to_card_url(self):
        idx = ManifestIndex([_card("{{CC: Цель}}", "sub/target.md")])
        text, stats = resolve_links_in_card("[ссылка]({{CC: Цель}})", "other/source.md", idx)
        assert text == "[ссылка](sub/target.md)"
        assert (stats.redirected, stats.kept_interservice) == (1, 0)

    def test_smart_link_not_in_manifest_kept_for_plugin(self):
        # Другой сервис / непубличная цель — {{...}} остаётся как есть (резолвит плагин).
        text, stats = resolve_links_in_card("[x]({{ZZ: Чужая}})", "a/b.md", ManifestIndex([]))
        assert text == "[x]({{ZZ: Чужая}})"
        assert (stats.redirected, stats.kept_interservice) == (0, 1)

    def test_smart_link_in_html_form(self):
        idx = ManifestIndex([_card("{{CC: Цель}}", "sub/t.md")])
        text, stats = resolve_links_in_card('<a href="{{CC: Цель}}">x</a>', "a/b.md", idx)
        assert text == '<a href="sub/t.md">x</a>'
        assert stats.redirected == 1


class TestRelativeBranch:
    def test_relative_link_resolved_via_path_index(self):
        # Источник sub/source.md, ссылка ../other/target.md → other/target.md в манифесте.
        idx = ManifestIndex([_card("{{CC: Цель}}", "other/target.md")])
        text, stats = resolve_links_in_card("[t](../other/target.md)", "sub/source.md", idx)
        assert text == "[t](other/target.md)"
        assert stats.redirected == 1

    def test_relative_link_not_in_manifest_flattened(self):
        text, stats = resolve_links_in_card("[t](../x/y.md)", "sub/source.md", ManifestIndex([]))
        assert text == "t"
        assert stats.flattened == 1

    def test_same_dir_relative_link(self):
        idx = ManifestIndex([_card("{{CC: Сосед}}", "sub/neighbor.md")])
        text, stats = resolve_links_in_card("[n](neighbor.md)", "sub/source.md", idx)
        assert text == "[n](sub/neighbor.md)"
        assert stats.redirected == 1


class TestOtherClasses:
    def test_external_url_kept(self):
        text, stats = resolve_links_in_card("[t](https://x.com/a)", "a/b.md", ManifestIndex([]))
        assert text == "[t](https://x.com/a)"
        assert stats.kept_external == 1

    def test_confluence_scheme_flattened(self):
        text, stats = resolve_links_in_card("[t](confluence://123)", "a/b.md", ManifestIndex([]))
        assert text == "t"
        assert stats.flattened == 1


class TestManifestIndex:
    def test_path_index_only_for_card_kind(self):
        # swagger-запись (url — http) не должна попадать в path-индекс.
        idx = ManifestIndex([
            {"name": "Op", "kind": "swagger", "doc_id": "{{CC: Op}}", "url": "https://swagger/x"},
        ])
        assert idx.lookup_by_path("https://swagger/x") is None
        assert idx.lookup_by_doc_id("{{CC: Op}}") is not None


class TestRegexPerformance:
    """Защита от катастрофического бэктрекинга в _MD_LINK_RE.

    Патологический вход: открывающая '[' и длинный прогон экранированных скобок
    (\\[КК_ЛК\\] ...) БЕЗ последующего '](...)'. На старом регэкспе (ветка [^\\]],
    пересекавшаяся с \\. на бэкслеше) движок перебирал экспоненту замощений и зависал
    на минуты. Запускаем резолв в ОТДЕЛЬНОМ процессе с таймаутом: поток не годится —
    C-движок re удерживает GIL и не прерывается, signal.alarm на Windows недоступен,
    так что подвисший регэксп заблокировал бы и сам тест. Дочерний процесс по таймауту
    убивается, и тест падает (а не зависает), если баг вернётся.
    """

    def test_pathological_input_does_not_hang(self):
        # ~50 неоднозначных единиц — на старом регэкспе это уже минуты; на новом мгновенно.
        # Вход ASCII (\[KK\] ...) — суть бага в бэкслеше, не в кириллице; так избегаем
        # проблем с кодировкой консоли в дочернем процессе.
        child = (
            "import sys\n"
            "sys.path.insert(0, %r)\n" % str(_CI_DIR)
            + "from card_link_resolver import resolve_links_in_card, ManifestIndex\n"
            "bs = chr(92)\n"
            "unit = bs + '[KK' + bs + '] Zayavka '\n"
            "text = '[' + unit * 50 + 'tail with no link target'\n"
            "resolve_links_in_card(text, 'a/b.md', ManifestIndex([]))\n"
        )
        try:
            subprocess.run([sys.executable, "-c", child], timeout=15, check=True,
                           capture_output=True)
        except subprocess.TimeoutExpired:
            pytest.fail("резолв ссылок завис — вернулся катастрофический бэктрекинг _MD_LINK_RE")

    def test_escaped_brackets_in_link_text_preserved(self):
        # Корректность не должна пострадать от сужения «любого символа»:
        # экранированные скобки в тексте ссылки сохраняются, ссылка резолвится.
        idx = ManifestIndex([_card("{{CC: Заявка}}", "sub/zayavka.md")])
        text, stats = resolve_links_in_card(r"[\[КК_ЛК\] Заявка]({{CC: Заявка}})", "a/b.md", idx)
        assert text == r"[\[КК_ЛК\] Заявка](sub/zayavka.md)"
        assert stats.redirected == 1
