# app/scripts/CI/kitcheck/checks/card_notification.py
"""Проверки карточки: уведомления.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
import re
from typing import Dict, List, Tuple


# Нотификации (тип notification): внутренняя согласованность карточки.
# Составной ключ «канал, получатели»: подраздел канала у события
# (#### <ключ>) обязан иметь карточку канала (### <ключ>) в разделе
# «Каналы и адреса доставки» — инцидент [КК_ВК]: канал «Уведомление в
# Экосистеме» использовался событиями, но в разделе каналов страницы
# отсутствовал. Плюс: упомянутый общий шаблон M-NN обязан существовать,
# E-номера событий монотонны (append-only, как OQ).
_NTF_EVENT_H_RE = re.compile(r"^###\s+NTF-\d+\.E(\d+)\.", re.M)
_NTF_TMPL_REF_RE = re.compile(r"общ\w+\s+шаблон\w*\s+(M-\d+)", re.I)
_NTF_TMPL_H_RE = re.compile(r"^###\s+(M-\d+)\.", re.M)
# заголовок-ключ — с фиксированным префиксом (решение пользователя
# 2026-08-15: префикс — «привязка к местности», показывает, что карточка
# разворачивает строку реестра; в ячейках реестров ключи без префикса)
_NTF_KEY_PREFIX_RE = re.compile(r"^Канал и получатели:\s*")


def _ntf_key(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def check_notification_structure(card_text: str) -> Tuple[List[str], bool]:
    """Согласованность карточки нотификаций; на прочих типах молчит
    (срабатывает только при обоих обязательных разделах шаблона)."""
    sections: Dict[str, List[str]] = {}
    current = ""
    for ln in card_text.splitlines():
        if ln.startswith("## ") and not ln.startswith("###"):
            current = _ntf_key(ln[3:])
            sections.setdefault(current, [])
        elif current:
            sections[current].append(ln)
    chan_lines = sections.get("Каналы и адреса доставки")
    evt_lines = sections.get("Сообщения нотификации")
    if chan_lines is None or evt_lines is None:
        return [], True
    report: List[str] = []
    ok = True
    unprefixed: List[str] = []

    def _keys(lines: List[str], marker: str) -> List[str]:
        out = []
        for ln in lines:
            if not ln.startswith(marker):
                continue
            raw = _ntf_key(ln[len(marker):])
            m = _NTF_KEY_PREFIX_RE.match(raw)
            if m:
                out.append(_ntf_key(raw[m.end():]))
            else:
                unprefixed.append(raw)
        return out

    chan_keys = set(_keys(chan_lines, "### "))
    evt_keys = _keys(evt_lines, "#### ")
    if unprefixed:
        report.append("нотификации: заголовок-ключ без префикса "
                      "«Канал и получатели: »: "
                      + "; ".join(unprefixed[:5]) + " ✗")
        ok = False
    missing = sorted({k for k in evt_keys if k not in chan_keys})
    if missing:
        report.append("нотификации: ключ «канал, получатели» события без "
                      "карточки в «Каналы и адреса доставки»: "
                      + "; ".join(missing[:5])
                      + " ✗ — карточку не синтезировать, нужен открытый "
                        "вопрос по источнику")
        ok = False
    tmpl_defined = set(_NTF_TMPL_H_RE.findall(card_text))
    tmpl_missing = sorted({m for m in _NTF_TMPL_REF_RE.findall(card_text)
                           if m not in tmpl_defined})
    if tmpl_missing:
        report.append("нотификации: упомянутый общий шаблон отсутствует: "
                      + ", ".join(tmpl_missing[:5]) + " ✗")
        ok = False
    e_raw = _NTF_EVENT_H_RE.findall(card_text)
    e_nums = [int(m) for m in e_raw]
    bad = [(a, b) for a, b in zip(e_nums, e_nums[1:]) if b <= a]
    if bad:
        report.append("нотификации: E-номера событий не монотонны "
                      "(append-only): "
                      + ", ".join(f"E{b:02d} после E{a:02d}"
                                  for a, b in bad[:3]) + " ✗")
        ok = False
    narrow = sorted({m for m in e_raw if len(m) < 2})
    if narrow:
        report.append("нотификации: формат E-номера — минимум две цифры "
                      "(E01…): " + ", ".join(f"E{m}" for m in narrow[:5])
                      + " ✗")
        ok = False
    # ссылка-заглушка [текст](#): суррогатный href вместо правила трёх
    # случаев (карточка в комплекте → относительная ссылка; иначе голый
    # текст + долг); финальный прогон locks 2026-08-15
    stubs = card_text.count("](#)")
    if stubs:
        report.append(f"нотификации: ссылка-заглушка «](#)» ({stubs} шт.) "
                      "✗ — по правилу трёх случаев: относительная ссылка "
                      "на карточку комплекта или голый текст + долг")
        ok = False
    # <br>-простыня: текст сообщения перенесён одной строкой из ячейки
    # источника вместо построчного разворачивания (рендеримость; в
    # таблицах (строки на «|») <br> легален — реестр событий)
    flat = [ln for ln in evt_lines
            if "<br>" in ln and not ln.lstrip().startswith("|")]
    if flat:
        report.append(f"нотификации: <br> вне таблиц в «Сообщения "
                      f"нотификации» ({len(flat)} строк) ✗ — тексты "
                      "разворачиваются построчно (правило шаблона)")
        ok = False
    if ok:
        report.append(f"нотификации: ключи каналов ({len(chan_keys)}), "
                      f"шаблоны, порядок событий ({len(e_nums)}) "
                      "согласованы ✓")
    return report, ok
