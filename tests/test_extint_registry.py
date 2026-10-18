# tests/test_extint_registry.py
"""extint_registry --check (срез С3.1, решение Д-44): реестры docs-external-contracts —
README папок АС, корневой реестр систем, поля шапки карточек, адреса потребителей."""
from pathlib import Path

from app.scripts.CI import extint_registry as er

HEAD = "https://gitlab.gboteam.ru/EAN/docs-svc/-/blob/HEAD/srs/contract-call/external/call-ext-001-x.md"


def w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def card(i: str, title: str = "Операция", kind: str = "operation", channel: str = "rest",
         sync: str = "sync", consumer: str = HEAD, extra_fm: str = "") -> str:
    fm = f"id: {i}\ntitle: '{title}'\ntype: external-integration\n"
    fm += f"kind: {kind}\n" if kind else ""
    fm += f"channel: {channel}\n" if channel else ""
    fm += f"sync: {sync}\n" if sync else ""
    return (f"---\n{fm}{extra_fm}---\n\n# {i}. {title}\n\n## 1. Краткое описание\n\nТекст.\n\n"
            "## Потребители\n\n| Сервис (`code` каталога) | Локальный ID | Карточка вызова |\n|---|---|---|\n"
            f"| svc | CALL-EXT-001 | [CALL-EXT-001. Вызов]({consumer}) |\n")


def readme(as_code: str, ops: list, formats: list = ()) -> str:
    out = (f"---\nid: EXTINT-{as_code}-000\ntitle: 'АС — базовые контракты внешней АС'\n"
           "type: external-integration-registry\n---\n\n# Заголовок\n\nНазначение.\n\n"
           "## О системе\n\n| Поле | Значение |\n|---|---|\n| Система | АС |\n\n"
           "## Операции\n\n| ID | Название | Канал | Синхронность | Карточка |\n|---|---|---|---|---|\n")
    out += "".join(f"| {i} | {t} | {ch} | {s} | [{f}]({f}) |\n" for i, t, ch, s, f in ops)
    if formats:
        out += "\n## Форматы сообщений\n\n| ID | Название | Канал | Карточка |\n|---|---|---|---|\n"
        out += "".join(f"| {i} | {t} | {ch} | [{f}]({f}) |\n" for i, t, ch, f in formats)
    return out


def root(rows: list) -> str:
    return ("# Внешние интеграции\n\n## Реестр систем\n\n| Система | Папка | README | Карточек |\n"
            "|---|---|---|---|\n" + "".join(f"| {s} | [`{p}/`]({p}/) | [README]({p}/README.md) | {n} |\n"
                                             for s, p, n in rows))


def clean_repo(tmp_path: Path) -> Path:
    """Чистая папка АС: две операции и формат, README и корневой реестр по шаблону."""
    repo = tmp_path / "repo"
    w(repo / "abc/extint-abc-001-op.md", card("EXTINT-ABC-001", "Операция один"))
    w(repo / "abc/extint-abc-002-op.md", card("EXTINT-ABC-002", "Операция два", channel="suv", sync="async"))
    w(repo / "abc/extint-abc-003-fmt.md", card("EXTINT-ABC-003", "Формат", kind="format", channel="kafka", sync=""))
    w(repo / "abc/README.md", readme("ABC", [
        ("EXTINT-ABC-002", "Операция два", "СУВ", "async", "extint-abc-002-op.md"),
        ("EXTINT-ABC-001", "Операция один", "REST", "sync", "extint-abc-001-op.md")],
        [("EXTINT-ABC-003", "Формат", "Kafka/СИП", "extint-abc-003-fmt.md")]))
    w(repo / "README.md", root([("АС АБЦ", "abc", 3)]))
    return repo


def text(repo: Path) -> str:
    lines, _bad = er.check(repo, limit=0)
    return "\n".join(lines)


# ---------------------------------------------------------------- несрабатывание

def test_clean_folder_silent(tmp_path):
    lines, bad = er.check(clean_repo(tmp_path), limit=0)
    assert not bad, lines
    assert lines[-2] == "✓ реестры и шапки карточек сходятся", lines


def test_format_without_sync_silent(tmp_path):
    t = text(clean_repo(tmp_path))
    assert "sync" not in t, t


def test_channel_subdirectory_with_own_readme_silent(tmp_path):
    """Криптомодуль: карточки в подкаталоге канала, README канала по шаблону, README
    папки АС ручной и ссылается на README канала."""
    repo = clean_repo(tmp_path)
    w(repo / "cm/http/extint-cm-001-sign.md", card("EXTINT-CM-001", "Подпись"))
    w(repo / "cm/http/README.md", readme("CM", [("EXTINT-CM-001", "Подпись", "REST", "sync",
                                                 "extint-cm-001-sign.md")]))
    w(repo / "cm/README.md", "# Криптомодуль\n\nКаналы: [HTTP](http/README.md).\n")
    w(repo / "README.md", root([("АС АБЦ", "abc", 3), ("Криптомодуль", "cm", 1)]))
    lines, bad = er.check(repo, limit=0)
    assert not bad, lines


# ---------------------------------------------------------------- срабатывание

def test_duplicate_id(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "abc/extint-abc-001-other.md", card("EXTINT-ABC-001", "Другая"))
    t = text(repo)
    assert "дубль id" in t and "extint-abc-001-op.md, abc/extint-abc-001-other.md" in t, t


def test_id_differs_from_file_name(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "abc/extint-abc-001-op.md", card("EXTINT-ABC-009", "Операция один"))
    t = text(repo)
    assert "id EXTINT-ABC-009, по имени файла и папке — EXTINT-ABC-001" in t, t


def test_channel_outside_dictionary(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "abc/extint-abc-001-op.md", card("EXTINT-ABC-001", "Операция один", channel="soap"))
    t = text(repo)
    assert "значение вне словаря шаблона" in t and "abc/extint-abc-001-op.md: soap" in t, t
    assert "канал в README «REST», в карточке «—»" in t, t


def test_no_readme(tmp_path):
    repo = clean_repo(tmp_path)
    (repo / "abc/README.md").unlink()
    t = text(repo)
    assert "нет README.md каталога карточек ×1" in t and "abc/ (карточек 3)" in t, t


def test_readme_row_without_file(tmp_path):
    repo = clean_repo(tmp_path)
    (repo / "abc/extint-abc-002-op.md").unlink()
    w(repo / "README.md", root([("АС АБЦ", "abc", 2)]))
    t = text(repo)
    assert "строка README без файла" in t and "EXTINT-ABC-002 → extint-abc-002-op.md" in t, t


def test_consumer_address_on_master(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "abc/extint-abc-001-op.md", card("EXTINT-ABC-001", "Операция один",
                                              consumer=HEAD.replace("/HEAD/", "/master/")))
    t = text(repo)
    assert "не на /-/blob/HEAD/" in t and "abc/extint-abc-001-op.md: /-/blob/master/ ×1" in t, t


def test_conflict_marker(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "README.md", root([("АС АБЦ", "abc", 3)]) + "<<<<<<< HEAD\nстрока\n=======\nдругая\n>>>>>>> ветка\n")
    lines, bad = er.check(repo, limit=0)
    t = "\n".join(lines)
    assert bad and "✗ маркер конфликта слияния ×2" in t, t


def test_broken_frontmatter(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "abc/extint-abc-001-op.md", "---\nid: EXTINT-ABC-001\ntitle: 'Без закрытия'\n\n# Текст\n")
    t = text(repo)
    assert "✗ шапка карточки не закрыта или отсутствует" in t and "abc/extint-abc-001-op.md" in t, t


# ---------------------------------------------------------------- случаи живого прогона

def test_link_text_with_brackets_and_bare_url_are_read(tmp_path):
    """Ссылка «[CALL-EXT-001. [КК] …](…)» и голый URL в ячейке — адреса видны."""
    repo = clean_repo(tmp_path)
    c = card("EXTINT-ABC-001", "Операция один").replace(
        f"[CALL-EXT-001. Вызов]({HEAD})", "[CALL-EXT-001. [КК] Вызов](" + HEAD.replace("/HEAD/", "/trunk/") + ")")
    c += "| svc2 | CALL-EXT-002 | " + HEAD.replace("/HEAD/", "/master/") + " |\n"
    w(repo / "abc/extint-abc-001-op.md", c)
    t = text(repo)
    assert "abc/extint-abc-001-op.md: /-/blob/master/ ×1, /-/blob/trunk/ ×1" in t, t


def test_readme_not_by_template_single_line_no_table_checks(tmp_path):
    """README не по шаблону — одна строка, построчная сверка не выполняется."""
    repo = clean_repo(tmp_path)
    w(repo / "abc/README.md", "# АС АБЦ\n\n| Карточка | Описание |\n|---|---|\n| x | y |\n")
    t = text(repo)
    assert "README не по шаблону" in t and "abc/README.md" in t, t
    assert "карточки нет в таблицах README" not in t, t


# ---------------------------------------------------------------- --write (С3.2)

def test_write_keeps_manual_sections_and_adds_missing_card(tmp_path):
    """Несрабатывание по ручному: «О системе», текст раздела и «Примеры обмена» — байт в байт."""
    repo = clean_repo(tmp_path)
    rd = repo / "abc/README.md"
    t = rd.read_text(encoding="utf-8").replace(
        "| Система | АС |", "| Система | АС АБЦ, владелец — банк |\n| Каналы | REST и СУВ |").replace(
        "## Операции\n\n", "## Операции\n\nРучной абзац раздела.\n\n") + "\n## Примеры обмена\n\nРучной текст.\n"
    rd.write_text(t, encoding="utf-8")
    w(repo / "abc/extint-abc-004-new.md", card("EXTINT-ABC-004", "Новая операция", channel="mq"))
    w(repo / "README.md", root([("АС АБЦ", "abc", 4)]))
    report, code = er.write(repo)
    assert code == 0, report
    new = rd.read_text(encoding="utf-8")
    for keep in ("| Система | АС АБЦ, владелец — банк |", "| Каналы | REST и СУВ |", "Ручной абзац раздела.",
                 "## Примеры обмена\n\nРучной текст.", "Назначение."):
        assert keep in new, keep
    assert "EXTINT-ABC-004" in new and "| MQ " in new, new
    lines, bad = er.check(repo, limit=0)
    assert not bad, lines


def test_write_orders_by_channel_then_number_and_is_idempotent(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "abc/extint-abc-005-dup.md", card("EXTINT-ABC-001", "Дубль", channel="rest"))
    w(repo / "README.md", root([("АС АБЦ", "abc", 4)]))
    report, code = er.write(repo)
    assert code == 0, report
    ops = (repo / "abc/README.md").read_text(encoding="utf-8").split("## Операции")[1].split("## Форматы")[0]
    ids = [ln.split("|")[1].strip() for ln in ops.splitlines() if ln.startswith("| EXTINT")]
    assert ids == ["EXTINT-ABC-002", "EXTINT-ABC-001", "EXTINT-ABC-001"], ids   # СУВ раньше REST; дубль — обе
    rd = repo / "abc/README.md"
    before, mtime = rd.read_bytes(), rd.stat().st_mtime_ns
    report, code = er.write(repo)
    assert code == 0 and "не перезаписаны" in report[-1], report
    assert rd.read_bytes() == before and rd.stat().st_mtime_ns == mtime


def test_write_creates_readme_by_template(tmp_path):
    repo = clean_repo(tmp_path)
    (repo / "abc/README.md").unlink()
    (repo / "abc/examples").mkdir()
    report, code = er.write(repo)
    assert code == 0 and "создано по шаблону ×1" in "\n".join(report), report
    new = (repo / "abc/README.md").read_text(encoding="utf-8")
    assert new.startswith("---\nid: EXTINT-ABC-000\ntitle: 'АС АБЦ — базовые контракты внешней АС'\n"), new
    assert "Назначение АС: в источниках не задано." in new and "[examples/](examples/)" in new, new
    assert "## Форматы сообщений" in new and "Вложения" not in new, new
    lines, bad = er.check(repo, limit=0)
    assert not bad, lines


def test_write_refuses_readme_not_by_template_and_row_without_file(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "xyz/extint-xyz-001-op.md", card("EXTINT-XYZ-001", "Операция"))
    w(repo / "xyz/README.md", "# XYZ\n\n| Карточка | Описание |\n|---|---|\n| x | y |\n")
    (repo / "abc/extint-abc-002-op.md").unlink()
    before_x, before_a = (repo / "xyz/README.md").read_bytes(), (repo / "abc/README.md").read_bytes()
    report, code = er.write(repo)
    t = "\n".join(report)
    assert code == 2 and "xyz/README.md: README не по шаблону" in t, t
    assert "abc/README.md: строка «Операции» без файла: EXTINT-ABC-002" in t, t
    assert (repo / "xyz/README.md").read_bytes() == before_x
    assert (repo / "abc/README.md").read_bytes() == before_a


def test_write_refuses_directory_with_card_without_kind(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "abc/extint-abc-004-nokind.md", card("EXTINT-ABC-004", "Без вида", kind=""))
    before = (repo / "abc/README.md").read_bytes()
    report, code = er.write(repo)
    assert code == 2 and "нет kind или вне operation | format ×1: extint-abc-004-nokind.md" in "\n".join(report), report
    assert (repo / "abc/README.md").read_bytes() == before


def test_write_root_registry_counts_and_names_kept(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "README.md", "# Внешние интеграции\n\nВводный текст.\n\n" + root([("Ручное имя АБЦ", "abc", 1)]).split("\n", 2)[2]
      + "\n## Прочее\n\nХвост.\n")
    w(repo / "new/extint-new-001-op.md", card("EXTINT-NEW-001", "Операция"))
    report, code = er.write(repo)
    assert code == 0, report
    t = (repo / "README.md").read_text(encoding="utf-8")
    assert "Вводный текст." in t and "## Прочее\n\nХвост." in t, t
    assert "| Ручное имя АБЦ | [`abc/`](abc/) | [README](abc/README.md) | 3 " in t, t
    assert "[`new/`](new/)" in t and "| 1 " in t.split("[`new/`](new/)")[1].split("\n")[0], t
    lines, bad = er.check(repo, limit=0)
    assert not bad, lines


def test_write_root_without_section_untouched(tmp_path):
    repo = clean_repo(tmp_path)
    w(repo / "README.md", "# Внешние интеграции\n\n## Реестр\n\nстарый реестр карточек\n")
    before = (repo / "README.md").read_bytes()
    report, code = er.write(repo)
    assert code == 0 and "реестр систем не пересобран" in "\n".join(report), report
    assert (repo / "README.md").read_bytes() == before


def test_write_keeps_crlf_and_bom(tmp_path):
    repo = clean_repo(tmp_path)
    rd = repo / "abc/README.md"
    rd.write_bytes(b"\xef\xbb\xbf" + rd.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
    w(repo / "abc/extint-abc-004-new.md", card("EXTINT-ABC-004", "Новая", channel="file"))
    w(repo / "README.md", root([("АС АБЦ", "abc", 4)]))
    report, code = er.write(repo)
    assert code == 0, report
    b = rd.read_bytes()
    assert b.startswith(b"\xef\xbb\xbf") and b.count(b"\n") == b.count(b"\r\n"), b[:80]
