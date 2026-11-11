# app/scripts/CI/kitcheck/checks/card_deviation.py
# Слой: миграция
"""Заметка о санкционированном отклонении снимает названные шаг, раздел и строку таблицы
источника из сверки (решение владельца 2026-11-11; постановка прибору того же дня, КК 2.17,
страница 2166861005: шаг 0 и строка паспорта «Привилегии» относятся к другому методу).

Норма канона (reference.md, «Санкционированное отклонение от источника») описывает заметку в
карточке. Прибор читает только заметку с явным перечнем:

    Не перенесено как санкционированное отклонение, решение <кого> <дата>: шаг 0; раздел «X»;
    строка «Y». <свободный текст>

- Формула канона: «санкционированное отклонение», «решение» и дата (ГГГГ-ММ-ДД или ДД.ММ.ГГГГ)
  в одном абзаце вне блоков кода. Перечень — после первого «:» за датой, до первой «.» вне
  «…» (точка между цифрами — часть номера); элементы через «;»: «шаг N» / «шаг №N» /
  «шаги N, M», «раздел «X»», «строка «X»».
- Снятие — вырезкой из текста источника группы ДО всех сверок: строки названного фрагмента
  заменяются пустыми (число строк сохраняется), проверки о заметке не знают. Литерал, который
  есть вне снятого, остаётся в сверке сам собой; номера шагов не сдвигаются.
  Шаг — от объявления «Шаг N» до следующего объявления или заголовка верхнего уровня (тот же
  разбор, что у сверки тел шагов). Раздел — md-заголовок с этим именем (без номера, разметки,
  регистра и «:» на конце) до следующего заголовка того же или старшего уровня. Строка —
  строка HTML-таблицы (<tr>…</tr>, в том числе на нескольких строках файла) или pipe-таблицы,
  у которой текст первой ячейки без тегов, разметки, регистра и «:» на конце равен имени.
- Абзац заметки «Не перенесено … санкционированное отклонение …» вырезается из текстов
  карточек группы перед сверкой: ни его «шаг 0», ни его цитаты потерю не закрывают.
- Видимость: на группу — строка «предупреждение: санкционированное отклонение …» с элементами
  как в заметке, числом вырезанных строк по каждому и числом исключённых литералов и теговых
  упоминаний; группа без ✗ получает знак ⚠ (selfcheck), гейт переносит строку предупреждением.
  Не найденный элемент, шаг заметки, присутствующий в карточке, заметка без перечня, даты или
  слова «решение» — отдельные предупреждения, по ним ничего не снимается.
- «Исправлено как санкционированное отклонение …» (гомоглиф, опечатка) не разбирается.
- Без заметки ничего не вызывается: отчёт прежний до байта.

Слой — миграция: снятие действует только на сверку с выгрузкой."""
import html as _html
import re
from typing import Dict, List, Optional, Tuple

from ..html import _fm_body
from ..md import code_line_flags

DEVIATION_PREFIX = "предупреждение: санкционированное отклонение"

_SANCTIONED_RE = re.compile(r"санкционированн\w*\s+отклонени", re.I)
_NOT_MOVED_RE = re.compile(r"не\s+перенесен", re.I)
_DECISION_RE = re.compile(r"(?<![\w-])решени", re.I)
_DATE_RE = re.compile(r"(?<![\d.-])(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})(?![\d-])")
_EL_STEP_RE = re.compile(r"^шаг(?:и)?\s+(№?\s*\d+(?:\.\d+)*(?:\s*,\s*№?\s*\d+(?:\.\d+)*)*)$", re.I)
_EL_NAMED_RE = re.compile(r"^(раздел|строка)\s+«([^«»]+)»$", re.I)
_NUM_RE = re.compile(r"\d+(?:\.\d+)*")
_MD_HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_TR_RE = re.compile(r"<tr\b[^>]*>.*?</tr\s*>", re.I | re.S)
_CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]\s*>", re.I | re.S)


class Note:
    """Разобранная заметка: карточка, дата решения, элементы [(вид, значение, как записан)]."""

    def __init__(self, card: str, date: str, elements: List[Tuple[str, str, str]]):
        self.card, self.date, self.elements = card, date, elements


def _paragraphs(text: str) -> List[Tuple[int, int, str]]:
    """[(первая строка, последняя строка, текст)] абзацев вне блоков кода."""
    lines = text.splitlines()
    flags = code_line_flags(lines)
    out: List[Tuple[int, int, str]] = []
    start: Optional[int] = None
    for i, ln in enumerate(lines + [""]):
        inside = i < len(lines) and not flags[i] and ln.strip() != ""
        if inside and start is None:
            start = i
        elif not inside and start is not None:
            out.append((start, i - 1, " ".join(x.strip() for x in lines[start:i])))
            start = None
    return out


def _is_removal_note(par: str) -> bool:
    return bool(_SANCTIONED_RE.search(par) and _NOT_MOVED_RE.search(par))


def _list_text(par: str, date_end: int) -> Optional[str]:
    """Перечень: после первого «:» за датой до первой «.» вне «…» (точка между цифрами — номер)."""
    colon = par.find(":", date_end)
    if colon < 0:
        return None
    depth, buf = 0, []
    s = par[colon + 1:]
    for k, ch in enumerate(s):
        if ch == "«":
            depth += 1
        elif ch == "»":
            depth = max(0, depth - 1)
        elif ch == "." and depth == 0 and not (k > 0 and s[k - 1].isdigit()
                                                and k + 1 < len(s) and s[k + 1].isdigit()):
            return "".join(buf)
        buf.append(ch)
    return "".join(buf)


def parse_note(par: str) -> Optional[Tuple[str, List[Tuple[str, str, str]]]]:
    """(дата, элементы) или None — заметка без формулы, даты, слова «решение» или перечня."""
    if not (_SANCTIONED_RE.search(par) and _DECISION_RE.search(par)):
        return None
    dm = _DATE_RE.search(par)
    if not dm:
        return None
    lst = _list_text(par, dm.end())
    if not lst or not lst.strip():
        return None
    els: List[Tuple[str, str, str]] = []
    for raw in (x.strip() for x in lst.split(";")):
        if not raw:
            continue
        ms = _EL_STEP_RE.match(raw)
        if ms:
            els.extend(("шаг", n, raw) for n in _NUM_RE.findall(ms.group(1)))
            continue
        mn = _EL_NAMED_RE.match(raw)
        if mn:
            els.append((mn.group(1).lower(), mn.group(2).strip(), raw))
            continue
        return None   # нераспознанный элемент — перечень не разобран, ничего не снимается
    return (dm.group(1), els) if els else None


def find_notes(cards: List[Tuple[str, str]]) -> Tuple[List[Note], List[str]]:
    """(заметки с перечнем, предупреждения о заметках без перечня) по текстам карточек группы."""
    notes: List[Note] = []
    warns: List[str] = []
    for name, text in cards:
        for _a, _b, par in _paragraphs(text):
            if not _is_removal_note(par):
                continue
            parsed = parse_note(par)
            if parsed is None:
                warns.append(f"предупреждение: заметка об отклонении без перечня — из сверки ничего "
                             f"не снято ({name}: «{par[:90]}…»; форма: «Не перенесено как "
                             "санкционированное отклонение, решение <кого> <дата>: шаг N; раздел "
                             "«X»; строка «Y». …»)")
                continue
            notes.append(Note(name, parsed[0], parsed[1]))
    return notes, warns


def blank_notes(text: str) -> str:
    """Абзацы заметок «Не перенесено … санкционированное отклонение …» — пустыми строками."""
    pars = [(a, b) for a, b, par in _paragraphs(text) if _is_removal_note(par)]
    if not pars:
        return text
    lines = text.split("\n")
    for a, b in pars:
        for i in range(a, b + 1):
            lines[i] = "\r" if lines[i].endswith("\r") else ""
    return "\n".join(lines)


def _plain_name(v: str) -> str:
    v = _html.unescape(re.sub(r"<[^>]+>", " ", v))
    v = re.sub(r"\*\*|__|`", "", v)
    v = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s+", "", v)
    return re.sub(r"\s+", " ", v).strip().rstrip(":").strip().casefold()


def _body_start(text: str) -> int:
    body = _fm_body(text)
    return text[:len(text) - len(body)].count("\n") if body and text.endswith(body) else 0


def _step_spans(lines: List[str], start: int) -> Dict[str, List[Tuple[int, int]]]:
    from .card_steps import _STEP_DECL_RE, _TOP_HEADING_RE
    spans: Dict[str, List[Tuple[int, int]]] = {}
    cur: Optional[str] = None
    first = 0
    for i in range(start, len(lines) + 1):
        ln = lines[i] if i < len(lines) else None
        m = _STEP_DECL_RE.match(ln) if ln is not None else None
        top = ln is not None and _TOP_HEADING_RE.match(ln)
        if cur is not None and (ln is None or m or top):
            spans.setdefault(cur, []).append((first, i - 1))
            cur = None
        if m:
            cur, first = m.group(1), i
    return spans


def _section_spans(lines: List[str], start: int, name: str) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for i in range(start, len(lines)):
        m = _MD_HEAD_RE.match(lines[i])
        if not m or _plain_name(m.group(2)) != name:
            continue
        lvl, j = len(m.group(1)), i + 1
        while j < len(lines):
            mj = _MD_HEAD_RE.match(lines[j])
            if mj and len(mj.group(1)) <= lvl:
                break
            j += 1
        out.append((i, j - 1))
    return out


def _row_spans(text: str, start: int, name: str) -> List[Tuple[int, int, int, int]]:
    """[(смещение начала, смещение конца, первая строка, последняя строка)] строк таблиц."""
    out = []
    off0 = sum(len(x) + 1 for x in text.split("\n")[:start])
    for m in _TR_RE.finditer(text, off0):
        c = _CELL_RE.search(m.group(0))
        if c and _plain_name(c.group(1)) == name:
            out.append((m.start(), m.end(), text.count("\n", 0, m.start()),
                        text.count("\n", 0, m.end())))
    for i, ln in enumerate(text.split("\n")):
        if i < start or not ln.lstrip().startswith("|"):
            continue
        cells = ln.strip().strip("|").split("|")
        if cells and _plain_name(cells[0]) == name:
            off = sum(len(x) + 1 for x in text.split("\n")[:i])
            out.append((off, off + len(ln.rstrip("\r")), i, i))
    return out


def _counts(orig: str, pruned: str) -> Tuple[int, int]:
    from .card_clean import source_tag_mentions
    from .card_source import _quoted_occurrences
    lit = ({v for _m, v, _s, _e in _quoted_occurrences(orig)}
           - {v for _m, v, _s, _e in _quoted_occurrences(pruned)})
    men = set(source_tag_mentions(orig)) - set(source_tag_mentions(pruned))
    return len(lit), len(men)


def apply_notes(src_text: str, cards: List[Tuple[str, str]], card_steps: Optional[set] = None
                ) -> Tuple[str, List[str], bool]:
    """(источник без снятого, строки отчёта, снято ли что-нибудь). cards — [(имя, текст)]
    карточек группы; card_steps — номера шагов, объявленных в карточках группы (без заметок):
    шаг заметки, присутствующий в карточке, — предупреждение «заметка устарела»."""
    notes, report = find_notes(cards)
    if not notes:
        return src_text, report, False
    start = _body_start(src_text)
    lines = src_text.split("\n")
    steps = _step_spans(lines, start)
    text = src_text
    removed_any = False
    for note in notes:
        done: List[str] = []
        for kind, value, raw in note.elements:
            cut = 0
            if kind == "шаг":
                if card_steps and value in card_steps:
                    report.append(f"предупреждение: заметка об отклонении ({note.card}): шаг {value} "
                                  "есть в карточке — заметка устарела, шаг сверяется как прежде")
                    continue
                for a, b in steps.get(value, []):
                    for i in range(a, b + 1):
                        cut += lines[i].strip() != ""
                        lines[i] = ""
            elif kind == "раздел":
                for a, b in _section_spans(lines, start, _plain_name(value)):
                    for i in range(a, b + 1):
                        cut += lines[i].strip() != ""
                        lines[i] = ""
            else:   # строка таблицы
                cur = "\n".join(lines)
                spans = _row_spans(cur, start, _plain_name(value))
                for s, e, a, b in sorted(spans, reverse=True):
                    cut += sum(1 for x in cur[s:e].split("\n") if x.strip())
                    cur = cur[:s] + "\n" * cur.count("\n", s, e) + cur[e:]
                lines = cur.split("\n")
            if cut:
                done.append(f"{raw} (строк источника {cut})")
            else:
                report.append(f"предупреждение: заметка об отклонении ({note.card}): «{raw}» — в "
                              "источнике не найдено, по этому элементу ничего не снято")
        if done:
            removed_any = True
            text_now = "\n".join(lines)
            n_lit, n_men = _counts(text, text_now)
            text = text_now
            report.append(f"{DEVIATION_PREFIX} (решение {note.date}, {note.card}): снято из сверки — "
                          + "; ".join(done)
                          + f"; исключено литералов {n_lit}, теговых упоминаний {n_men}")
    return "\n".join(lines), report, removed_any
