# tests/test_source_inventory.py
"""Механическая опись выгрузки (У-1): полноту гарантирует генерация,
--check ловит потерю строк, лишние строки и правку скриптовых колонок."""

from pathlib import Path

from app.scripts.CI.source_inventory import build, check, scan


def make_page(root: Path, name: str, pid: str, title: str,
              rtype: str = "function") -> Path:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\ntitle: '{title}'\nrequirement_type: {rtype}\n"
        f"confluence_page_id: '{pid}'\n---\n\nтело\n", encoding="utf-8")
    return p


def setup_src(tmp_path: Path) -> Path:
    src = tmp_path / "confluence"
    make_page(src, "Функции/f1.md", "111", "[Т] Функция один")
    make_page(src, "Функции/f2.md", "222", "[Т] Функция два", "unknown")
    (src / "index.md").parent.mkdir(parents=True, exist_ok=True)
    (src / "index.md").write_text("# nav\n", encoding="utf-8")
    return src


def test_skeleton_rows_and_index_excluded(tmp_path):
    src = setup_src(tmp_path)
    rows, n_index = scan(src)
    assert len(rows) == 2 and n_index == 1
    lines = build(src)
    assert any("| 111 |" in ln for ln in lines)
    assert any("ИТОГО: страниц 2; навигационных index.md 1" in ln
               for ln in lines)


def test_page_without_frontmatter_not_lost(tmp_path):
    # асимметрия: файл без frontmatter — строка с «—», не пропуск
    src = setup_src(tmp_path)
    (src / "голый.md").write_text("текст без frontmatter\n",
                                  encoding="utf-8")
    rows, _ = scan(src)
    assert len(rows) == 3
    assert any(r["page_id"] == "—" and r["title"] == "голый"
               for r in rows)


def test_check_ok_after_llm_fill(tmp_path):
    src = setup_src(tmp_path)
    inv = tmp_path / "inventory.md"
    inv.write_text("\n".join(build(src)) + "\n", encoding="utf-8")
    # LLM заполняет свои колонки (последние две) — это легально
    lines = inv.read_text(encoding="utf-8").splitlines()
    filled = False
    for i, ln in enumerate(lines):
        if "| 222 |" in ln:
            assert ln.rstrip().endswith("|  |  |")
            lines[i] = ln.rstrip()[:-len("|  |  |")] + \
                "| function | прочитано: эндпоинта нет, библиотечная |"
            filled = True
    assert filled
    inv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report, ok = check(src, inv)
    assert ok, report
    assert any("вердикт: OK" in ln and "без гипотезы 1" in ln
               for ln in report)


def test_check_catches_lost_row(tmp_path):
    src = setup_src(tmp_path)
    inv = tmp_path / "inventory.md"
    lines = [ln for ln in build(src) if "| 222 |" not in ln]
    inv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report, ok = check(src, inv)
    assert not ok and any("ПОТЕРЯНЫ" in ln and "222" in ln
                          for ln in report)


def test_check_catches_script_column_edit(tmp_path):
    # анти-подгонка: правка титула/req_type в описи — брак
    src = setup_src(tmp_path)
    inv = tmp_path / "inventory.md"
    text = "\n".join(build(src)) + "\n"
    inv.write_text(text.replace("[Т] Функция два", "[Т] Функция 2"),
                   encoding="utf-8")
    report, ok = check(src, inv)
    assert not ok and any("ИЗМЕНЕНЫ скриптовые" in ln for ln in report)


def test_yaml_folded_title_joined(tmp_path):
    # легальный YAML-перенос длинного title (экспортёр переносит по
    # стандарту) — склеивается в полный титул, маркера нет
    src = setup_src(tmp_path)
    p = src / "Функции" / "folded.md"
    p.write_text(
        "---\ntitle: '[Т] Очень длинный титул переносимый по стандарту\n"
        "  YAML с продолжением на второй строке v.2.1'\n"
        "requirement_type: function\nconfluence_page_id: '333'\n---\n\n"
        "тело\n", encoding="utf-8")
    rows, _ = scan(src)
    r = next(r for r in rows if r["page_id"] == "333")
    assert r["title"].endswith("v.2.1")
    assert "⋯" not in r["title"]


def test_truncated_title_marked(tmp_path):
    # титул, у которого продолжение так и не закрыло кавычку, — маркер
    # «⋯» и счётчик в ИТОГО
    src = setup_src(tmp_path)
    p = src / "Функции" / "cut.md"
    p.write_text(
        "---\ntitle: '[Т] Очень длинный обрезанный титул без хвоста\n"
        "requirement_type: function\nconfluence_page_id: '334'\n---\n\n"
        "тело\n", encoding="utf-8")
    rows, _ = scan(src)
    cut = next(r for r in rows if r["page_id"] == "334")
    assert cut["title"].endswith("⋯")
    lines = build(src)
    assert any("титулов обрезано экспортёром 1" in ln for ln in lines)
    # НЕсрабатывание: нормальные закрытые титулы без маркера
    assert not any(r["title"].endswith("⋯") for r in rows
                   if r["page_id"] in ("111", "222"))


def test_double_space_title_roundtrip_ok(tmp_path):
    # титул с двойным пробелом (реальные источники): ячейка жмёт
    # пробелы — --check не считает это правкой скриптовой колонки
    src = setup_src(tmp_path)
    make_page(src, "Функции/dbl.md", "444", "[Т]  Агенты  источника")
    inv = tmp_path / "inventory.md"
    inv.write_text("\n".join(build(src)) + "\n", encoding="utf-8")
    report, ok = check(src, inv)
    assert ok, report
    assert any("правок скриптовых колонок 0" in ln for ln in report)


def test_refresh_keeps_llm_columns(tmp_path):
    # сканер улучшился после заполнения — refresh обновляет скриптовые
    # колонки, сохраняя работу LLM; --check после него OK
    from app.scripts.CI.source_inventory import refresh
    src = setup_src(tmp_path)
    inv = tmp_path / "inventory.md"
    lines = build(src)
    # эмуляция старого скелета: титул записан с отъеденной кавычкой
    lines = [ln.replace("[Т] Функция один", "[Т] Функция один'")
             if "| 111 |" in ln else ln for ln in lines]
    # LLM заполнила свои колонки
    lines = [ln.rstrip()[:-len("|  |  |")] + "| function | сигналы согласны |"
             if "| 222 |" in ln else ln for ln in lines]
    inv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report, ok = check(src, inv)
    assert not ok  # расхождение титула видно
    out = refresh(src, inv)
    inv.write_text("\n".join(out) + "\n", encoding="utf-8")
    assert any("сохранено 1/2" in ln for ln in out)
    report, ok = check(src, inv)
    assert ok, report
    text = inv.read_text(encoding="utf-8")
    assert "| function | сигналы согласны |" in text


def test_duplicate_page_id_flagged(tmp_path):
    src = setup_src(tmp_path)
    make_page(src, "Функции/f3.md", "111", "[Т] Функция три")
    lines = build(src)
    assert any("дублей page_id 1" in ln for ln in lines)
    assert any(ln.startswith("⚠ дубли page_id") for ln in lines)
