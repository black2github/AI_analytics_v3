# app/scripts/CI/kitcheck/checks/artifacts.py
"""Проверки selfcheck: artifacts — перенесены из selfcheck.py дословно (этап 3 рефакторинга);
selfcheck реэкспортирует имена."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[2]))  # каталог утилит прибора
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from urllib.parse import unquote
import json
import re
try:
    from kitcheck import fs as _fs
    from kitcheck.md import _kit_md
    from kitcheck.md import code_blocks
    from kitcheck.md import page_ids
    from kitcheck.md import read_frontmatter
    from kitcheck.md import split_cells
    from kitcheck.md import strip_row
except ImportError:  # импорт пакетом app.scripts.CI (тесты)
    from .. import fs as _fs  # type: ignore
    from ..md import _kit_md  # type: ignore
    from ..md import code_blocks  # type: ignore
    from ..md import page_ids  # type: ignore
    from ..md import read_frontmatter  # type: ignore
    from ..md import split_cells  # type: ignore
    from ..md import strip_row  # type: ignore


_STRUCT_EXT = {".json", ".yaml", ".yml", ".xml"}


_BOM = b"\xef\xbb\xbf"


# Блок кода в ячейке таблицы выгрузка отдаёт как <pre>…</pre> (экспортёр с
# 2026-09-06, repair_export --unfence-html): пример из ячейки — тоже кандидат.
_PRE_RE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.S | re.I)


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-.]{7,}")


def _parse_structured(raw: bytes, ext: str) -> Optional[str]:
    """None — разбирается; иначе короткое описание ошибки."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return f"не UTF-8 ({e.reason})"
    try:
        if ext == ".json":
            import json
            json.loads(text)
        elif ext in (".yaml", ".yml"):
            try:
                import yaml  # noqa: WPS433 — есть в окружении прибора
            except ImportError:
                return None  # без PyYAML YAML не проверяем (молчим)
            yaml.safe_load(text)
        elif ext == ".xml":
            import xml.etree.ElementTree as ET
            ET.fromstring(text)
    except Exception as e:  # noqa: BLE001 — любой сбой разбора — находка
        return str(e).splitlines()[0][:120]
    return None


def _source_candidates(text: str) -> List[str]:
    """Фрагменты страницы источника, которые могли быть примером:
    блоки кода (границы — `is_fence`, как у всего прибора), `<pre>…</pre>`
    и ячейки таблиц (инлайн-код в ячейке склеивается, `<br>` — перевод
    строки)."""
    out = code_blocks(text)
    out.extend(re.sub(r"<br\s*/?>", "\n", m) for m in _PRE_RE.findall(text))
    for ln in text.splitlines():
        if ln.lstrip().startswith("|"):
            for cell in split_cells(strip_row(ln)):
                c = re.sub(r"<br\s*/?>", "\n", cell)
                c = c.replace("`", "").replace("\\|", "|").strip()
                if len(c) > 10:
                    out.append(c)
    return out


def _struct_tokens(raw: bytes) -> List[str]:
    text = raw.decode("utf-8", errors="replace")
    seen: List[str] = []
    for t in _TOKEN_RE.findall(text):
        if t not in seen and not t.isdigit():
            seen.append(t)
        if len(seen) >= 6:
            break
    return seen


def check_structured_examples(docs: Path, idx: Dict[str, Path]
                              ) -> Tuple[List[str], bool]:
    """(отчёт, ok). idx: page_id -> файл выгрузки (пусто без источников)."""
    files = sorted(p for p in docs.rglob("*")
                   if p.is_file() and p.suffix.lower() in _STRUCT_EXT)
    if not files:
        return [], True
    owners: Dict[Path, List[Path]] = {}
    for md in _kit_md(docs):
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _ART_LINK_RE.finditer(text):
            tgt = unquote(m.group(1)).split("#", 1)[0].replace("\\", "/")
            if not tgt or "://" in tgt:
                continue
            try:
                rp = (md.parent / Path(tgt)).resolve()
            except OSError:
                continue
            if rp.suffix.lower() in _STRUCT_EXT:
                owners.setdefault(rp, []).append(md)
    rep: List[str] = []
    ok = True
    n_ok = 0
    for f in files:
        rel = f.relative_to(docs).as_posix()
        raw = _fs.read_bytes(f)
        ext = f.suffix.lower()
        if raw.startswith(_BOM):
            ok = False
            rep.append(f"✗ структурный файл {rel}: BOM в начале — брак "
                       "переноса (источник BOM не несёт); снять BOM")
            continue
        err = _parse_structured(raw, ext)
        if err is None:
            n_ok += 1
            continue
        # развод причины по источнику
        cards = owners.get(f.resolve(), [])
        pages: List[Path] = []
        for c in cards:
            for pid in page_ids(read_frontmatter(c) or {}):
                if pid in idx and idx[pid] not in pages:
                    pages.append(idx[pid])
        tokens = _struct_tokens(raw)
        located = None
        src_parses = False
        for pg in pages:
            try:
                ptext = _fs.read_text(pg, encoding="utf-8", errors="replace")
            except OSError:
                continue
            hits = sum(1 for t in tokens if t in ptext)
            if tokens and hits >= max(2, len(tokens) // 2):
                located = pg
                for cand in _source_candidates(ptext):
                    if sum(1 for t in tokens if t in cand) >= 2 and \
                            _parse_structured(cand.encode("utf-8"),
                                              ext) is None:
                        src_parses = True
                        break
                break
        if located is not None and not src_parses:
            rep.append(f"⚠ структурный файл {rel} не разбирается ({err}); "
                       "в источнике пример тоже не разбирается — дефект "
                       "аналитики: сохранить как .txt с пометкой в карточке "
                       "и записью в вопросы, не чинить "
                       f"(источник: {located.name})")
            continue
        ok = False
        why = ("в источнике тот же пример разбирается" if src_parses
               else "в источнике пример не найден" if pages
               else "источника нет")
        rep.append(f"✗ структурный файл {rel} не разбирается ({err}); "
                   f"{why} — брак переноса, чинится по источнику")
    for f in files:
        if f.resolve() not in owners:
            rep.append(f"⚠ структурный файл {f.relative_to(docs).as_posix()} "
                       "без ссылающейся карточки — пример, о котором "
                       "комплект молчит")
    if n_ok and ok:
        rep.insert(0, f"структурные файлы: {n_ok} разбираются ✓")
    return rep, ok


_ART_LINK_RE = re.compile(r"\]\(([^)\s]+?)(?:\s+\"[^\"]*\")?\)")


def check_file_artifacts(docs: Path) -> Tuple[List[str], bool]:
    """Сторож не-markdown артефактов комплекта (files/): приложение
    источника (XSD/JSON-схема и т.п.) живёт в подкаталоге files/ рядом
    с карточкой-владельцем, и карточка ОБЯЗАНА на него ссылаться.
    Файл в files/ без входящей ссылки — «сирота» (✗): артефакт, о
    котором комплект молчит. Ссылка карточки в files/ на несуществующий
    файл — тоже ✗ (потеря артефакта). Каталоги img/ — вне сторожа:
    перенос картинок — отдельная существующая конвенция."""
    arts = {p.resolve() for p in docs.rglob("*")
            if p.is_file() and "files" in p.relative_to(docs).parts
            and "img" not in p.relative_to(docs).parts}
    linked: set = set()
    broken: List[Tuple[str, str]] = []
    for md in _kit_md(docs):
        try:
            text = _fs.read_text(md, encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _ART_LINK_RE.finditer(text):
            tgt = unquote(m.group(1)).split("#", 1)[0]
            if not tgt or "://" in tgt or tgt.startswith("mailto:"):
                continue
            norm_t = tgt.replace("\\", "/")
            if "files/" not in norm_t and not norm_t.startswith("files/"):
                continue
            try:
                rp = (md.parent / Path(norm_t)).resolve()
            except OSError:
                continue
            if rp.is_file():
                linked.add(rp)
            else:
                broken.append((md.relative_to(docs).as_posix(), tgt))
    rep: List[str] = []
    ok = True
    for a in sorted(arts - linked):
        ok = False
        rep.append("✗ файл-артефакт без ссылающейся карточки (сирота "
                   "files/): "
                   + Path(a).relative_to(docs.resolve()).as_posix()
                   + " — артефакт, о котором комплект молчит")
    for rel, tgt in broken:
        ok = False
        rep.append(f"✗ битая ссылка на files-артефакт: {rel} → {tgt} "
                   "(файла нет — потеря артефакта)")
    return rep, ok
