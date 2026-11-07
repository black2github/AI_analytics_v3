"""Опись выгрузки считает картинки в теле страниц: ссылок, файлов, ссылок без файла
(замечание ОНБ-В 63, 2026-11-07)."""
from pathlib import Path

from app.scripts.CI.source_inventory import build, check, page_images, refresh


def make(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def page(pid: str, title: str, body: str) -> str:
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\n{body}\n"


def test_two_img_one_file(tmp_path):
    src = tmp_path / "confluence"
    p = src / "Раздел" / "Страница.md"
    make(p, page("101", "Страница", '<img src="img/a.png"/> текст <img src="img/b.png"/>'))
    (src / "Раздел" / "img").mkdir(parents=True)
    (src / "Раздел" / "img" / "a.png").write_bytes(b"x")
    assert page_images(p, p.read_text(encoding="utf-8")) == (2, 1, 1)
    out = build(src)
    assert any("ИЗОБРАЖЕНИЯ В ТЕЛЕ СТРАНИЦ: ссылок 2, файлов 1, ссылок без файла 1; "
               "страниц со ссылками 1, из них со ссылками без файла 1" in ln for ln in out)
    line = [ln for ln in out if ln.startswith("i ссылки на изображения без файла:")]
    assert len(line) == 1 and "101 «Страница» — ссылок 2, файлов 1, без файла 1" in line[0]


def test_markdown_and_ac_image_forms(tmp_path):
    src = tmp_path / "confluence"
    p = src / "Стр.md"
    make(p, page("102", "Стр", '![схема](img/s.png)\n<ac:image ac:height="20">'
                 '<ri:attachment ri:filename="icon.png"/></ac:image>\n'
                 '![внешняя](https://example.org/x.png)'))
    (src / "img").mkdir(parents=True)
    (src / "img" / "s.png").write_bytes(b"x")
    (src / "img" / "icon.png").write_bytes(b"x")
    assert page_images(p, p.read_text(encoding="utf-8")) == (3, 2, 1)


def test_page_without_images_not_listed(tmp_path):
    src = tmp_path / "confluence"
    make(src / "Стр.md", page("103", "Стр", "просто текст, ссылка [x](y.md)"))
    out = build(src)
    assert any("ИЗОБРАЖЕНИЯ В ТЕЛЕ СТРАНИЦ: ссылок 0, файлов 0, ссылок без файла 0; "
               "страниц со ссылками 0, из них со ссылками без файла 0" in ln for ln in out)
    assert not any(ln.startswith("i ссылки на изображения без файла") for ln in out)


def test_all_files_present_no_i_line(tmp_path):
    src = tmp_path / "confluence"
    make(src / "Стр.md", page("104", "Стр", '<img src="img/a.png">'))
    (src / "img").mkdir(parents=True)
    (src / "img" / "a.png").write_bytes(b"x")
    out = build(src)
    assert any("ссылок 1, файлов 1, ссылок без файла 0" in ln for ln in out)
    assert not any(ln.startswith("i ссылки на изображения без файла") for ln in out)


def test_old_attachment_line_kept_and_check_refresh_work(tmp_path):
    src = tmp_path / "confluence"
    make(src / "Стр.md", page("105", "Стр", '<img src="img/a.png">'))
    (src / "img").mkdir(parents=True)
    (src / "img" / "a.png").write_bytes(b"x")
    out = build(src)
    assert any("ИТОГО ПРИЛОЖЕНИЙ: файлов 0; изображений 1" in ln for ln in out)
    inv = tmp_path / "inventory.md"
    inv.write_text("\n".join(out) + "\n", encoding="utf-8")
    rep, ok = check(src, inv)
    assert ok, rep
    ref = refresh(src, inv)
    assert any(ln.startswith("ИЗОБРАЖЕНИЯ В ТЕЛЕ СТРАНИЦ") for ln in ref)
