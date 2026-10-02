# tests/test_pick_pages.py
#
# Точечная замена страниц архива страницами из новой полной выгрузки (2026-10-02).
#
# Главное, что закрепляется:
#   • страница переносится по тому же относительному пути, байт в байт, вместе с
#     картинками; страницы не из списка не трогаются;
#   • всё или ничего: не найденный идентификатор, занятый чужой страницей путь,
#     несовмещённые корни — ничего не пишется (молча пропущенная страница означала
#     бы, что ошибочная версия осталась в архиве);
#   • переименованная страница не оставляет в архиве двойника со старым путём;
#   • ссылки разбираются с балансом скобок — имена страниц содержат «(…)».

from pathlib import Path

import pytest

from app.scripts.pick_pages import (ADDED, MOVED, REPLACED, SAME, PickError,
                                    build_plan, link_targets, main, read_ids,
                                    referenced_files)


def _page(root: Path, rel: str, page_id: str, body: str = "текст\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (f"---\ntitle: '{Path(rel).stem}'\nconfluence_page_id: '{page_id}'\n"
            f"status: draft\n---\n\n{body}")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def _stand(tmp_path):
    """Архив (старая выгрузка) и новая полная выгрузка одного дерева."""
    arc, new = tmp_path / "raw", tmp_path / "new"
    for root, tag in ((arc, "старый"), (new, "новый")):
        _page(root, "Сервис.md", "1", f"{tag} корень\n")
        _page(root, "Сервис/А.md", "2", f"{tag} А, см. [Б](Б-(v2).md)\n")
        _page(root, "Сервис/Б-(v2).md", "3", f"{tag} Б\n")
        _page(root, "Сервис/Раздел/В.md", "4",
              f'{tag} В <img src="img/pic.png" alt="x"> и [А](../А.md)\n')
        (root / "Сервис/Раздел/img").mkdir(parents=True, exist_ok=True)
        (root / "Сервис/Раздел/img/pic.png").write_bytes(tag.encode("utf-8"))
    return arc, new


def _ids(tmp_path, text):
    p = tmp_path / "ids.txt"
    p.write_text(text, encoding="utf-8")
    return p


def _snapshot(root: Path):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


class TestParsing:
    def test_ids_file_formats(self, tmp_path):
        p = _ids(tmp_path, "﻿# список\n2, 3\n4  # комментарий\n\n2\n")
        assert read_ids(p) == ["2", "3", "4"]

    def test_non_numeric_id_is_error(self, tmp_path):
        with pytest.raises(PickError):
            read_ids(_ids(tmp_path, "2\nGBO-1\n"))

    def test_empty_list_is_error(self, tmp_path):
        with pytest.raises(PickError):
            read_ids(_ids(tmp_path, "# пусто\n"))

    def test_link_with_parentheses_in_name(self):
        text = "см. [Б](Раздел-(БлокировкаЗакрытие)/Б-(v2).md) и [вне](https://x/y)."
        assert link_targets(text)[0] == "Раздел-(БлокировкаЗакрытие)/Б-(v2).md"

    def test_referenced_files_split_md_and_assets(self):
        text = ('[a](../А.md#якорь) ![p](img/1.png) <img src="img/2.png" alt="x"> '
                '[ext](https://x/y.md) [anc](#раздел) [ph](confluence://123) '
                '[att](/download/attachments/1/f.docx)')
        md, other = referenced_files(text)
        assert md == ["../А.md"]
        assert other == ["img/1.png", "img/2.png"]


class TestTransfer:
    def test_replaces_only_listed_pages_byte_for_byte(self, tmp_path):
        arc, new = _stand(tmp_path)
        before = _snapshot(arc)
        assert main([str(new), str(arc), "--pages", str(_ids(tmp_path, "2\n"))]) == 0
        after = _snapshot(arc)
        assert after["Сервис/А.md"] == (new / "Сервис/А.md").read_bytes()
        untouched = {k: v for k, v in after.items() if k != "Сервис/А.md"}
        assert untouched == {k: v for k, v in before.items() if k != "Сервис/А.md"}

    def test_images_travel_with_the_page(self, tmp_path):
        arc, new = _stand(tmp_path)
        assert main([str(new), str(arc), "--pages", str(_ids(tmp_path, "4\n"))]) == 0
        assert (arc / "Сервис/Раздел/img/pic.png").read_bytes() == "новый".encode("utf-8")

    def test_dry_run_writes_nothing(self, tmp_path):
        arc, new = _stand(tmp_path)
        before = _snapshot(arc)
        assert main([str(new), str(arc), "--pages", str(_ids(tmp_path, "2 4\n")),
                     "--dry-run"]) == 0
        assert _snapshot(arc) == before

    def test_identical_page_is_reported_as_unchanged(self, tmp_path):
        arc, new = _stand(tmp_path)
        (new / "Сервис/Б-(v2).md").write_bytes((arc / "Сервис/Б-(v2).md").read_bytes())
        plan = build_plan(new, arc, ["3"])
        assert plan["pages"][0]["status"] == SAME

    def test_new_page_is_added_with_directories(self, tmp_path):
        arc, new = _stand(tmp_path)
        _page(new, "Сервис/Новый-раздел/Г.md", "5", "новая Г\n")
        plan = build_plan(new, arc, ["5"])
        assert plan["pages"][0]["status"] == ADDED
        assert main([str(new), str(arc), "--pages", str(_ids(tmp_path, "5\n"))]) == 0
        assert (arc / "Сервис/Новый-раздел/Г.md").is_file()

    def test_renamed_page_leaves_no_twin(self, tmp_path):
        arc, new = _stand(tmp_path)
        (new / "Сервис/А.md").unlink()
        _page(new, "Сервис/А-новое-имя.md", "2", "новый А\n")
        plan = build_plan(new, arc, ["2"])
        assert plan["pages"][0]["status"] == MOVED
        assert main([str(new), str(arc), "--pages", str(_ids(tmp_path, "2\n"))]) == 0
        assert (arc / "Сервис/А-новое-имя.md").is_file()
        assert not (arc / "Сервис/А.md").exists()

    def test_report_file(self, tmp_path):
        arc, new = _stand(tmp_path)
        out = tmp_path / "pick.md"
        assert main([str(new), str(arc), "--pages", str(_ids(tmp_path, "2\n")),
                     "--out", str(out)]) == 0
        text = out.read_text(encoding="utf-8")
        assert f"| {REPLACED} | 1 |" in text and "`Сервис/А.md`" in text


class TestAllOrNothing:
    def test_missing_id_stops_everything(self, tmp_path):
        arc, new = _stand(tmp_path)
        before = _snapshot(arc)
        assert main([str(new), str(arc), "--pages", str(_ids(tmp_path, "2 999\n"))]) == 1
        assert _snapshot(arc) == before          # даже найденная страница 2 не записана

    def test_target_path_taken_by_another_page_stops(self, tmp_path):
        arc, new = _stand(tmp_path)
        # в новой выгрузке страница 2 переехала на путь, где в архиве лежит страница 3
        (new / "Сервис/А.md").unlink()
        (new / "Сервис/Б-(v2).md").unlink()
        _page(new, "Сервис/Б-(v2).md", "2", "новый А на месте Б\n")
        before = _snapshot(arc)
        assert main([str(new), str(arc), "--pages", str(_ids(tmp_path, "2\n"))]) == 1
        assert _snapshot(arc) == before

    def test_misaligned_roots_stop(self, tmp_path):
        arc, new = _stand(tmp_path)
        before = _snapshot(arc)
        # архив указан уровнем глубже, чем новая выгрузка
        assert main([str(new), str(arc / "Сервис"), "--pages",
                     str(_ids(tmp_path, "2\n"))]) == 2
        assert _snapshot(arc) == before

    def test_duplicate_id_in_tree_stops(self, tmp_path):
        arc, new = _stand(tmp_path)
        _page(new, "Сервис/Двойник.md", "2", "двойник\n")
        assert main([str(new), str(arc), "--pages", str(_ids(tmp_path, "2\n"))]) == 2

    def test_same_directory_is_usage_error(self, tmp_path):
        arc, _ = _stand(tmp_path)
        assert main([str(arc), str(arc), "--pages", str(_ids(tmp_path, "2\n"))]) == 2


class TestLinkCheck:
    def test_resolved_links_give_no_warning(self, tmp_path):
        arc, new = _stand(tmp_path)
        plan = build_plan(new, arc, ["2", "4"])
        assert plan["warnings"] == [] and plan["errors"] == []

    def test_link_to_file_missing_in_archive_is_warned(self, tmp_path):
        arc, new = _stand(tmp_path)
        # соседняя страница переименована в Confluence: в архиве её нового пути нет
        (new / "Сервис/Б-(v2).md").unlink()
        _page(new, "Сервис/Б-(v3).md", "3", "новый Б\n")
        _page(new, "Сервис/А.md", "2", "новый А, см. [Б](Б-(v3).md)\n")
        plan = build_plan(new, arc, ["2"])
        assert plan["errors"] == []
        assert any("Б-(v3).md" in w for w in plan["warnings"])

    def test_link_to_page_moved_in_same_run_is_fine(self, tmp_path):
        # НЕсрабатывание: цель ссылки переносится тем же запуском
        arc, new = _stand(tmp_path)
        (new / "Сервис/Б-(v2).md").unlink()
        _page(new, "Сервис/Б-(v3).md", "3", "новый Б\n")
        _page(new, "Сервис/А.md", "2", "новый А, см. [Б](Б-(v3).md)\n")
        plan = build_plan(new, arc, ["2", "3"])
        assert plan["warnings"] == []

    def test_new_image_missing_everywhere_is_warned(self, tmp_path):
        arc, new = _stand(tmp_path)
        _page(new, "Сервис/Раздел/В.md", "4", 'новый В <img src="img/новая.png" alt="x">' + chr(10))
        plan = build_plan(new, arc, ["4"])
        assert any("img/новая.png" in w for w in plan["warnings"])

    def test_image_missing_in_new_but_kept_in_archive_is_silent(self, tmp_path):
        # НЕсрабатывание: картинки нет в новой выгрузке, но в архиве она лежит —
        # остаётся как была
        arc, new = _stand(tmp_path)
        (new / "Сервис/Раздел/img/pic.png").unlink()
        plan = build_plan(new, arc, ["4"])
        assert plan["warnings"] == [] and plan["assets"] == []

    def test_links_to_old_path_of_moved_page_are_warned(self, tmp_path):
        # страница 2 переименована; страница 4 архива (не в списке) ссылается на
        # её старый путь ../А.md — после переноса ссылка станет битой
        arc, new = _stand(tmp_path)
        (new / "Сервис/А.md").unlink()
        _page(new, "Сервис/А-новое-имя.md", "2", "новый А\n")
        plan = build_plan(new, arc, ["2"])
        assert any("не перевыгружается" in w and "../А.md" in w
                   for w in plan["warnings"])

    def test_no_such_warning_when_linker_is_reexported_too(self, tmp_path):
        arc, new = _stand(tmp_path)
        (new / "Сервис/А.md").unlink()
        _page(new, "Сервис/А-новое-имя.md", "2", "новый А\n")
        _page(new, "Сервис/Раздел/В.md", "4", "новый В и [А](../А-новое-имя.md)\n")
        plan = build_plan(new, arc, ["2", "4"])
        assert not any("не перевыгружается" in w for w in plan["warnings"])

    def test_preexisting_broken_link_is_not_reported_again(self, tmp_path):
        # НЕсрабатывание: ссылка вела в никуда и до переноса (другой сервис вне
        # архива) — перенос её не менял, шум не нужен
        arc, new = _stand(tmp_path)
        for root, tag in ((arc, "старый"), (new, "новый")):
            _page(root, "Сервис/А.md", "2", tag + " А, см. [ЕСК](../../esk/ЕСК.md)" + chr(10))
        plan = build_plan(new, arc, ["2"])
        assert plan["pages"][0]["status"] == REPLACED and plan["warnings"] == []


class TestExtract:
    """Извлечение: каталога назначения нет или он пуст — страницы из списка
    складываются туда в той же структуре (2026-10-02, исходная задача владельца:
    «забрать файлы с указанными идентификаторами в отдельный каталог»)."""

    def test_extract_into_missing_directory(self, tmp_path, capsys):
        _arc, new = _stand(tmp_path)
        out = tmp_path / "выборка" / "вложенный"
        assert main([str(new), str(out), "--pages", str(_ids(tmp_path, "2 4"))]) == 0
        got = _snapshot(out)
        assert sorted(got) == ["Сервис/А.md", "Сервис/Раздел/img/pic.png",
                               "Сервис/Раздел/В.md"]
        assert got["Сервис/Раздел/В.md"] == (new / "Сервис/Раздел/В.md").read_bytes()
        text = capsys.readouterr().out
        assert "извлечение" in text and "добавлена: 2" in text
        assert "⚠" not in text                    # ссылки на соседей — не шум

    def test_extract_into_empty_directory(self, tmp_path):
        _arc, new = _stand(tmp_path)
        out = tmp_path / "пусто"
        out.mkdir()
        assert main([str(new), str(out), "--pages", str(_ids(tmp_path, "3"))]) == 0
        assert sorted(_snapshot(out)) == ["Сервис/Б-(v2).md"]

    def test_extract_dry_run_creates_nothing(self, tmp_path):
        _arc, new = _stand(tmp_path)
        out = tmp_path / "выборка"
        assert main([str(new), str(out), "--pages", str(_ids(tmp_path, "2")),
                     "--dry-run"]) == 0
        assert not out.exists()

    def test_extract_with_missing_id_creates_nothing(self, tmp_path):
        _arc, new = _stand(tmp_path)
        out = tmp_path / "выборка"
        assert main([str(new), str(out), "--pages", str(_ids(tmp_path, "2 999"))]) == 1
        assert not out.exists()

    def test_source_is_not_modified(self, tmp_path):
        _arc, new = _stand(tmp_path)
        before = _snapshot(new)
        assert main([str(new), str(tmp_path / "выборка"), "--pages",
                     str(_ids(tmp_path, "2 3 4"))]) == 0
        assert _snapshot(new) == before

    def test_extracted_set_then_replaces_pages_in_archive(self, tmp_path):
        # два шага: извлечь набор, затем этим набором заменить страницы архива
        arc, new = _stand(tmp_path)
        out = tmp_path / "выборка"
        assert main([str(new), str(out), "--pages", str(_ids(tmp_path, "2 4"))]) == 0
        assert main([str(out), str(arc), "--pages", str(_ids(tmp_path, "2 4"))]) == 0
        assert (arc / "Сервис/А.md").read_bytes() == (new / "Сервис/А.md").read_bytes()
        assert (arc / "Сервис/Раздел/img/pic.png").read_bytes() == "новый".encode("utf-8")

    def test_destination_that_is_a_file_is_usage_error(self, tmp_path):
        _arc, new = _stand(tmp_path)
        f = tmp_path / "файл.txt"
        f.write_text("x", encoding="utf-8")
        assert main([str(new), str(f), "--pages", str(_ids(tmp_path, "2"))]) == 2
