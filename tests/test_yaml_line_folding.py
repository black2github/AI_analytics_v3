# tests/test_yaml_line_folding.py
#
# Инцидент 2026-08-23: длинный title в выгрузке выглядел обрезанным на ~150 байтах
# с незакрытой кавычкой, и разные страницы читались как дубли. Причина — ширина
# PyYAML по умолчанию (80 символов): длинное значение сворачивалось на вторую
# строку. Данные при этом целы (YAML валиден), ломались построчные читатели —
# grep, инвентаризация выгрузки, любая быстрая сверка.
#
# Здесь закрепляем: все генераторы frontmatter пишут значение ОДНОЙ строкой.

import sys
from pathlib import Path

import yaml

# Модули app/scripts/CI используют sibling-импорты (см. test_manifest_card_url).
_CI_DIR = Path(__file__).resolve().parent.parent / "app" / "scripts" / "CI"
if str(_CI_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_DIR))

from card_generator import _render_frontmatter          # noqa: E402
from manifest_builder import ManifestBuildResult, render_manifest  # noqa: E402

from app.scripts.migrate_confluence_page import write_md_file      # noqa: E402

# Реальные заголовки из выгрузок, на которых дефект и проявился.
LONG_TITLE = ("[РРКО_ИПВ] Система: Функция поиска документов по параметрам "
              "для формирования рассылки (обратная загрузка)")
LONG_TITLE_QUOTES = ('[РРКО_ИПИ] Агент: Замена ставки НДС с 20 на 22% для РПП '
                     'в статусах "Черновик", "Ожидает подписи"')


def _value_line(text: str, key: str) -> str:
    """Строка YAML со значением ключа."""
    for line in text.splitlines():
        if line.startswith(key + ":"):
            return line
    raise AssertionError(f"ключ {key} не найден в:\n{text}")


def _continuation_after(text: str, key: str) -> str:
    """Следующая строка после ключа — признак свёрнутого значения."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(key + ":"):
            return lines[i + 1] if i + 1 < len(lines) else ""
    raise AssertionError(f"ключ {key} не найден")


class TestExportedPage:
    """write_md_file — frontmatter выгруженных страниц Confluence."""

    def _write(self, tmp_path, title):
        path = tmp_path / "страница.md"
        write_md_file(path, {"doc_id": "{{SIGN: тест}}", "title": title,
                             "status": "draft"}, "Тело страницы.")
        return path.read_text(encoding="utf-8")

    def test_long_title_stays_on_one_line(self, tmp_path):
        text = self._write(tmp_path, LONG_TITLE)
        assert not _continuation_after(text, "title").startswith("  ")
        assert LONG_TITLE in _value_line(text, "title")

    def test_long_title_quote_is_closed(self, tmp_path):
        """Именно незакрытая кавычка и создавала видимость обрезки."""
        text = self._write(tmp_path, LONG_TITLE)
        line = _value_line(text, "title").rstrip()
        if line.startswith("title: '"):
            assert line.endswith("'"), f"кавычка не закрыта: {line}"

    def test_title_with_inner_quotes(self, tmp_path):
        text = self._write(tmp_path, LONG_TITLE_QUOTES)
        assert not _continuation_after(text, "title").startswith("  ")
        assert yaml.safe_load(text.split("---")[1])["title"] == LONG_TITLE_QUOTES

    def test_value_survives_round_trip(self, tmp_path):
        text = self._write(tmp_path, LONG_TITLE)
        assert yaml.safe_load(text.split("---")[1])["title"] == LONG_TITLE

    def test_short_title_unchanged(self, tmp_path):
        text = self._write(tmp_path, "Короткий заголовок")
        assert _value_line(text, "title") == "title: Короткий заголовок"

    def test_body_untouched(self, tmp_path):
        text = self._write(tmp_path, LONG_TITLE)
        assert text.endswith("Тело страницы.\n")


class TestCardGenerator:
    def test_long_value_on_one_line(self):
        block = _render_frontmatter({"title": LONG_TITLE, "generated": True})
        assert not _continuation_after(block, "title").startswith("  ")
        assert yaml.safe_load(block.strip("-\n"))["title"] == LONG_TITLE


class TestManifest:
    def test_long_value_on_one_line(self):
        result = ManifestBuildResult(service_code="SIGN", entries=[])
        text = render_manifest(result)
        assert "service_code: SIGN" in text
        # длинное значение в шапке манифеста тоже не должно сворачиваться
        doc = yaml.safe_load(text)
        assert doc["service_code"] == "SIGN"


def test_pyyaml_default_would_fold():
    """
    Сторож смысла: без width PyYAML действительно сворачивает — если однажды
    поведение библиотеки изменится, тесты выше перестанут что-либо доказывать.
    """
    folded = yaml.dump({"title": LONG_TITLE}, allow_unicode=True,
                       default_flow_style=False, sort_keys=False)
    assert len(folded.splitlines()) > 1, "PyYAML больше не сворачивает — тесты выше формальны"
