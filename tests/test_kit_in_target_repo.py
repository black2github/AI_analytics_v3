# tests/test_kit_in_target_repo.py
"""Комплект команды в целевом репозитории домена (постановка прибору 2026-11-15, вариант Б′):
комплект прогона определяется по объявлениям, а не по именам каталогов клона. Путь строки
«комплект <путь>» профиля источников — `<имя целевого репозитория>/<каталог комплекта команды>`
(шаблон sources-readme.md); в целевом имя — поле name манифеста корня домена, каталог — строка
таблицы «Комплекты команд» README домена.

Инварианты:
1. в исходном репозитории — прежнее определение (строка профиля предка), числа не меняются;
2. в целевом с выгрузкой из src — тот же вердикт, что в src: «страница → свой комплект» без ✗,
   зоны частей сверяются (раньше молча пропускались), покрытие не перевёрнуто;
3. домен с двумя комплектами команд: каждый каталог — в свой комплект, страница комплекта А в
   каталоге Б — ✗;
4. пара не нашлась (нет манифеста, name не объявлен) — ⚠ с обеими половинами, прогон основной,
   прежние ✗ остаются;
5. основной комплект в своём репозитории документации (не в домене) — без изменений;
6. гейт: режим репозитория документации и в форме `--src <клон> --docs <каталог>` (каталог —
   строка таблицы домена, матрица в нём); комплект прогона — по объявлениям при --sources.
"""
import json
import sys
from pathlib import Path

from app.scripts.CI import selfcheck as sc
from app.scripts.CI import source_coverage as cov
from app.scripts.CI.kitcheck.checks import source_profile as sp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "scripts" / "CI"))
import transfer_gate as tg  # noqa: E402

REPO = "docs-f1"          # name манифеста целевого
KIT = f"{REPO}/bc"        # путь строки «комплект …» профиля
KIT2 = f"{REPO}/xx"


def make(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def source(title: str, pid: str) -> str:
    return f"---\ntitle: '{title}'\nconfluence_page_id: '{pid}'\n---\n\nтекст\n"


def card(cid: str, pids: str) -> str:
    return (f"---\nid: {cid}\ntitle: 'К'\ntype: function\nconfluence_page_ids: [{pids}]\n---\n\n"
            f"# {cid}. К\n\nт\n")


def profile(rows: str) -> str:
    return ("# Профиль источников\n\n## Разметка подсервисов\n\n"
            "| Матчер (тег или ветвь) | Зона |\n|---|---|\n" + rows + "\n## Прочее\n")


ROWS = (f"| 900002 | комплект {KIT} |\n"
        f"| 900003 | комплект {KIT2} |\n")

MATRIX = "# Матрица трассировки\n\n| FROM | TO |\n|---|---|\n"


def src_repo(tmp_path: Path, rows: str = ROWS) -> Path:
    """Исходный репозиторий: 900001 — основной комплект, 900002 — комплект bc, 900003 — xx."""
    root = tmp_path / "src-x"
    (root / ".git").mkdir(parents=True)
    make(root / "README.md", profile(rows))
    conf = root / "sources" / "confluence"
    make(conf / "kk" / "p1.md", source("Функция", "900001"))
    make(conf / "kk" / "p2.md", source("Метод адаптера", "900002"))
    make(conf / "kk" / "p3.md", source("Другой метод", "900003"))
    make(root / "docs" / "srs" / "function" / "fun-1.md", card("FUN-1", "900001"))
    make(root / KIT / "srs" / "calls" / "call-1.md", card("CALL-EXT-001", "900002"))
    return root


def domain(tmp_path: Path, name=REPO, kits=("bc",), manifest=True) -> Path:
    """Клон целевого репозитория домена. Папка клона названа иначе, чем репозиторий: имя
    берётся из манифеста, не из папки."""
    root = tmp_path / "clone-any-name"
    (root / ".git").mkdir(parents=True)
    rows = "".join(f"| `{k}` | {k.upper()} | Комплект {k} | `{k}/README.md` |\n" for k in kits)
    make(root / "README.md", "# Домен\n\n## Комплекты команд\n\n"
         "| service-id | Слот | Название | Вход |\n|---|---|---|---|\n" + rows + "\nтекст\n")
    if manifest:
        make(root / "gpb-manifest.json",
             json.dumps({"name": name} if name is not None else {"title": "x"}))
    for k in kits:
        make(root / k / "traceability-matrix.md", MATRIX)
    make(root / "bc" / "srs" / "calls" / "call-1.md", card("CALL-EXT-001", "900002"))
    return root


def conf(src: Path) -> Path:
    return src / "sources" / "confluence"


# ---------------------------------------------------------------- определение комплекта

def test_kit_of_run_in_source_repo_unchanged(tmp_path):
    src = src_repo(tmp_path)
    assert sp.kit_of_run(src / KIT, conf(src)) == (KIT, None)
    assert sp.kit_of_run(src / "docs", conf(src)) == ("", None)


def test_kit_of_run_in_target_by_declarations(tmp_path):
    src = src_repo(tmp_path)
    tgt = domain(tmp_path)
    kit, note = sp.kit_of_run(tgt / "bc", conf(src))
    assert kit == KIT
    assert note.startswith(f"i комплект прогона {KIT}/ — по объявлениям целевого: name «{REPO}»")
    assert "каталог «bc» таблицы «Комплекты команд»" in note


def test_kit_of_run_without_sources_or_kit_rows_silent(tmp_path):
    tgt = domain(tmp_path)
    assert sp.kit_of_run(tgt / "bc", None) == ("", None)
    src = src_repo(tmp_path, rows="| 900001 | подсервис a |\n")
    assert sp.kit_of_run(tgt / "bc", conf(src)) == ("", None)


def test_no_manifest_warns_names_both_halves(tmp_path):
    src = src_repo(tmp_path)
    tgt = domain(tmp_path, manifest=False)
    kit, note = sp.kit_of_run(tgt / "bc", conf(src))
    assert kit == ""
    assert note == ("⚠ комплект прогона по объявлению не определён: каталог «bc» есть в таблице "
                    "«Комплекты команд», имя репозитория — gpb-manifest.json в корне домена нет; "
                    f"объявлены: {KIT}, {KIT2}; прогон считается основным")


def test_manifest_without_name_warns(tmp_path):
    src = src_repo(tmp_path)
    tgt = domain(tmp_path, name=None)
    kit, note = sp.kit_of_run(tgt / "bc", conf(src))
    assert kit == "" and "в gpb-manifest.json корня домена нет поля name" in note


def test_manifest_name_not_declared_warns_and_old_behaviour(tmp_path):
    src = src_repo(tmp_path)
    tgt = domain(tmp_path, name="docs-other")
    kit, note = sp.kit_of_run(tgt / "bc", conf(src))
    assert kit == ""
    assert ("путь «docs-other/bc» (name «docs-other» манифеста корня домена + каталог «bc» "
            "таблицы «Комплекты команд») не объявлен строкой «комплект …» профиля источников") in note
    report, _ok = sc.run(tgt / "bc", conf(src))
    assert note in report
    # прежнее поведение: прогон основной, карточка комплекта bc — ✗
    assert any(ln.startswith("✗ разметка комплекта: основной docs/srs/calls/call-1.md")
               for ln in report), report


def test_main_kit_docs_repo_not_in_domain_unchanged(tmp_path):
    # основной комплект в своём репозитории документации: домена нет — определение прежнее
    src = src_repo(tmp_path)
    main = tmp_path / "docs-main"
    (main / ".git").mkdir(parents=True)
    make(main / "traceability-matrix.md", MATRIX)
    make(main / "gpb-manifest.json", json.dumps({"name": "docs-main"}))
    make(main / "srs" / "function" / "fun-1.md", card("FUN-1", "900001"))
    assert sp.kit_of_run(main, conf(src)) == ("", None)
    report, _ok = sc.run(main, conf(src))
    assert not any("комплект прогона" in ln or "✗ разметка комплекта" in ln for ln in report), report


def test_kit_dir_not_in_domain_table_silent(tmp_path):
    src = src_repo(tmp_path)
    tgt = domain(tmp_path)
    make(tgt / "zz" / "srs" / "x.md", card("FUN-9", "900001"))
    assert sp.kit_of_run(tgt / "zz", conf(src)) == ("", None)


# ---------------------------------------------------------------- selfcheck в целевом

def test_selfcheck_target_same_verdict_as_source(tmp_path):
    src = src_repo(tmp_path)
    tgt = domain(tmp_path)
    rep_src, _ = sc.run(src / KIT, conf(src))
    rep_tgt, _ = sc.run(tgt / "bc", conf(src))
    for rep in (rep_src, rep_tgt):
        assert not any("✗ разметка комплекта" in ln for ln in rep), rep
        assert any(f"прогон: {KIT}/" in ln for ln in rep), rep
    assert any(ln.startswith(f"i комплект прогона {KIT}/") for ln in rep_tgt)
    assert not any("комплект прогона" in ln for ln in rep_src)


def test_two_team_kits_in_domain(tmp_path):
    src = src_repo(tmp_path)
    tgt = domain(tmp_path, kits=("bc", "xx"))
    assert sp.kit_of_run(tgt / "xx", conf(src))[0] == KIT2
    # страница комплекта bc в каталоге xx — ✗ по-прежнему
    make(tgt / "xx" / "srs" / "calls" / "call-2.md", card("CALL-EXT-002", "900002"))
    make(tgt / "xx" / "srs" / "calls" / "call-3.md", card("CALL-EXT-003", "900003"))
    report, _ok = sc.run(tgt / "xx", conf(src))
    bad = [ln for ln in report if ln.startswith("✗ разметка комплекта")]
    assert bad == [f"✗ разметка комплекта: {KIT2}/srs/calls/call-2.md — источник «Метод адаптера» "
                   f"размечен в комплект {KIT}/, карточка лежит в комплекте {KIT2}/ (профиль "
                   "источников: страница → свой комплект; карточку перенести в свой комплект)"], report
    report, _ok = sc.run(tgt / "bc", conf(src))
    assert not any(ln.startswith("✗ разметка комплекта") for ln in report), report


def test_subservice_zone_checked_in_target_after_detection(tmp_path):
    # раньше в целевом прогон считался основным и зоны частей страниц комплекта молча не
    # сверялись; теперь сверяются — срабатывание
    rows = f"| 900002 | комплект {KIT}, подсервис bc-a |\n"
    src = src_repo(tmp_path, rows=rows)
    tgt = domain(tmp_path)
    cards = {"900002": tgt / "bc" / "srs" / "calls" / "call-1.md"}
    rep, ok = sp.check_subservice_mapping(tgt / "bc", conf(src), cards, None)
    assert ok, rep          # прежнее поведение: страница «другого» комплекта пропущена
    report, _ok = sc.run(tgt / "bc", conf(src))
    assert any(ln.startswith("✗ разметка: srs/calls/call-1.md") and "подсервис «bc-a»" in ln
               for ln in report), report


def test_coverage_in_target_not_inverted_and_uses_explicit_inventory(tmp_path):
    src = src_repo(tmp_path)
    tgt = domain(tmp_path)
    lines, _b = cov.coverage_report(conf(src), tgt / "bc")
    assert lines[0] == ("страниц выгрузки: 3; покрыто артефактами: 1; другой комплект: 1; "
                        "НЕ покрыто: 1")
    inv = make(src / "inventory.md", "# Опись\n")
    report, _ok = sc.run(tgt / "bc", conf(src), inventory=inv)
    assert not any("опись не найдена" in ln for ln in report), report


# ---------------------------------------------------------------- гейт

def test_detect_layout_domain_kit_forms(tmp_path):
    tgt = domain(tmp_path)
    assert tg.detect_layout(tgt / "bc", "docs") == (tgt / "bc", True)
    assert tg.detect_layout(tgt, "bc") == (tgt / "bc", True)
    # каталог не из таблицы домена — рабочий режим, как прежде
    make(tgt / "zz" / "traceability-matrix.md", MATRIX)
    assert tg.detect_layout(tgt, "zz") == (tgt / "zz", False)
    # рабочий репозиторий: docs/ без домена — как прежде
    src = src_repo(tmp_path)
    assert tg.detect_layout(src, "docs") == (src / "docs", False)


def test_gate_target_both_forms_ready_same_kit(tmp_path):
    src = src_repo(tmp_path)
    tgt = domain(tmp_path)
    for kw in ({"src_root": tgt / "bc"}, {"src_root": tgt, "docs_name": "bc"}):
        lines, _ready, data = tg.run_gate(sources=conf(src), no_validator=True, **kw)
        text = "\n".join(lines)
        assert data.get("docs_repo") is True or "репозиторий документации" in text, text
        assert "разметка комплекта: основной" not in text, text
        assert f"комплект прогона {KIT}/ — по объявлениям целевого" in text, text
        assert "журнал open-questions.md не найден" not in text, text


def test_gate_target_unmatched_warns_keeps_errors(tmp_path):
    src = src_repo(tmp_path)
    tgt = domain(tmp_path, name="docs-other")
    lines, ready, _data = tg.run_gate(tgt / "bc", sources=conf(src), no_validator=True)
    text = "\n".join(lines)
    assert "комплект прогона по объявлению не определён" in text, text
    assert "разметка комплекта: основной docs/srs/calls/call-1.md" in text, text
    assert not ready


def test_gate_source_second_kit_unchanged(tmp_path):
    src = src_repo(tmp_path)
    make(src / "inventory.md", "# Опись\n")
    lines, _ready, _data = tg.run_gate(src, docs_name=KIT, no_validator=True)
    text = "\n".join(lines)
    assert f"комплект {KIT}/ объявлен в профиле источников" in text, text
    assert "комплект прогона" not in text and "разметка комплекта: основной" not in text, text
