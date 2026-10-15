# -*- coding: utf-8 -*-
"""Stage 4: build SCR-CL cards from normalized sidecars (UTF-8)."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(r"C:\repos\serv-migr\src-onb-v")
NORM = ROOT / "sandbox" / "normalized"
OUT = ROOT / "srs" / "screen-form" / "client"
CAT = ROOT / "srs" / "screen-form"

SCR01, SCR02, SCR03, SCR04 = (
    "scr-cl-01-org-data.md",
    "scr-cl-02-org-data-no-dadata.md",
    "scr-cl-03-applicant.md",
    "scr-cl-04-phone-confirm.md",
)

T_ORG = '[ОНБ_В] ЭФ Клиента "Ввод данных организации/ИП с внешнего сайта"'
T_NODATA = (
    '[ОНБ_В] ЭФ Клиента "Ввод данных организации/ИП с внешнего сайта. '
    'Нет данных из DADATA"'
)
T_NODATA_CTL = (
    '[ОНБ_В] ЭФ Клиента "Ввод данных организации/ИП с внешнего сайта". '
    "Нет данных из DADATA"
)
T_APP = '[ОНБ_В] ЭФ Клиента "Ввод данных заявителя с внешнего сайта"'
T_PHONE = '[ОНБ_В] ЭФ Клиента "Подтверждение номера телефона"'

PLT = "../../platform-functions.md"
CALL = "../../contract-call/internal"
CTL = "../../control"
DM = "../../data-model/dictionaries.md"

L_PLT1 = (
    f"[PLT-001 Метод определения размерности экрана]"
    f"({PLT}#plt-001-метод-определения-размерности-экрана)"
)
L_PLT2 = (
    f"[PLT-002 ЭКО_Получение текста согласия]"
    f"({PLT}#plt-002-эко_получение-текста-согласия)"
)
L_PLT3 = (
    f"[PLT-003 Модальное окно «Первое место в рейтинге MW»]"
    f"({PLT}#plt-003-модальное-окно-первое-место-в-рейтинге-mw)"
)
L_CALL1 = (
    f"[CALL-INT-001 Сервис подсказки по организациям и ИП]"
    f"({CALL}/call-int-001-dadata-org-suggest.md)"
)
L_CALL2 = (
    f"[CALL-INT-002 [ОНБ_2021] Метод поиска заявки ОНБ по идентификатору CRM]"
    f"({CALL}/call-int-002-onb2021-find-request-by-crm-id.md)"
)
L_CALL3 = (
    f"[CALL-INT-003 [ОНБ_2021] Метод проверки возможности удалённого "
    f"открытия счёта]"
    f"({CALL}/call-int-003-onb2021-remote-account-open-check.md)"
)
L_CALL6 = (
    f"[CALL-INT-006 uaa/clientuser/register - Первоначальная регистрация "
    f"пользователя]({CALL}/call-int-006-uaa-clientuser-register.md)"
)
L_CALL7 = (
    f"[CALL-INT-007 uaa/clientuser/completeRegister - Завершение "
    f"регистрации пользователя]"
    f"({CALL}/call-int-007-uaa-clientuser-complete-register.md)"
)
L_CALL8 = (
    f"[CALL-INT-008 uaa/clientuser/renewConfirm - Повторная отправка кода "
    f"подтверждения]({CALL}/call-int-008-uaa-clientuser-renew-confirm.md)"
)
L_GRP1 = (
    f'[CTL-GRP-1 При нажатии кнопки "Открыть счёт"]({CTL}/README.md)'
)
L_GRP2 = (
    f'[CTL-GRP-2 При нажатии кнопки "Продолжить"]({CTL}/README.md)'
)
L_CTL009 = (
    f"[CTL-009 КПП: обязательность заполнения]"
    f"({CTL}/cards-org.md#ctl-009-кпп-обязательность-заполнения)"
)
L_DM = f"[настраиваемые параметры сервиса]({DM}#настраиваемые-параметры)"
L_DM_SRC = f"[[Настраиваемые параметры] ОНБ_В]({DM}#настраиваемые-параметры)"

LOGIC_LABELS = {
    "если", "то", "иначе", "иначе если", "или", "и", "е", "сли", "т", "о",
}

VIS_H = ("видимость", "отображение на эф")
FMT_H = (
    "формат", "формат отображения в поле", "формат отображения в списке",
    "placeholder", "пример отображения", "примеры значений", "пример значения",
    "отображения текста",
)
FILL_H = ("доступность на редактирование",)
OBL_H = ("обязательность заполнения",)
ACT_H = (
    "логика отображения модального окна по ссылке",
)
HDR_H = ("название поля на эф не отображается",)


def strip_bold(s: str) -> str:
    return re.sub(r"\*\*", "", s or "").strip()


def unwrap_links(s: str) -> str:
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "[":
            depth = 0
            j = i
            while j < len(s):
                if s[j] == "[":
                    depth += 1
                elif s[j] == "]":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j < len(s) and j + 1 < len(s) and s[j + 1] == "(":
                k = s.find(")", j + 2)
                if k != -1:
                    out.append(s[i + 1 : j])
                    i = k + 1
                    continue
        out.append(s[i])
        i += 1
    s = "".join(out)
    s = re.sub(r"https?://confluence[^\s)\"'<>]*", "", s)
    s = re.sub(r"https?://www\.figma\.com[^\s)\"'<>]*", "", s)
    s = s.replace("Cсылки на Figma", "")
    s = s.replace("Ссылки на Figma", "")
    return s


def apply_kit_links(s: str) -> str:
    s = re.sub(r"по кнопке\s+с \[", 'по кнопке "Назад" с [', s)
    pairs = [
        (T_NODATA, f"[{T_NODATA}]({SCR02})"),
        (T_ORG, f"[{T_ORG}]({SCR01})"),
        (T_APP, f"[{T_APP}]({SCR03})"),
        (T_PHONE, f"[{T_PHONE}]({SCR04})"),
        (
            "[ОНБ_2021] Метод поиска заявки ОНБ по идентификатору CRM",
            L_CALL2,
        ),
        (
            "[ОНБ_2021] Метод проверки возможности удалённого открытия счёта",
            L_CALL3,
        ),
        ("Сервис подсказки по организациям и ИП", L_CALL1),
        (
            "uaa/clientuser/completeRegister - Завершение регистрации "
            "пользователя",
            L_CALL7,
        ),
        (
            "uaa/clientuser/register - Первоначальная регистрация пользователя",
            L_CALL6,
        ),
        (
            "uaa/clientuser/renewConfirm - Повторная отправка кода "
            "подтверждения",
            L_CALL8,
        ),
        ("ЭКО_Получение текста согласия", L_PLT2),
        ('Модальное окно "Первое место в рейтинге MW"', L_PLT3),
        ("Модальное окно «Первое место в рейтинге MW»", L_PLT3),
        ("Метод определения размерности экрана", L_PLT1),
        ("[ОНБ_В] Группа контролей №1", L_GRP1),
        ("[ОНБ_В] Группа контролей №2", L_GRP2),
        ("[Настраиваемые параметры] ОНБ_В", L_DM_SRC),
    ]
    holders: list[str] = []
    for name, link in pairs:
        tok = f"\x00L{len(holders)}\x00"
        holders.append(link)
        s = s.replace(name, tok)
    for i, link in enumerate(holders):
        s = s.replace(f"\x00L{i}\x00", link)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"(<br>\s*){3,}", "<br><br>", s)
    return s.strip()


def clean(s: str) -> str:
    if not s:
        return s
    return apply_kit_links(unwrap_links(s))


def parse_tables(path: Path) -> dict[int, list[list[str]]]:
    text = path.read_text(encoding="utf-8")
    tables: dict[int, list[list[str]]] = {}
    parts = re.split(r"^## Таблица (\d+).*$", text, flags=re.M)
    it = iter(parts[1:])
    for n, body in zip(it, it):
        rows: list[list[str]] = []
        for ln in body.splitlines():
            if not ln.startswith("|"):
                continue
            inner = ln.strip().strip("|")
            if set(inner.replace("|", "").strip()) <= set("- "):
                continue
            rows.append([c.strip() for c in inner.split("|")])
        tables[int(n)] = rows
    return tables


def t0_map(rows: list[list[str]]) -> dict[str, str]:
    d: dict[str, str] = {}
    for r in rows:
        if len(r) < 2:
            continue
        d[strip_bold(r[0])] = r[1]
    return d


def t0_get(d: dict[str, str], *keys: str) -> str:
    for k, v in d.items():
        for want in keys:
            if want.lower() in k.lower():
                return v
    return ""


def type_canon(raw: str, fill: str) -> str:
    t = strip_bold(raw).lower()
    f = strip_bold(fill).lower()
    if "checkbox" in t or "логическ" in t:
        return "Чекбокс"
    if "графическ" in t or "картинк" in t or "изображен" in t:
        return "Изображение"
    if t.startswith("блок"):
        return ""
    if (
        "список" in t
        or "выбор" in f
        or "предикатив" in f
        or "списка" in f
    ):
        return "Список"
    return "Текст"


def fill_canon(raw: str) -> str:
    t = strip_bold(raw)
    if not t or t.startswith("Блок") or t.lower().startswith("см."):
        return ""
    low = t.lower()
    parts: list[str] = []
    if "автомат" in low:
        parts.append("Автоматически")
    if "ручн" in low:
        parts.append("Вручную")
    if "выбор" in low or "списк" in low or "предикатив" in low:
        parts.append("Выбор из списка")
    return " / ".join(parts) if parts else t


def is_block_row(name: str) -> bool:
    return strip_bold(name).startswith("Блок ")


def split_comment(comment: str) -> list[tuple[str | None, str]]:
    if not comment:
        return []
    chunks = re.split(r"<br>", comment)
    sections: list[tuple[str | None, str]] = []
    cur_h: str | None = None
    cur_b: list[str] = []

    def flush() -> None:
        nonlocal cur_h, cur_b
        if cur_h is not None or any(x.strip() for x in cur_b):
            sections.append((cur_h, "<br>".join(cur_b).strip()))
        cur_h, cur_b = None, []

    for ch in chunks:
        raw = ch.strip()
        m = re.match(r"^(\*\*[^*]{2,120}\*\*)\s*:?\s*(.*)$", raw)
        if m:
            label = strip_bold(m.group(1)).rstrip(":").strip()
            low = label.lower()
            if (
                low not in LOGIC_LABELS
                and not low.startswith(("если", "то", "иначе"))
                and not low.startswith("шаг")
            ):
                flush()
                cur_h = label
                if m.group(2).strip():
                    cur_b.append(m.group(2).strip())
                continue
        cur_b.append(ch)
    flush()
    return sections


def bucket_header(h: str | None) -> str:
    if not h:
        return "logic"
    k = h.lower().rstrip(":").strip()
    if k in VIS_H or k.startswith("отображение"):
        return "vis"
    if k in FMT_H or k.startswith("формат") or k.startswith("placeholder"):
        return "fmt"
    if k in FILL_H or k.startswith("доступность"):
        return "fillx"
    if k in OBL_H or k.startswith("обязательность"):
        return "obl"
    if k in ACT_H or "модального окна" in k or k.lower().startswith("по нажатию"):
        return "act"
    if k in HDR_H or "название поля на эф" in k:
        return "hdr"
    if "название блока" in k:
        return "skip"
    return "logic"


def fld_section(
    fid: str,
    name: str,
    typ: str,
    fill: str,
    obl: str,
    comment: str,
    *,
    kpp: bool = False,
) -> str:
    name = strip_bold(name)
    typ_c = type_canon(typ, fill)
    fill_c = fill_canon(fill)
    obl_s = strip_bold(obl)
    com = clean(comment)
    com = com.replace(
        'см. раздел "Правила формирования массива "Организации"" ниже',
        'см. [FF-1 «Правила формирования массива "Организации"»]'
        '(#ff-1-правила-формирования-массива-организации)',
    )
    bags: dict[str, list[str]] = {
        "vis": [], "fmt": [], "fillx": [], "obl": [], "act": [],
        "hdr": [], "logic": [],
    }
    for h, body in split_comment(com):
        b = bucket_header(h)
        if b == "skip":
            continue
        piece = body
        if h and b == "logic":
            piece = f"**{h}:** {body}".strip() if body else f"**{h}**"
        elif h and b == "fmt":
            if h.lower() in ("формат",):
                piece = body
            else:
                piece = f"**{h}:** {body}".strip() if body else f"**{h}**"
        elif h and b == "hdr":
            bags["hdr"].append(h)
            if body.strip().startswith("="):
                bags["logic"].append(body.strip())
            elif body.strip():
                bags["logic"].append(body.strip())
            continue
        elif h and b == "act":
            piece = f"**{h}:** {body}".strip() if body else h
        bags[b].append(piece)

    if name == "Баннер MW" and bags["vis"]:
        vis_j = "<br>".join(bags["vis"])
        if "По нажатию на баннер" in vis_j:
            pre, _, post = vis_j.partition("По нажатию на баннер")
            logic_i = pre.find("Кликабельный баннер")
            if logic_i >= 0:
                bags["vis"] = [pre[:logic_i].rstrip("<br> ")]
                bags["logic"].append(pre[logic_i:].strip())
            else:
                bags["vis"] = [pre.rstrip("<br> ")]
            bags["act"].append("По нажатию на баннер" + post)

    lines = [f"### {fid}. «{name}»", ""]
    if typ_c:
        lines.append(f"- **Тип:** {typ_c}")
    if bags["fmt"]:
        lines.append("- **Формат:** " + "<br>".join(bags["fmt"]))
    fill_bits = [x for x in [fill_c] if x]
    fill_bits.extend(bags["fillx"])
    if fill_bits:
        lines.append("- **Способ заполнения:** " + "<br>".join(fill_bits))
    if kpp:
        src = "<br>".join(bags["obl"]) if bags["obl"] else (
            "Да, **если** ЭФ.«ИНН» содержит 10 символов; **иначе** — Нет"
        )
        lines.append(
            f"- **Обязательность:** {src}. Проверка — {L_CTL009}."
        )
    elif obl_s.lower().startswith("см."):
        lines.append(f"- **Обязательность:** {clean(obl_s)}")
    elif obl_s == "Да":
        lines.append("- **Обязательность:** Да")
    elif obl_s == "Нет":
        lines.append("- **Обязательность:** Нет")
    elif obl_s and not obl_s.startswith("Блок"):
        lines.append(f"- **Обязательность:** {clean(obl_s)}")
    if bags["vis"]:
        lines.append("- **Видимость:** " + "<br>".join(bags["vis"]))
    if bags["logic"]:
        lines.append(
            "- **Логика установки значения:** " + "<br>".join(bags["logic"])
        )
    if bags["act"]:
        lines.append("- **Действие:** " + "<br>".join(bags["act"]))
    if bags["hdr"]:
        lines.append("- **Заголовок:** " + "<br>".join(bags["hdr"]))
    lines.append("")
    return "\n".join(lines)


def mockups() -> str:
    return (
        "**Макеты ЭФ** | XL, L, M, S, XS — макеты в src (Figma); URL в "
        f"комплект не переносятся. Размерность экрана — {L_PLT1}."
    )


def fm(sid: str, title: str, pid: str) -> str:
    return (
        f"---\n"
        f"id: {sid}\n"
        f"title: '{title}'\n"
        f"type: screen-form\n"
        f"service: onboarding-external\n"
        f"version: prod-2026-09\n"
        f"confluence_page_ids: ['{pid}']\n"
        f"---\n"
    )


def nav() -> str:
    return (
        "[комплект](../../../README.md) · "
        "[матрица](../../../traceability-matrix.md) · "
        "[экранные формы](../README.md)"
    )


def field_rows(rows: list[list[str]], phone: bool) -> list[list[str]]:
    if not rows:
        return []
    hdr = " ".join(rows[0]).lower()
    start = 1 if ("название" in hdr or "№" in rows[0][0]) else 0
    out = []
    for r in rows[start:]:
        if phone:
            r = (r + [""] * 6)[:6]
            out.append([r[0], r[1], r[2], r[3], r[4], r[5]])
        else:
            r = (r + [""] * 7)[:7]
            num = r[1] if len(r) > 1 else r[0]
            out.append([r[0], num, r[2], r[3], r[4], r[5], r[6]])
    return out


def block_for(name: str, current: str) -> str:
    if name in (
        "Баннер MW", "Заголовок", "Порядок открытия счета", "Информер",
        "Информация", "Код подтверждения", "Таймер",
    ) or name.startswith("Согласен"):
        return "—"
    if name in (
        "Сайт партнёра", "ID заявки на продажу в АС CRM Infor",
        "Удаленное открытие счета", "Заключение двустороннего ДБС",
        "Акция", "ID записи сведений по заявке во внешней системе",
    ):
        return "—"
    if name.startswith("Капча"):
        return "Блок прохождения капчи"
    if name in ("Фамилия", "Имя", "Отчество", "Мобильный телефон", "Email"):
        return "Блок регистрации пользователя клиента"
    if name in (
        "Краткое наименование", "Выберите организацию", "ИНН", "КПП",
        "Город обслуживания",
    ):
        return "Блок выбора организации"
    if name == "Тип счёта":
        return "Блок выбора типа счёта"
    return current if current != "—" else "—"


def obl_reg(obl: str, *, kpp: bool = False) -> str:
    s = strip_bold(obl)
    if kpp:
        return f"условно — {L_CTL009}"
    if s == "Нет":
        return "Нет"
    if s.lower().startswith("см."):
        return "условно — см. поле"
    if "см. описание" in s.lower():
        return f"условно — {L_CTL009}"
    return "Да"


def button_title(raw: str) -> str:
    t = unwrap_links(raw)
    t = strip_bold(t).strip().strip('"')
    t = re.sub(r"\s+", " ", t).strip()
    if not t or t in ("или",):
        return "Назад"
    if "Назад" in t:
        return "Назад"
    if "Обновить капчу" in t or t.startswith("(Обновить"):
        return "Обновить капчу"
    return t


def emit_buttons(rows: list[list[str]], phone: bool) -> tuple[str, int]:
    if not rows:
        return "", 0
    hdr = " ".join(rows[0]).lower()
    start = 1 if "название" in hdr or rows[0][0] in ("№", "**№**") else 0
    chunks: list[str] = []
    n = 0
    for r in rows[start:]:
        n += 1
        if phone:
            r = (r + [""] * 6)[:6]
            title = button_title(r[1])
            desc = clean(r[4])
            vis = clean(r[5])
        else:
            r = (r + [""] * 4)[:4]
            title = button_title(r[1])
            desc = clean(r[2] if len(r) > 2 else "")
            vis = clean(r[3] if len(r) > 3 else "Всегда")
        loc = ""
        if title in ("Обновить", "Вперед"):
            loc = " (кнопка браузера)"
        chunks.append(
            f"### B-{n}. «{title}»{loc}\n\n"
            f"- **Видимость:** {vis or 'всегда'}\n"
            f"- **При нажатии:** {desc}\n"
        )
    return "\n".join(chunks), n


def emit_browser(rows: list[list[str]], start_n: int) -> str:
    if not rows:
        return ""
    hdr = " ".join(rows[0]).lower()
    start = 1 if "название" in hdr else 0
    chunks = []
    n = start_n
    for r in rows[start:]:
        n += 1
        title = button_title(r[1] if len(r) > 1 else r[0])
        desc = clean(r[2] if len(r) > 2 else "")
        chunks.append(
            f"### B-{n}. «{title}» (кнопка браузера)\n\n"
            f"- **Видимость:** всегда (кнопка браузера)\n"
            f"- **При нажатии:** {desc}\n"
        )
    return "\n".join(chunks)


def build_fields(
    rows: list[list[str]], phone: bool
) -> tuple[str, str, int]:
    parsed = field_rows(rows, phone)
    reg = ["| № | Блок | Поле | Тип | Обяз. |", "|---|---|---|---|---|"]
    body: list[str] = []
    n_fld = 0
    block = "—"
    for r in parsed:
        if phone:
            num, name, typ, fill, obl, com = r
        else:
            _a, num, name, typ, fill, obl, com = r
        num = strip_bold(num)
        name = strip_bold(name)
        if is_block_row(name):
            block = name
            continue
        n_fld += 1
        fid = f"FLD-{n_fld}"
        kpp = name == "КПП"
        typ_c = type_canon(typ, fill) or "Текст"
        blk = block_for(name, block)
        reg.append(
            f"| {num} | {blk} | {fid} «{name}» | {typ_c} | "
            f"{obl_reg(obl, kpp=kpp)} |"
        )
        body.append(fld_section(fid, name, typ, fill, obl, com, kpp=kpp) + "\n")
    return "\n".join(reg), "".join(body), n_fld


def array_ff() -> str:
    raw = (NORM / "src-org.md").read_text(encoding="utf-8")
    i = raw.find("# Правила формирования массива")
    text = clean(raw[i:])
    text = text.replace(
        "# Правила формирования массива \"Организации\"",
        "",
        1,
    )
    return text.strip()


def write_card(
    *,
    sid: str,
    title: str,
    h1: str,
    pid: str,
    sidecar: str,
    fname: str,
    grp: str,
    skip_note: str,
    blocks: list[str],
    extra_ev_row: str,
    ev_detail: str,
    msgs: str,
    ff: str,
    phone: bool,
    purpose_keys: tuple[str, ...],
    how_keys: tuple[str, ...],
) -> None:
    tables = parse_tables(NORM / sidecar)
    t0 = t0_map(tables[0])
    purpose = clean(t0_get(t0, *purpose_keys))
    how = clean(t0_get(t0, *how_keys))
    extra = clean(t0_get(t0, "Дополнительн"))
    reg, flds, n_fld = build_fields(tables[1], phone)
    btns, bn = emit_buttons(tables.get(2, []), phone)
    if 3 in tables:
        btns = (btns + "\n" + emit_browser(tables[3], bn)).strip() + "\n"
    blk_md = "\n".join(f"- {b}" for b in blocks)
    grp_line = (
        f"Обязательность видимых полей проверяет {grp}. "
        if grp else ""
    )
    blk_line = "Видимость блоков — раздел 3; " if blocks else ""
    sec3 = (
        f"## 3. Видимость блоков\n\n{blk_md}\n\n"
        if blocks else ""
    )
    body = f"""{fm(sid, title, pid)}
# {h1}

{nav()}

{mockups()}

## 1. Назначение

{purpose}

**Как перейти:** {how}

{grp_line}{blk_line}правила полей — раздел 4 (FLD-N); открытие и реакции полей — раздел 5 (EV-N); кнопки — раздел 6 (B-N). Сущностей модели данных (`ENT`) в сервисе нет.

## 2. Реестр полей

{reg}

{skip_note}

{sec3}## 4. Правила полей

{flds}
## 5. События

| ID | Триггер | Суть реакции |
|---|---|---|
| EV-1 | Открытие формы | Дополнительные действия при открытии |
{extra_ev_row}

### EV-1. Открытие формы

{extra}

{ev_detail}

## 6. Кнопки

{btns}

{msgs}

{ff}
"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / fname).write_text(body, encoding="utf-8")
    print(f"wrote {fname} fld={n_fld}")


def write_readme() -> None:
    text = f"""---
id: SCR-000
title: 'Экранные формы'
type: screen-form
service: onboarding-external
version: prod-2026-09
---

# Экранные формы

[комплект](../../README.md) · [матрица](../../traceability-matrix.md)

Реестр экранных форм (ЭФ) сервиса — интерфейсов Клиента во внешней части сайта. Формы сгруппированы по контурам. В этом срезе банковского контура нет.

## Клиентский контур

| ID | Экранная форма | Файл |
|---|---|---|
| SCR-CL-01 | ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта» | [client/{SCR01}](client/{SCR01}) |
| SCR-CL-02 | ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA» | [client/{SCR02}](client/{SCR02}) |
| SCR-CL-03 | ЭФ Клиента «Ввод данных заявителя с внешнего сайта» | [client/{SCR03}](client/{SCR03}) |
| SCR-CL-04 | ЭФ Клиента «Подтверждение номера телефона» | [client/{SCR04}](client/{SCR04}) |

UI-вкладок формы не имеют: четыре отдельные страницы-источника — четыре карточки.

## Банковский контур

В срезе нет.

## Платформенные экраны

Универсальное модальное окно рейтинга MarksWebb — [PLT-003 Модальное окно «Первое место в рейтинге MW»](../platform-functions.md#plt-003-модальное-окно-первое-место-в-рейтинге-mw). Размерность экрана — [PLT-001 Метод определения размерности экрана](../platform-functions.md#plt-001-метод-определения-размерности-экрана).

## Как читать экранную форму

ЭФ описаны событийной моделью:

- **EV-N — событие**: открытие формы или реакция на изменение поля.
- **B-N — кнопка**: элемент управления и логика нажатия.
- **FLD-N — правило поля**: статика (тип, формат, заполнение, обязательность, видимость).
- **MSG-N — сообщение**: текст, показываемый пользователю.
- **FF-N — функция формы**: именованный набор шагов этой формы (массив «Организации»).

Проверки полей — в [контролях](../control/README.md). Сущностей модели данных (`ENT`) нет; параметры — в [справочниках](../data-model/dictionaries.md).

## Дерево

```
screen-form/
├── README.md
└── client/     → scr-cl-01…04
```
"""
    CAT.mkdir(parents=True, exist_ok=True)
    (CAT / "README.md").write_text(text, encoding="utf-8")
    print("wrote screen-form/README.md")


def wrap_in_file(path: Path, titles: list[tuple[str, str]]) -> int:
    text = path.read_text(encoding="utf-8")
    orig = text
    rel = Path(os.path.relpath(OUT, path.parent)).as_posix()
    for title, fname in titles:
        href = f"{rel}/{fname}"
        i = 0
        out: list[str] = []
        while True:
            j = text.find(title, i)
            if j < 0:
                out.append(text[i:])
                break
            after = j + len(title)
            lb = text.rfind("[", 0, j)
            rb = text.rfind("]", 0, j)
            in_label = lb > rb
            already = j > 0 and text[j - 1] == "[" and after < len(text) and text[after:after + 2] == "]("
            out.append(text[i:j])
            if already or in_label:
                out.append(title)
            else:
                out.append(f"[{title}]({href})")
            i = after
        text = "".join(out)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return 1
    return 0


def wrap_waiters() -> None:
    titles = [
        (T_NODATA, SCR02),
        (T_NODATA_CTL, SCR02),
        (T_ORG, SCR01),
        (T_APP, SCR03),
        (T_PHONE, SCR04),
    ]
    files = [
        ROOT / "srs" / "data-model" / "dictionaries.md",
        ROOT / "srs" / "control" / "README.md",
        ROOT / "srs" / "control" / "cards-org.md",
        ROOT / "srs" / "control" / "cards-applicant.md",
        ROOT / "srs" / "platform-functions.md",
        ROOT / "srs" / "contract-call" / "internal" / "README.md",
    ]
    files.extend((ROOT / "srs" / "contract-call" / "internal").glob("call-int-*.md"))
    n = 0
    for p in files:
        n += wrap_in_file(p, titles)
    print(f"wrapped waiters: {n} files changed")


def main() -> None:
    org_blocks = [
        "«Блок выбора организации» — название блока на ЭФ не отображается.",
        "«Блок выбора типа счёта» — название блока на ЭФ не отображается.",
    ]
    app_blocks = [
        "«Блок регистрации пользователя клиента» — название блока на ЭФ не отображается.",
        "«Блок прохождения капчи» — название блока на ЭФ не отображается.",
    ]
    org_ev2_row = (
        "| EV-2 | Изменение FLD «ИНН» (ввод/удаление 12-го символа) | "
        "Скрытие и очистка / показ FLD «КПП» |\n"
    )
    org_ev2_detail = (
        "### EV-2. Изменение поля «ИНН»\n\n"
        "Условие видимости FLD «КПП»: при введении 12-ого символа в поле "
        "ЭФ.«ИНН» поле ЭФ.«КПП» скрывается и **очищается**, при удаления "
        "12-ого символа в поле ЭФ.«ИНН» поле ЭФ.«КПП» отображается. "
        "Условие срабатывает в процессе редактирования поля ЭФ.«ИНН», "
        "потеря фокуса с поля ЭФ.«ИНН» не требуется.\n"
    )
    org_msg = f"""## 7. Сообщения

| ID | Тип | Показ | Содержание |
|---|---|---|---|
| MSG-1 | Модальное окно | EV-1, «Код ответа» = `"UNAVAILABLE"` | "Страница не найдена" (см. макет) |
| MSG-2 | Модальное окно | B «Открыть счёт», шаг 0 | заголовок: "Сервис недоступен иностранным юридическим лицам"; текст и кнопка "Понятно" — в шаге 0 кнопки |
| MSG-3 | Модальное окно | B «Войти в ГПБ Бизнес-Онлайн» | "Предупреждение об уходе": заголовок "Вы точно хотите уйти со страницы?"; текст и кнопки — в описании кнопки |

Тексты ошибок контролей не дублируются — в {L_GRP1}.
"""
    nodata_msg = f"""## 7. Сообщения

| ID | Тип | Показ | Содержание |
|---|---|---|---|
| MSG-1 | Модальное окно | B «Открыть счёт», шаг 0 | заголовок: "Сервис недоступен иностранным юридическим лицам"; текст и кнопка "Понятно" — в шаге 0 кнопки |
| MSG-2 | Модальное окно | B «Войти в ГПБ Бизнес-Онлайн» | "Предупреждение об уходе": заголовок "Вы точно хотите уйти со страницы?"; текст и кнопки — в описании кнопки |

Тексты ошибок контролей не дублируются — в {L_GRP1}.
"""
    app_msg = f"""## 7. Сообщения

| ID | Тип | Показ | Содержание |
|---|---|---|---|
| MSG-1 | Модальное окно | B «Войти в ГПБ Бизнес-Онлайн» | "Предупреждение об уходе": заголовок "Вы точно хотите уйти со страницы?"; текст и кнопки — в описании кнопки |
| MSG-2 | Сообщение на поле | B «Продолжить», шаг 2, системный код ошибки = 911 | "Неверный код" — на ЭФ.«Код с картинки» |

Тексты ошибок контролей не дублируются — в {L_GRP2}.

"""
    phone_msg = """## 7. Сообщения

| ID | Тип | Показ | Содержание |
|---|---|---|---|
| MSG-1 | Модальное окно | B «Войти в ГПБ Бизнес-Онлайн» | "Предупреждение об уходе": заголовок "Покинуть страницу?"; текст и кнопки — в описании кнопки |
| MSG-2 | Сообщение об ошибке | B «Условное продолжить», шаг 1.1 | сообщение, соответствующее значению «Системный код ошибки» ответа completeRegister |

"""
    org_ff = f"""
## 8. Функции формы

### FF-1. «Правила формирования массива "Организации"»

Вызов метода — {L_CALL1}; параметры запроса и разбор **suggestions** — в карточке вызова и в шагах ниже.

{array_ff()}
"""
    write_card(
        sid="SCR-CL-01", title=T_ORG,
        h1="ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта»",
        pid="2188264108", sidecar="src-org.md.tables.md", fname=SCR01,
        grp=L_GRP1,
        skip_note="Номера 0…7, 9…12 — как в источнике (номер 8 отсутствует).",
        blocks=org_blocks, extra_ev_row=org_ev2_row, ev_detail=org_ev2_detail,
        msgs=org_msg, ff=org_ff,
        phone=False, purpose_keys=("Назначение",), how_keys=("перейти",),
    )
    write_card(
        sid="SCR-CL-02", title=T_NODATA,
        h1="ЭФ Клиента «Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA»",
        pid="2188264123", sidecar="src-nodata.md.tables.md", fname=SCR02,
        grp=L_GRP1,
        skip_note="Номера 0…8, 10…12 — как в источнике (номер 9 отсутствует).",
        blocks=org_blocks, extra_ev_row=org_ev2_row, ev_detail=org_ev2_detail,
        msgs=nodata_msg, ff="",
        phone=False, purpose_keys=("Назначение",), how_keys=("перейти",),
    )
    write_card(
        sid="SCR-CL-03", title=T_APP,
        h1="ЭФ Клиента «Ввод данных заявителя с внешнего сайта»",
        pid="2188264146", sidecar="src-app.md.tables.md", fname=SCR03,
        grp=L_GRP2, skip_note="",
        blocks=app_blocks, extra_ev_row="", ev_detail="", msgs=app_msg, ff="",
        phone=False, purpose_keys=("Назначение",), how_keys=("перейти",),
    )
    write_card(
        sid="SCR-CL-04", title=T_PHONE,
        h1="ЭФ Клиента «Подтверждение номера телефона»",
        pid="2188264158", sidecar="src-phone.md.tables.md", fname=SCR04,
        grp="", skip_note="",
        blocks=[], extra_ev_row="", ev_detail="", msgs=phone_msg, ff="",
        phone=True, purpose_keys=("Назначение",), how_keys=("Переход", "перейти"),
    )
    write_readme()
    wrap_waiters()


if __name__ == "__main__":
    main()
