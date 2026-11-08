# app/scripts/CI/extint_registry.py
"""Реестры репозитория базовых контрактов внешних АС (docs-external-contracts):
README папки АС (EXTINT-<AS>-000), корневой реестр систем, поля шапки карточек
(решение Д-44 владельца пилота 2026-10-18; норма — шаблон канона
`_meta/templates/contract-call.md`, раздел A; реестр структурных фактов SF-06).

Режим `--check` (по умолчанию) сверяет и ничего не пишет. Код 0 — расхождений
нет, 1 — есть ⚠ или ✗, 2 — ошибка запуска.

Карточка — файл `extint-*.md` в папке АС или в подкаталоге канала
(`crypto-module/http/`); прочие `.md` (README, инструкции `ins-*`) проверяются
только на маркеры конфликта. Реестр карточек — `README.md` каталога карточки:
папки АС, а у Криптомодуля — подкаталога канала; README папки Криптомодуля —
ручной, от него требуются ссылки на README каждого канала.

Проверки:
- шапка: сломанная (нет закрывающей «---») — ✗; `id`, `title`, `kind`
  (`operation` — вызов | `message` — односторонний обмен | `common` — общее без
  обмена), `channel` из словаря, `sync` (`sync` | `async`) у операций, у
  `message` и `common` `sync` не указывается — ⚠;
- `id` уникален по всем файлам; `id` = `EXTINT-<ПАПКА>-NNN` и совпадает с
  именем файла `extint-<папка>-NNN-<slug>.md` — ⚠;
- название метода (`title`, без него — H1 без ID) уникально в папке АС: общий
  базовый контракт один на метод — ⚠ с перечнем ID;
- README каталога карточек есть; README по шаблону (раздел «## Операции») —
  его таблицы «Операции», «Сообщения и файлы», «Общие форматы и коды» ↔
  карточки: нет строки, строка
  без файла, название (= `title`, без него — H1 карточки без ID), канал, синхронность, таблица
  не по `kind`; README не по шаблону — одна строка, сверка таблиц пропущена
  (перевод — отдельный заход со сверкой фактов);
- корневой README: раздел «## Реестр систем» (`Система | Папка | README |
  Карточек`) ↔ папки АС;
- «Потребители» карточки: раздел есть, три колонки, адреса абсолютные и на
  `/-/blob/HEAD/` (не `master`, `trunk`, рабочая ветка);
- маркеры конфликта (`<<<<<<<`, `>>>>>>>` вне блоков кода) в любом `.md` — ✗;
- содержимое потребителя в базовом контракте (шаблон, раздел A, «Что содержит базовый
  контракт»; решение владельца 2026-11-08): §1 «Где используется» не указатель шаблона,
  §1 «Документация» без ссылки на файл в `files/` папки АС и без внешнего URL вне Confluence,
  подраздел `###` с этими лейблами
  в §1, шаги потребителя в §4 (нотация `**Шаг N.**`), прежний заголовок §4 — ⚠; ячейки
  «Правил заполнения» §2/§3 с «=» в начале или ID/адресом артефакта сервиса — i-строка
  (константу владельца от присвоения потребителя по форме не отличить);
- ID карточек `EXTINT-<AS>-NNN` в ручном разделе «О системе» README папки АС и README канала — ⚠.

Режим `--write` пересобирает выводимые таблицы «Операции», «Сообщения и файлы»,
«Общие форматы и коды» README по шаблону (два последних раздела — только при
карточках `message` / `common`) и раздел «## Реестр систем» корневого README; текст вне этих
таблиц (назначение, «О системе», «Примеры обмена», прочие разделы) — байт в байт;
строки сгруппированы по каналу в порядке словаря, внутри — по номеру, таблицы
выровнены пробелами; дубль ID — обе строки. README каталога без README создаётся
по шаблону: ручные «Назначение» и «О системе» — «в источниках не задано». Отказ
(файл не тронут, код 2) — для README не по шаблону (перевод — отдельным заходом
со сверкой фактов), при строке без файла (снимает человек), при карточке со
сломанной шапкой или без `kind` в каталоге; корневой README без «## Реестр
систем» не трогается (одна строка `i`). EOL и BOM файла сохраняются, запись
атомарная, неизменённый файл не перезаписывается.

Словарь каналов и порядок их в реестрах — шаблон канона, раздел A; здесь копия
для разбора, расширение словаря — правкой шаблона и этой таблицы.

Запуск: python extint_registry.py --repo <клон docs-external-contracts>
"""
import argparse
import os
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from kitcheck.md import code_line_flags, frontmatter_split, table_cells  # noqa: E402
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .kitcheck.md import code_line_flags, frontmatter_split, table_cells  # type: ignore  # noqa: E402

# словарь каналов: значение поля channel → отображение в реестре; порядок — порядок групп
CHANNELS: List[Tuple[str, str]] = [
    ("suv", "СУВ"), ("online-adapter", "онлайн-адаптер"), ("rest", "REST"), ("soap", "SOAP"),
    ("mq", "MQ"), ("otsgds", "ОТСГДС"), ("db", "БД"), ("file", "файл"), ("kafka", "Kafka/СИП"),
    ("postmessage", "PostMessage")]
CHANNEL_TITLE = dict(CHANNELS)
SYNCS = ("sync", "async")
NO_VALUE = "—"

OPS_TITLE = "Операции"
OPS_COLS = ["ID", "Название", "Канал", "Синхронность", "Карточка"]
SIDE_COLS = ["ID", "Название", "Канал", "Карточка"]
# таблицы README АС по kind карточки (шаблон канона, раздел A; решение владельца пилота
# 2026-10-18 вечер: operation — вызов, message — односторонний обмен, common — общее без обмена);
# порядок — порядок разделов README; «Сообщения и файлы» и «Общие форматы и коды» — только при карточках
TABLES: List[Tuple[str, str, List[str], str]] = [
    ("operation", OPS_TITLE, OPS_COLS, ""),
    ("message", "Сообщения и файлы", SIDE_COLS,
     "Односторонний обмен: сообщения по подписке, одна сторона MQ-пары, файлы обмена — ответа в этой\n"
     "карточке нет."),
    ("common", "Общие форматы и коды", SIDE_COLS,
     "Общее для операций АС, обмена нет: типы данных, перечни кодов ошибок."),
]
KINDS = tuple(k for k, _t, _c, _i in TABLES)
TABLE_OF_KIND = {k: t for k, t, _c, _i in TABLES}
ROOT_TITLE = "Реестр систем"
ROOT_COLS = ["Система", "Папка", "README", "Карточек"]
SKIP_DIRS = {"examples", "files", ".git"}

# адрес ссылки — по «](…)»: текст ссылки бывает со скобками («[CALL-EXT-001. [КК] …](…)»)
_TARGET_RE = re.compile(r"\]\(([^)\s]+)\)")
_URL_RE = re.compile(r"https?://[^\s|)\]]+")
_BLOB_RE = re.compile(r"/-/blob/([^/\s)]+)/")
_SEP_CELL_RE = re.compile(r":?-+:?")
_CONFLICT_RE = re.compile(r"^(<<<<<<<|>>>>>>>)(\s|$)")


class Card:
    def __init__(self, path: Path, repo: Path, as_dir: Path):
        self.path, self.as_dir = path, as_dir
        self.rel = path.relative_to(repo).as_posix()
        self.reg_dir = path.parent
        raw = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
        fm_text, self.body = frontmatter_split(raw)
        self.broken = fm_text is None
        # номер строки файла = номер строки тела + смещение (шапка и разделители)
        self.body_offset = raw.count("\n") - self.body.count("\n")
        self.fm: Dict[str, str] = {}
        for ln in (fm_text or "").split("\n"):
            m = re.match(r"^([\w-]+):\s*(.*?)\s*$", ln)
            if m:
                self.fm[m.group(1)] = _unquote(_strip_comment(m.group(2)))

    def get(self, key: str) -> str:
        return self.fm.get(key, "")

    @property
    def id(self) -> str:
        return self.get("id")


def _strip_comment(v: str) -> str:
    return re.sub(r"\s+#.*$", "", v) if not v.startswith(("'", '"')) else v


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        q, v = v[0], v[1:-1]
        if q == "'":
            v = v.replace("''", "'")      # YAML: '' внутри одинарных кавычек — одна кавычка
    return v.strip()


def _num(card_id: str) -> int:
    m = re.search(r"-(\d+)$", card_id)
    return int(m.group(1)) if m else 10 ** 6


_REGISTRY_TYPE_RE = re.compile(r"^type:\s*['\"]?external-integration-registry['\"]?\s*$", re.M)


def _is_as_dir(d: Path) -> bool:
    """Папка АС — по форме: в ней есть карточки `extint-*.md` (вне examples/ и files/) или README
    с `type: external-integration-registry`. Прочие каталоги верхнего уровня (рабочий sandbox/
    исполнителя и подобные) — не АС (замечание 2026-11-08: «АС 33» при sandbox/ в worktree)."""
    if any(not (SKIP_DIRS & set(p.relative_to(d).parts[:-1])) for p in d.rglob("extint-*.md")):
        return True
    readme = d / "README.md"
    if readme.is_file():
        fm, _body = frontmatter_split(readme.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n"))
        return bool(fm and _REGISTRY_TYPE_RE.search(fm))
    return False


def as_dirs(repo: Path) -> List[Path]:
    return sorted(p for p in repo.iterdir() if p.is_dir() and not p.name.startswith(".") and _is_as_dir(p))


def skipped_dirs(repo: Path) -> List[str]:
    """Каталоги верхнего уровня, не признанные папками АС (скрытые .git, .claude — молча, как прежде)."""
    return sorted(p.name for p in repo.iterdir() if p.is_dir() and not p.name.startswith(".")
                  and not _is_as_dir(p))


def _skipped_note(repo: Path) -> str:
    names = skipped_dirs(repo)
    return (f"i каталогов пропущено: {len(names)} ({', '.join(names)}) — не папки АС: нет карточек extint-*.md "
            "и README с type: external-integration-registry") if names else ""


def find_cards(repo: Path) -> List[Card]:
    cards = []
    for d in as_dirs(repo):
        for p in sorted(d.rglob("extint-*.md")):
            if SKIP_DIRS & set(p.relative_to(d).parts[:-1]):
                continue
            cards.append(Card(p, repo, d))
    return cards


# ---------------------------------------------------------------- разбор README

class Section:
    def __init__(self, title: str):
        self.title = title
        self.header: List[str] = []
        self.rows: List[List[str]] = []
        self.tables = 0


def parse_sections(text: str) -> Dict[str, Section]:
    """Разделы «## …» с таблицами (вне блоков кода): заголовок таблицы и строки."""
    lines = text.replace("\r\n", "\n").split("\n")
    code = code_line_flags(lines)
    out: Dict[str, Section] = {}
    cur: Optional[Section] = None
    in_table = False
    for ln, is_code in zip(lines, code):
        if not is_code and ln.startswith("## "):
            cur = out.setdefault(ln[3:].strip(), Section(ln[3:].strip()))
            in_table = False
            continue
        st = ln.strip()
        if cur is None or is_code or not st.startswith("|"):
            in_table = False
            continue
        cells = table_cells(st)
        if all(_SEP_CELL_RE.fullmatch(c) for c in cells if c):
            continue
        if not in_table:
            cur.tables += 1
            in_table = True
            if not cur.header:
                cur.header = cells
                continue
            if cells == cur.header:
                continue
        cur.rows.append(cells)
    return out


def _link_target(cell: str) -> str:
    m = _TARGET_RE.search(cell)
    return (m.group(1) if m else cell.strip("` ")).split("#", 1)[0]


# ---------------------------------------------------------------- проверка

class Report:
    def __init__(self, limit: int = 12):
        self.lines: List[str] = []
        self.fail = 0
        self.warn = 0
        self.limit = limit

    def emit(self, mark: str, title: str, items: List[str]) -> None:
        if not items:
            return
        if mark == "✗":
            self.fail += len(items)
        else:
            self.warn += len(items)
        shown = items if self.limit <= 0 else items[:self.limit]
        self.lines.append(f"{mark} {title} ×{len(items)}:")
        self.lines.extend(f"   {x}" for x in shown)
        if len(shown) < len(items):
            self.lines.append(f"   … ещё {len(items) - len(shown)} (полный перечень: --limit 0)")

    def info(self, text: str) -> None:
        self.lines.append(f"i {text}")


def check_cards(cards: List[Card], rep: Report) -> None:
    broken = [c.rel for c in cards if c.broken]
    rep.emit("✗", "шапка карточки не закрыта или отсутствует — поля не читаются", broken)
    ok = [c for c in cards if not c.broken]
    rep.emit("⚠", "нет id", [c.rel for c in ok if not c.id])
    rep.emit("⚠", "нет title (в реестре — H1 карточки без ID)", [c.rel for c in ok if not c.get("title")])
    rep.emit("⚠", "нет kind или значение вне " + " | ".join(KINDS),
             [f"{c.rel}: {c.get('kind') or NO_VALUE}" for c in ok if c.get("kind") not in KINDS])
    rep.emit("⚠", "нет channel или значение вне словаря шаблона (в реестре — «—»)",
             [f"{c.rel}: {c.get('channel') or NO_VALUE}" for c in ok
              if c.get("channel") not in CHANNEL_TITLE])
    rep.emit("⚠", "у операции нет sync или значение вне sync | async",
             [f"{c.rel}: {c.get('sync') or NO_VALUE}" for c in ok
              if c.get("kind") == "operation" and c.get("sync") not in SYNCS])
    rep.emit("⚠", "у message или common указан sync (не указывается — синхронность только у вызова)",
             [f"{c.rel}: {c.get('kind')}" for c in ok if c.get("kind") in ("message", "common") and "sync" in c.fm])
    by_id: Dict[str, List[str]] = defaultdict(list)
    for c in ok:
        if c.id:
            by_id[c.id].append(c.rel)
    rep.emit("⚠", "дубль id — перенумерация отдельным решением владельца с уведомлением потребителей",
             [f"{i}: {', '.join(v)}" for i, v in sorted(by_id.items()) if len(v) > 1])
    # Общий базовый контракт — один на метод (решение владельца пилота 2026-11-01): дубль ID ловится
    # выше, а одинаковое название метода в одной АС под разными ID — нет (EXTINT-F1-026 и
    # EXTINT-F1-029 — одна и та же DBLINK-витрина). Название — title, без него H1 без ID; сравнение
    # без регистра, вида кавычек и лишних пробелов. Разные АС — не дубль.
    by_name: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    shown: Dict[Tuple[str, str], str] = {}
    for c in ok:
        title = c.get("title") or h1_name(c)
        key = (c.as_dir.name, _name_key(title))
        if key[1]:
            by_name[key].append(c.id or c.rel)
            shown.setdefault(key, title)
    rep.emit("⚠", "одинаковое название метода в одной АС под разными id — общий базовый контракт один "
                  "на метод: дубль объединяет владелец с уведомлением потребителей",
             [f"{key[0]}: {', '.join(v)} — «{shown[key]}»" for key, v in sorted(by_name.items())
              if len(v) > 1])
    bad = []
    for c in ok:
        folder = c.as_dir.name
        m = re.match(r"^extint-" + re.escape(folder) + r"-(\d{3})-.+\.md$", c.path.name)
        if not m:
            bad.append(f"{c.rel}: имя файла не extint-{folder}-NNN-<slug>.md")
        elif c.id and c.id != f"EXTINT-{folder.upper()}-{m.group(1)}":
            bad.append(f"{c.rel}: id {c.id}, по имени файла и папке — EXTINT-{folder.upper()}-{m.group(1)}")
    rep.emit("⚠", "id ↔ имя файла ↔ папка расходятся", bad)


_NAME_QUOTES_RE = re.compile(r"[«»“”„\"']")


def _name_key(name: str) -> str:
    """Название для сверки дублей: без регистра, вида кавычек, лишних пробелов и точки в конце."""
    return re.sub(r"\s+", " ", _NAME_QUOTES_RE.sub('"', name)).strip().rstrip(".").casefold()


def check_consumers(cards: List[Card], rep: Report) -> None:
    missing, cols, refs, relative = [], [], [], []
    for c in cards:
        # и у карточки со сломанной шапкой: тело читается целиком, адреса проверяются
        lines = c.body.split("\n")
        flags = code_line_flags(lines)
        start = next((i for i, (ln, f) in enumerate(zip(lines, flags))
                      if not f and ln.strip() == "## Потребители"), None)
        if start is None:
            missing.append(c.rel)
            continue
        end = next((i for i in range(start + 1, len(lines))
                    if not flags[i] and lines[i].startswith("## ")), len(lines))
        sec = lines[start + 1:end]
        rows = [ln.strip() for ln in sec if ln.strip().startswith("|")]
        if rows and len(table_cells(rows[0])) != 3:
            cols.append(f"{c.rel}: колонок {len(table_cells(rows[0]))}")
        bad_refs: Dict[str, int] = defaultdict(int)
        for ln in rows[2:]:
            for target in _TARGET_RE.findall(ln):
                if not re.match(r"https?://", target):
                    relative.append(f"{c.rel}: {target}")
            # адреса — и в ссылках, и голыми URL в ячейке (ESK-004…006)
            for url in _URL_RE.findall(ln):
                b = _BLOB_RE.search(url)
                if b and b.group(1) != "HEAD":
                    bad_refs[b.group(1)] += 1
        if bad_refs:
            refs.append(f"{c.rel}: " + ", ".join(f"/-/blob/{r}/ ×{n}" for r, n in sorted(bad_refs.items())))
    rep.emit("⚠", "нет раздела «Потребители»", missing)
    rep.emit("⚠", "таблица «Потребители» не в три колонки (Сервис | Локальный ID | Карточка вызова)", cols)
    rep.emit("⚠", "адрес карточки вызова не абсолютный", relative)
    rep.emit("⚠", "адрес карточки вызова не на /-/blob/HEAD/ (не master, не trunk, не рабочая ветка)", refs)


def h1_name(card: Card) -> str:
    """H1 карточки без ID: «# EXTINT-AS-NNN. Название» → «Название»."""
    m = re.search(r"^# (.+)$", card.body, re.M)
    if not m:
        return ""
    return re.sub(r"^EXTINT-[A-Z0-9-]+?-\d+[A-Z]?\.?\s*", "", m.group(1).strip()).strip()


def expected_row(card: Card) -> Dict[str, str]:
    # «Название» = title; без title — H1 карточки без ID, ⚠ «нет title» остаётся (как в матрице;
    # решение владельца пилота 2026-10-18, пересмотр развилки 7)
    return {"title": card.get("title") or h1_name(card) or NO_VALUE,
            "channel": CHANNEL_TITLE.get(card.get("channel"), NO_VALUE),
            "sync": card.get("sync") if card.get("sync") in SYNCS else NO_VALUE}


def check_readmes(repo: Path, cards: List[Card], rep: Report) -> None:
    by_dir: Dict[Path, List[Card]] = defaultdict(list)
    for c in cards:
        by_dir[c.reg_dir].append(c)
    no_readme, not_tpl, no_row, row_no_file, mism, wrong_table = [], [], [], [], [], []
    for d in sorted(by_dir):
        rel_d = d.relative_to(repo).as_posix()
        readme = d / "README.md"
        if not readme.is_file():
            no_readme.append(f"{rel_d}/ (карточек {len(by_dir[d])})")
            continue
        secs = parse_sections(readme.read_bytes().decode("utf-8", errors="replace"))
        if OPS_TITLE not in secs:
            not_tpl.append(f"{rel_d}/README.md")
            continue
        names = {c.path.name: c for c in by_dir[d]}
        seen = set()
        for _k, title, _cols, _intro in TABLES:
            sec = secs.get(title)
            if sec is None:
                continue
            col = {h: n for n, h in enumerate(sec.header)}
            for r in sec.rows:
                cell = r[col["Карточка"]] if "Карточка" in col and col["Карточка"] < len(r) else r[-1]
                fname = _link_target(cell).split("/")[-1]
                c = names.get(fname)
                if c is None:
                    row_no_file.append(f"{rel_d}/README.md «{title}»: {r[0]} → {fname or NO_VALUE}")
                    continue
                seen.add(fname)
                want = expected_row(c)
                kind = c.get("kind")
                if kind in TABLE_OF_KIND and TABLE_OF_KIND[kind] != title:
                    wrong_table.append(f"{c.rel}: kind {kind}, строка в «{title}»")
                got = {"title": r[col["Название"]] if "Название" in col and col["Название"] < len(r) else "",
                       "channel": r[col["Канал"]] if "Канал" in col and col["Канал"] < len(r) else "",
                       "sync": r[col["Синхронность"]] if "Синхронность" in col and col["Синхронность"] < len(r) else want["sync"]}
                for key, label in (("title", "название"), ("channel", "канал"), ("sync", "синхронность")):
                    if title != OPS_TITLE and key == "sync":
                        continue
                    if got[key].replace("\\|", "|") != want[key]:
                        mism.append(f"{c.rel}: {label} в README «{got[key]}», в карточке «{want[key]}»")
                if c.id and r[0] != c.id:
                    mism.append(f"{c.rel}: ID в README «{r[0]}», в карточке «{c.id}»")
        no_row += [c.rel for c in by_dir[d] if c.path.name not in seen]
    rep.emit("⚠", "нет README.md каталога карточек", no_readme)
    rep.emit("⚠", "README не по шаблону (нет раздела «Операции») — сверка таблиц пропущена, перевод отдельным заходом", not_tpl)
    rep.emit("⚠", "карточки нет в таблицах README (--write добавит)", no_row)
    rep.emit("⚠", "строка README без файла (снимает человек; --write откажет)", row_no_file)
    rep.emit("⚠", "строка README расходится с шапкой карточки", mism)
    rep.emit("⚠", "строка не в той таблице по kind", wrong_table)
    # README папки АС с подкаталогами каналов — ручной: ссылки на README каналов
    links_missing = []
    for d in as_dirs(repo):
        channel_dirs = sorted({c.reg_dir for c in cards if c.as_dir == d and c.reg_dir != d})
        if not channel_dirs:
            continue
        readme = d / "README.md"
        text = readme.read_bytes().decode("utf-8", errors="replace") if readme.is_file() else ""
        for cd in channel_dirs:
            sub = cd.relative_to(d).as_posix()
            if not re.search(r"\]\(\.?/?" + re.escape(sub) + r"/(README\.md)?\)", text):
                links_missing.append(f"{d.name}/README.md → {sub}/README.md")
    rep.emit("⚠", "README папки АС не ссылается на README канала", links_missing)


def check_root(repo: Path, cards: List[Card], rep: Report) -> None:
    readme = repo / "README.md"
    if not readme.is_file():
        rep.emit("⚠", "нет корневого README.md", ["README.md"])
        return
    secs = parse_sections(readme.read_bytes().decode("utf-8", errors="replace"))
    sec = secs.get(ROOT_TITLE)
    if sec is None:
        rep.emit("⚠", f"корневой README: нет раздела «{ROOT_TITLE}» — сверка реестра систем пропущена",
                 ["README.md"])
        return
    col = {h: n for n, h in enumerate(sec.header)}
    count: Dict[str, int] = defaultdict(int)
    for c in cards:
        count[c.as_dir.name] += 1
    folders = {d.name for d in as_dirs(repo)}
    seen, issues = set(), []
    for r in sec.rows:
        fcell = r[col["Папка"]] if "Папка" in col and col["Папка"] < len(r) else ""
        folder = _link_target(fcell).strip("/").split("/")[0]
        if folder not in folders:
            issues.append(f"строка без папки: {fcell or NO_VALUE}")
            continue
        seen.add(folder)
        n = r[col["Карточек"]] if "Карточек" in col and col["Карточек"] < len(r) else ""
        if n != str(count[folder]):
            issues.append(f"{folder}: карточек в реестре {n or NO_VALUE}, в папке {count[folder]}")
        rcell = r[col["README"]] if "README" in col and col["README"] < len(r) else ""
        has = (repo / folder / "README.md").is_file()
        if has != bool(_TARGET_RE.search(rcell)):
            issues.append(f"{folder}: README в реестре «{rcell or NO_VALUE}», файл {'есть' if has else 'нет'}")
    issues += [f"папки нет в реестре: {f}/" for f in sorted(folders - seen)]
    rep.emit("⚠", f"корневой README, «{ROOT_TITLE}» ↔ папки АС", issues)


def check_conflicts(repo: Path, rep: Report) -> None:
    hits = []
    for p in sorted(repo.rglob("*.md")):
        if ".git" in p.relative_to(repo).parts:
            continue
        lines = p.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
        for n, (ln, f) in enumerate(zip(lines, code_line_flags(lines)), 1):
            if not f and _CONFLICT_RE.match(ln):
                hits.append(f"{p.relative_to(repo).as_posix()}:{n}: {ln[:40]}")
    rep.emit("✗", "маркер конфликта слияния", hits)


# ---------------------------------------------------------------- содержимое потребителя в base
#
# Шаблон канона contract-call.md, раздел A (решение владельца 2026-11-08): базовый контракт
# содержит то, что задаёт владелец АС; кто вызывает метод, чем потребитель заполняет параметры и
# что делает с ответом — в карточке вызова и функции потребителя. Признаки — по форме карточки:
# положение (§1 таблица паспорта, §4), нотация шагов канона (`**Шаг N.**`, notation.md техбука),
# наличие ссылки на файл. Словарная часть — лейблы двух строк паспорта («Где используется»,
# «Документация») и текст-указатель шаблона: основание — шаблон, видимость — i-строка с числом
# проверенных строк, строка в реестре словарных эвристик README прибора.
# указатель шаблона и его короткая прежняя форма (без хвоста «и в docs сервисов») — содержимого
# потребителя в обеих нет (решение 2026-11-08); любой другой текст в ячейке — сигнал
BASE_POINTERS = ("Потребители — в разделе «Потребители» и в docs сервисов",
                 "Потребители — в разделе «Потребители»")
BASE_MARK = "⚠"           # уровень признаков содержимого потребителя (решение владельца по замеру trunk)
_LABEL_USED = "где используется"
_LABEL_DOC = "документация"
_OLD_S4_TITLE = "обработка ошибок и повторные вызовы"
_STEP_NOTATION_RE = re.compile(r"\*\*Шаг\s*№?\s*\d+(?:\.\d+)*\.?\*\*")
_SUBHEAD_RE = re.compile(r"^#{3,6}\s+(.+?)\s*$")
_ASSIGN_RE = re.compile(r"^\s*(?:\*\*|__)?\s*=")
# ID артефакта сервиса (PROC-004, CALL-EXT-049, FUN-CL-12) и адрес в чужом репозитории
_FOREIGN_ID_RE = re.compile(r"\b(?!EXTINT-)(?:[A-Z]{2,6}-)+\d{2,3}(?:\.\d+)?\b")
_FOREIGN_LINK_RE = re.compile(r"\]\([^)\s]*/-/blob/|\]\(\.\./\.\./")
_ABOUT_ID_RE = re.compile(r"\bEXTINT-[A-Z0-9]+(?:-[A-Z0-9]+)*?-\d{3}\b")


def _plain_cell(cell: str) -> str:
    """Ячейка для сравнения: без жирного/кода, кавычки одного вида, пробелы схлопнуты, без точки в конце."""
    s = re.sub(r"\*\*|__|`", "", cell)
    s = re.sub(r"[«»“”„\"]", '"', s)
    return re.sub(r"\s+", " ", s).strip().rstrip(".").casefold()


def _numbered_sections(card: Card) -> Dict[str, Tuple[str, List[Tuple[int, str]]]]:
    """Разделы «## N. …» тела карточки: номер → (заголовок, [(номер строки файла, строка)]) вне кода."""
    lines = card.body.split("\n")
    flags = code_line_flags(lines)
    out: Dict[str, Tuple[str, List[Tuple[int, str]]]] = {}
    cur: Optional[str] = None
    for n, (ln, f) in enumerate(zip(lines, flags), card.body_offset + 1):
        if f:
            continue
        if ln.startswith("## "):
            m = re.match(r"^## (\d+)\.", ln)
            cur = m.group(1) if m else None
            if cur is not None and cur not in out:
                out[cur] = (ln[3:].strip(), [])
            continue
        if cur is not None:
            out[cur][1].append((n, ln))
    return out


_DOC_TARGET_RE = re.compile(r"\]\(<?([^)>]+?)>?\)")   # адрес с пробелами: «files/Интеграция с ЕПР.txt»


_EXT_URL_RE = re.compile(r"https?://([^/\s)|>\]]+)", re.I)


def _doc_file_state(card: Card, cell: str) -> str:
    """«file» — в ячейке ссылка на существующий файл в files/ папки АС карточки или внешний URL вне
    Confluence (внешняя документация владельца переносится дословно — шаблон, раздел A); «missing» —
    ссылка в files/ есть, файла по ней нет; «» — ни того, ни другого. Confluence — по имени хоста."""
    if any("confluence" not in h.casefold() for h in _EXT_URL_RE.findall(cell)):
        return "file"
    files_dir = (card.as_dir / "files").resolve()
    state = ""
    for target in _DOC_TARGET_RE.findall(cell):
        t = target.split("#", 1)[0].strip()
        if not t or re.match(r"[a-z]+://", t):
            continue
        p = (card.path.parent / t).resolve()
        try:
            p.relative_to(files_dir)
        except ValueError:
            continue
        if p.is_file():
            return "file"
        state = "missing"
    return state


def check_base_content(cards: List[Card], rep: Report) -> None:
    """Содержимое потребителя в базовом контракте (шаблон contract-call.md, раздел A)."""
    pointers = {_plain_cell(p) for p in BASE_POINTERS}
    used, doc, sub, steps, old4, assigns = [], [], [], [], [], []
    n_used = n_doc = 0
    for c in cards:
        if c.get("type") not in ("", "external-integration"):
            continue
        secs = _numbered_sections(c)
        _h1, s1 = secs.get("1", ("", []))
        for n, ln in s1:
            st = ln.strip()
            mh = _SUBHEAD_RE.match(st)
            if mh and _plain_cell(mh.group(1)).rstrip(":") in (_LABEL_USED, _LABEL_DOC):
                sub.append(f"{c.rel}:{n}: {st[:70]}")
                continue
            if not st.startswith("|"):
                continue
            cells = table_cells(st)
            if len(cells) < 2:
                continue
            label = _plain_cell(cells[0]).rstrip(":")
            if label == _LABEL_USED:
                n_used += 1
                if _plain_cell(cells[1]) not in pointers:
                    used.append(f"{c.rel}:{n}: {cells[1][:70] or NO_VALUE}")
            elif label == _LABEL_DOC:
                n_doc += 1
                state = _doc_file_state(c, cells[1])
                if state != "file":
                    doc.append(f"{c.rel}:{n}: {cells[1][:70] or NO_VALUE}"
                               + (" (файла по ссылке в files/ нет)" if state == "missing" else ""))
        h4, s4 = secs.get("4", ("", []))
        if _OLD_S4_TITLE in h4.casefold():
            old4.append(c.rel)
        for n, ln in s4:
            if _STEP_NOTATION_RE.search(ln):
                steps.append(f"{c.rel}:{n}: {ln.strip()[:70]}")
        for key in ("2", "3"):
            col = None
            for n, ln in secs.get(key, ("", []))[1]:
                st = ln.strip()
                if not st.startswith("|"):
                    col = None
                    continue
                cells = table_cells(st)
                if col is None:
                    col = next((i for i, h in enumerate(cells)
                                if _plain_cell(h).startswith("правила заполнения")), -1)
                    continue
                if col < 0 or col >= len(cells) or all(_SEP_CELL_RE.fullmatch(x) for x in cells if x):
                    continue
                v = cells[col]
                if _ASSIGN_RE.match(v) or _FOREIGN_LINK_RE.search(v) or _FOREIGN_ID_RE.search(v):
                    assigns.append(f"{c.rel}:{n}: {cells[0][:40]} — {v[:60]}")
    rep.info(f"содержимое потребителя в base (шаблон contract-call, раздел A): строк «Где используется» "
             f"{n_used}, «Документация» {n_doc} — сверены с указателем шаблона и ссылкой на files/")
    rep.emit(BASE_MARK, "§1 «Где используется» — не указатель шаблона «" + BASE_POINTERS[0]
             + "»: содержимое — в «Процессы» карточки вызова потребителя", used)
    rep.emit(BASE_MARK, "§1 «Документация» без ссылки на файл в files/ папки АС или внешний URL вне "
                        "Confluence — строка не создаётся; страница владельца — в «Документация АС» README папки",
             doc)
    rep.emit(BASE_MARK, "§1 подраздел с лейблом паспорта «Где используется» / «Документация» — ячейки §1 "
                        "в подразделы не выводятся", sub)
    rep.emit(BASE_MARK, "§4 шаги потребителя (нотация **Шаг N.**) — в функцию или процесс потребителя, "
                        "в §4 только коды результата и отказов владельца", steps)
    rep.emit("⚠", "§4 прежний заголовок «Обработка ошибок и повторные вызовы» — «Коды результата и "
                  "отказов» при переделке карточки", old4)
    if assigns:
        shown = assigns if rep.limit <= 0 else assigns[:rep.limit]
        rep.info(f"правил-присвоений в base: {len(assigns)} — «=» в начале «Правил заполнения» или ID/адрес "
                 "артефакта сервиса; константа владельца и присвоение потребителя по форме не различаются, "
                 "вынос — по правилу границы шаблона:")
        rep.lines.extend(f"   {x}" for x in shown)
        if len(shown) < len(assigns):
            rep.lines.append(f"   … ещё {len(assigns) - len(shown)} (полный перечень: --limit 0)")


def check_readme_about(repo: Path, cards: List[Card], rep: Report) -> None:
    """ID карточек в ручной части README («## О системе») — их дом выводимые таблицы
    (шаблон contract-call.md, раздел A, README папки АС; решение владельца 2026-11-08)."""
    dirs = sorted({c.reg_dir for c in cards} | {c.as_dir for c in cards})
    hits = []
    for d in dirs:
        readme = d / "README.md"
        if not readme.is_file():
            continue
        lines = readme.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
        on = False
        for n, (ln, f) in enumerate(zip(lines, code_line_flags(lines)), 1):
            if f:
                continue
            if ln.startswith("## "):
                on = ln.strip() == "## О системе"
                continue
            if on:
                ids = list(dict.fromkeys(_ABOUT_ID_RE.findall(ln)))
                if ids:
                    hits.append(f"{readme.relative_to(repo).as_posix()}:{n}: {', '.join(ids)}")
    rep.emit("⚠", "ID карточек в ручной части README («О системе») — их дом выводимые таблицы ниже", hits)


def check(repo: Path, limit: int = 12) -> Tuple[List[str], bool]:
    """(отчёт, есть ⚠ или ✗)."""
    cards = find_cards(repo)
    rep = Report(limit)
    check_cards(cards, rep)
    check_readmes(repo, cards, rep)
    check_readme_about(repo, cards, rep)
    check_root(repo, cards, rep)
    check_consumers(cards, rep)
    check_base_content(cards, rep)
    check_conflicts(repo, rep)
    note = _skipped_note(repo)
    if note:
        rep.lines.append(note)
    n_as = len(as_dirs(repo))
    total = f"ИТОГО: АС {n_as}, карточек {len(cards)}; ✗ {rep.fail}, ⚠ {rep.warn}"
    if not rep.fail and not rep.warn:
        rep.lines.append("✓ реестры и шапки карточек сходятся")
    rep.lines.append(total)
    return rep.lines, bool(rep.fail or rep.warn)


# ---------------------------------------------------------------- запись

NOT_SET = "в источниках не задано"
EXAMPLES_TEXT = ("Каталог [`examples/`](examples/): файлы обмена по карточкам; какой файл к какой карточке —\n"
                 "§5 карточки.")
NO_EXAMPLES_TEXT = "Примеров обмена нет: каталога `examples/` в папке нет."
POINTER = ("Здесь — базовые контракты {name}: операции, сообщения и общие форматы с параметрами, кодами\n"
           "результата и примерами, одно описание на всю Экосистему. Чего здесь нет: как сервис\n"
           "вызывает контракт — карточка `CALL-EXT-NNN` в комплекте сервиса-потребителя\n"
           "(`srs/contract-call/external/`); маппинг на сущности сервисов; открытые вопросы сервисов.\n"
           "Потребители контракта и адреса их карточек вызова — в разделе «Потребители» его карточки.")


def _esc(text: str) -> str:
    return re.sub(r"(?<!\\)\|", r"\\|", re.sub(r"\s+", " ", text)).strip() or NO_VALUE


def aligned(cols: List[str], rows: List[List[str]]) -> List[str]:
    """Таблица, выровненная пробелами (шаблон: «таблицы выровнены пробелами»)."""
    widths = [max([len(c)] + [len(r[n]) for r in rows] + [3]) for n, c in enumerate(cols)]

    def line(cells: List[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[n]) for n, c in enumerate(cells)) + " |"
    return [line(cols), "| " + " | ".join("-" * w for w in widths) + " |"] + [line(r) for r in rows]


def _order(card: Card) -> Tuple[int, int, str]:
    ch = card.get("channel")
    pos = [k for k, _ in CHANNELS].index(ch) if ch in CHANNEL_TITLE else len(CHANNELS)
    return (pos, _num(card.id), card.path.name)


def card_rows(cards: List[Card], kind: str) -> List[List[str]]:
    out = []
    for c in sorted((c for c in cards if c.get("kind") == kind), key=_order):
        want = expected_row(c)
        link = f"[{c.path.name}]({c.path.name})"
        row = [c.id or NO_VALUE, _esc(want["title"]), want["channel"]]
        out.append(row + ([want["sync"]] if kind == "operation" else []) + [link])
    return out


def _section_span(lines: List[str], title: str) -> Optional[Tuple[int, int]]:
    """[начало, конец) раздела «## <title>» в строках файла (вне блоков кода)."""
    flags = code_line_flags(lines)
    start = next((i for i, (ln, f) in enumerate(zip(lines, flags)) if not f and ln.rstrip() == f"## {title}"), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if not flags[i] and lines[i].startswith("## ")), len(lines))
    return start, end


def _replace_table(lines: List[str], span: Tuple[int, int], table: List[str]) -> List[str]:
    """Первая таблица раздела заменяется новой; текст раздела вне таблицы — как был.
    Таблицы в разделе нет — вставляется после текста раздела."""
    s, e = span
    t0 = next((i for i in range(s + 1, e) if lines[i].lstrip().startswith("|")), None)
    if t0 is None:
        body_end = e
        while body_end - 1 > s and not lines[body_end - 1].strip():
            body_end -= 1
        return lines[:body_end] + [""] + table + [""] + lines[body_end:]
    t1 = t0
    while t1 < e and lines[t1].lstrip().startswith("|"):
        t1 += 1
    return lines[:t0] + table + lines[t1:]


def system_names(repo: Path) -> Dict[str, str]:
    """Имя АС по папке: строка «## Реестр систем» корневого README, иначе заголовок
    «### <имя> — папка [`<папка>/`]» прежнего реестра карточек."""
    readme = repo / "README.md"
    if not readme.is_file():
        return {}
    text = readme.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    out: Dict[str, str] = {}
    for m in re.finditer(r"^### (.+?) — папка \[`?([\w-]+)/?`?\]", text, re.M):
        out.setdefault(m.group(2), m.group(1).strip())
    sec = parse_sections(text).get(ROOT_TITLE)
    if sec and "Папка" in sec.header and "Система" in sec.header:
        col = {h: n for n, h in enumerate(sec.header)}
        for r in sec.rows:
            if max(col["Папка"], col["Система"]) < len(r):
                folder = _link_target(r[col["Папка"]]).strip("/").split("/")[0]
                out[folder] = r[col["Система"]]
    return out


def _table_block(kind: str, title: str, cols: List[str], intro: str, cards: List[Card]) -> List[str]:
    """Раздел таблицы README: заголовок, вводная фраза шаблона (кроме «Операций»), таблица."""
    return [f"## {title}", ""] + ([intro, ""] if intro else []) + aligned(cols, card_rows(cards, kind)) + [""]


def new_readme(as_code: str, name: str, d: Path, cards: List[Card], eol: str) -> str:
    about = [["Система", _esc(name)], ["Каналы", NOT_SET], ["Среда и адреса", "в источниках не заданы"],
             ["Документация АС", "в источниках не задана"],
             ["Примеры", "[examples/](examples/)" if (d / "examples").is_dir() else NO_VALUE]]
    if (d / "files").is_dir():
        about.append(["Вложения", "[files/](files/)"])
    title = f"{name} — базовые контракты внешней АС"
    out = ["---", f"id: EXTINT-{as_code}-000", "title: '" + title.replace("'", "''") + "'",
           "type: external-integration-registry", "---", "", f"# EXTINT-{as_code}-000. {title}", "",
           f"Назначение АС: {NOT_SET}.", "", POINTER.format(name=name), "", "## О системе", ""]
    out += aligned(["Поле", "Значение"], about) + [""]
    for kind, title, cols, intro in TABLES:
        # «Операции» — всегда; прочие разделы — только при карточках этого вида
        if kind == "operation" or any(c.get("kind") == kind for c in cards):
            out += _table_block(kind, title, cols, intro, cards)
    out += ["## Примеры обмена", "", EXAMPLES_TEXT if (d / "examples").is_dir() else NO_EXAMPLES_TEXT, ""]
    return eol.join("\n".join(out).split("\n"))


def _read(p: Path) -> Tuple[str, bool, str]:
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = (raw[3:] if bom else raw).decode("utf-8")
    return text, bom, ("\r\n" if "\r\n" in text else "\n")


def _write_atomic(p: Path, text: str, bom: bool) -> None:
    data = (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".extint-", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def rebuild_readme(text: str, cards: List[Card]) -> str:
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    prev = OPS_TITLE
    for kind, title, cols, intro in TABLES:
        rows = card_rows(cards, kind)
        span = _section_span(lines, title)
        if span:
            # раздел есть — заменяется только таблица; без карточек этого вида раздел остаётся с
            # пустой таблицей (ручной текст раздела не снимается)
            lines = _replace_table(lines, span, aligned(cols, rows))
        elif rows:
            # раздела нет, карточки есть — раздел вставляется после предыдущего раздела таблиц
            ins = _section_span(lines, prev)[1]
            lines = lines[:ins] + _table_block(kind, title, cols, intro, cards) + lines[ins:]
        if _section_span(lines, title):
            prev = title
    return eol.join(lines)


def write(repo: Path) -> Tuple[List[str], int]:
    """(отчёт, код): 0 — записано или без изменений, 2 — есть отказы (эти файлы не тронуты)."""
    cards = find_cards(repo)
    names = system_names(repo)
    by_dir: Dict[Path, List[Card]] = defaultdict(list)
    for c in cards:
        by_dir[c.reg_dir].append(c)
    refused: List[str] = []
    written: List[str] = []
    created: List[str] = []
    for d in sorted(by_dir):
        rel = d.relative_to(repo).as_posix()
        dc = by_dir[d]
        why = []
        broken = [c.path.name for c in dc if c.broken]
        nokind = [c.path.name for c in dc if not c.broken and c.get("kind") not in KINDS]
        if broken:
            why.append(f"шапка не читается ×{len(broken)}: " + ", ".join(broken))
        if nokind:
            why.append(f"нет kind или вне {' | '.join(KINDS)} ×{len(nokind)}: " + ", ".join(nokind))
        readme = d / "README.md"
        if readme.is_file():
            text, bom, _eol = _read(readme)
            secs = parse_sections(text)
            if OPS_TITLE not in secs:
                why.append("README не по шаблону (нет «## Операции») — перевод отдельным заходом со сверкой фактов")
            else:
                files = {c.path.name for c in dc}
                for _k, title, _cols, _intro in TABLES:
                    sec = secs.get(title)
                    for r in (sec.rows if sec else []):
                        fname = _link_target(r[-1]).split("/")[-1]
                        if fname not in files:
                            why.append(f"строка «{title}» без файла: {r[0]} → {fname or NO_VALUE} "
                                       "(снимает человек)")
        if why:
            refused.append(f"{rel}/README.md: " + "; ".join(why))
            continue
        if readme.is_file():
            new = rebuild_readme(text, dc)
            if new != text:
                _write_atomic(readme, new, bom)
                written.append(f"{rel}/README.md")
        else:
            first, _bom, eol = _read(dc[0].path)
            as_code = dc[0].as_dir.name.upper()
            name = names.get(dc[0].as_dir.name, as_code)
            _write_atomic(readme, new_readme(as_code, name, d, dc, eol), False)
            created.append(f"{rel}/README.md")
    # корневой реестр систем
    root = repo / "README.md"
    root_note = ""
    if root.is_file():
        text, bom, _eol = _read(root)
        if ROOT_TITLE not in parse_sections(text):
            root_note = (f"i корневой README: нет раздела «{ROOT_TITLE}» — реестр систем не пересобран "
                         "(перевод корня — отдельным заходом)")
        else:
            sec = parse_sections(text)[ROOT_TITLE]
            col = {h: n for n, h in enumerate(sec.header)}
            folders = {d.name for d in as_dirs(repo)}
            kept: Dict[str, str] = {}
            gone = []
            for r in sec.rows:
                f = _link_target(r[col["Папка"]]).strip("/").split("/")[0] if col.get("Папка", 99) < len(r) else ""
                if f not in folders:
                    gone.append(f"строка без папки: {r[col['Папка']] if col.get('Папка', 99) < len(r) else NO_VALUE}")
                elif col.get("Система", 99) < len(r):
                    kept[f] = r[col["Система"]]
            if gone:
                refused.append("README.md («Реестр систем»): " + "; ".join(gone) + " (снимает человек)")
            else:
                count: Dict[str, int] = defaultdict(int)
                for c in cards:
                    count[c.as_dir.name] += 1
                rows = []
                for d in as_dirs(repo):
                    sysname = kept.get(d.name) or _esc(names.get(d.name, d.name.upper()))
                    has = (d / "README.md").is_file()
                    rows.append([sysname, f"[`{d.name}/`]({d.name}/)",
                                 f"[README]({d.name}/README.md)" if has else NO_VALUE, str(count[d.name])])
                lines = text.replace("\r\n", "\n").split("\n")
                lines = _replace_table(lines, _section_span(lines, ROOT_TITLE), aligned(ROOT_COLS, rows))
                new = ("\r\n" if "\r\n" in text else "\n").join(lines)
                if new != text:
                    _write_atomic(root, new, bom)
                    written.append("README.md («Реестр систем»)")
    report: List[str] = []
    if refused:
        report.append(f"✗ --write отказывает ×{len(refused)} — эти файлы не тронуты:")
        report += [f"   {x}" for x in refused]
    if created:
        report.append(f"✓ создано по шаблону ×{len(created)} (ручные «Назначение» и «О системе» — «{NOT_SET}»):")
        report += [f"   {x}" for x in created]
    if written:
        report.append(f"✓ пересобрано ×{len(written)} (ручные разделы не тронуты):")
        report += [f"   {x}" for x in written]
    if root_note:
        report.append(root_note)
    skipped = _skipped_note(repo)
    if skipped:
        report.append(skipped)
    if not (refused or created or written):
        report.append("✓ реестры совпадают с карточками — файлы не перезаписаны")
    return report, 2 if refused else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Реестры docs-external-contracts: README папок АС, "
                                 "корневой реестр систем, поля шапки карточек (--check / --write).")
    ap.add_argument("--repo", type=Path, required=True, help="корень клона docs-external-contracts")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="сверка (режим по умолчанию)")
    mode.add_argument("--write", action="store_true",
                      help="пересобрать выводимые таблицы README АС и корневого реестра систем")
    ap.add_argument("--limit", type=int, default=12,
                    help="строк перечня на находку в --check (0 — все; по умолчанию 12)")
    args = ap.parse_args(argv)
    if not args.repo.is_dir():
        print(f"✗ нет каталога репозитория: {args.repo}")
        return 2
    if args.write:
        report, code = write(args.repo)
        print("\n".join(report))
        return code
    report, bad = check(args.repo, args.limit)
    print("\n".join(report))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
