# -*- coding: utf-8 -*-
"""Restore converter structure in SCR cards for isolated --check (stage 4)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, r"C:\repos\serv-migr\docs-o2new\_meta\tools")
from normalize_tables import (  # type: ignore
    heavy_source_cells,
    html_fragment_to_markdown,
    passport_cell_html,
    _md_profile,
)

ROOT = Path(r"C:\repos\serv-migr\src-onb-v")
CONF = (
    ROOT
    / "confluence"
    / "[ОНБ_В]-Сервис-открытия-1-го-счета-и-регистрации-клиента-во-внешней-части-сайта"
    / "[ОНБ_В]-Экранные-формы"
    / "[ОНБ_В]-ЭФ-Клиента"
)
CLIENT = ROOT / "srs" / "screen-form" / "client"

# Longest names first. Link text = source substring (probes stay intact).
WRAPS = [
    (
        '[ОНБ_В] ЭФ Клиента "Ввод данных организации/ИП с внешнего сайта. Нет данных из DADATA"',
        "scr-cl-02-org-data-no-dadata.md",
    ),
    (
        '[ОНБ_В] ЭФ Клиента "Ввод данных организации/ИП с внешнего сайта"',
        "scr-cl-01-org-data.md",
    ),
    (
        '[ОНБ_В] ЭФ Клиента "Ввод данных заявителя с внешнего сайта"',
        "scr-cl-03-applicant.md",
    ),
    (
        '[ОНБ_В] ЭФ Клиента "Подтверждение номера телефона"',
        "scr-cl-04-phone-confirm.md",
    ),
    (
        "[Настраиваемые параметры] ОНБ_В",
        "../../data-model/dictionaries.md#настраиваемые-параметры",
    ),
    (
        "[ОНБ_2021] Метод поиска заявки ОНБ по идентификатору CRM",
        "../../contract-call/internal/call-int-002-onb2021-find-request-by-crm-id.md",
    ),
    (
        "[ОНБ_2021] Метод проверки возможности удалённого открытия счёта",
        "../../contract-call/internal/call-int-003-onb2021-remote-account-open-check.md",
    ),
    (
        "Сервис подсказки по организациям и ИП",
        "../../contract-call/internal/call-int-001-dadata-org-suggest.md",
    ),
    (
        "Метод определения размерности экрана",
        "../../platform-functions.md#plt-001-метод-определения-размерности-экрана",
    ),
    (
        "ЭКО_Получение текста согласия",
        "../../platform-functions.md#plt-002-эко_получение-текста-согласия",
    ),
    (
        'Модальное окно "Первое место в рейтинге MW"',
        "../../platform-functions.md#plt-003-модальное-окно-первое-место-в-рейтинге-mw",
    ),
]


def wrap_names(md: str) -> str:
    for name, href in WRAPS:
        out: list[str] = []
        i = 0
        nlen = len(name)
        while True:
            j = md.find(name, i)
            if j < 0:
                out.append(md[i:])
                break
            already = j > 0 and md[j - 1] == "[" and md.find("](", j) == j + nlen
            longer_prefix = any(
                longer != name and longer.startswith(name) and md.startswith(longer, j)
                for longer, _ in WRAPS
            )
            if already or longer_prefix:
                out.append(md[i:j + nlen])
                i = j + nlen
                continue
            out.append(md[i:j])
            out.append(f"[{name}]({href})")
            i = j + nlen
        md = "".join(out)
    return md


def layout_blocks(src: str) -> str:
    chunks: list[str] = []
    for cell in heavy_source_cells(src):
        md = html_fragment_to_markdown(cell)
        prof = _md_profile(md.splitlines())
        if len(prof) < 3:
            continue
        head = md.lstrip()[:40].lower()
        if head.startswith("перейти") or head.startswith("- **если**") or head.startswith("**шаг"):
            continue
        chunks.append(md.strip())
    return "\n\n".join(chunks)


def replace_how(card: str, how_md: str) -> str:
    how_md = wrap_names(how_md).strip()
    new = f"**Как перейти:**\n\n{how_md}"
    pat = re.compile(
        r"\*\*Как перейти:\*\*.*?(?=\n\n(?:Обязательность|Правила полей))",
        re.S,
    )
    if not pat.search(card):
        raise SystemExit("how-to block not found")
    return pat.sub(new, card, count=1)


def replace_ev1(card: str, open_md: str) -> str:
    open_md = wrap_names(open_md).strip()
    pat = re.compile(
        r"(### EV-1\. Открытие формы\n\n)(.*?)(?=\n### EV-2|\n## 6\. )",
        re.S,
    )
    if not pat.search(card):
        raise SystemExit("EV-1 block not found")
    return pat.sub(rf"\1{open_md}\n\n", card, count=1)


def insert_layouts(card: str, layouts: str) -> str:
    if not layouts.strip():
        return card
    if "Размерности и имена макетов" in card:
        return card
    marker = "**Макеты ЭФ** |"
    i = card.find(marker)
    if i < 0:
        raise SystemExit("passport layouts line not found")
    nl = card.find("\n", i)
    block = (
        "\n\nРазмерности и имена макетов (URL Figma в комплект не переносятся):\n\n"
        + layouts.strip()
        + "\n"
    )
    return card[:nl] + block + card[nl:]


def patch_01(card: str, src: str) -> str:
    how = html_fragment_to_markdown(passport_cell_html(src, "Как перейти") or "")
    opn = html_fragment_to_markdown(
        passport_cell_html(src, "Дополнительные действия при открытии") or ""
    )
    card = replace_how(card, how)
    card = replace_ev1(card, opn)
    card = insert_layouts(card, layout_blocks(src))
    card = card.replace(
        "| 3.3 | Блок выбора организации | FLD-6 «КПП» | Текст | условно — [CTL-009 КПП: обязательность заполнения](../../control/cards-org.md#ctl-009-кпп-обязательность-заполнения) |",
        "| 3.3 | Блок выбора организации | FLD-6 «КПП» | Текст | см. описание поля |",
        1,
    )
    return card


def patch_02(card: str, src: str) -> str:
    how = html_fragment_to_markdown(passport_cell_html(src, "Как перейти") or "")
    opn = html_fragment_to_markdown(
        passport_cell_html(src, "Дополнительные действия при открытии") or ""
    )
    card = replace_how(card, how)
    card = replace_ev1(card, opn)
    card = insert_layouts(card, layout_blocks(src))
    card = card.replace(
        "| 3.3 | Блок выбора организации | FLD-6 «КПП» | Текст | условно — [CTL-009 КПП: обязательность заполнения](../../control/cards-org.md#ctl-009-кпп-обязательность-заполнения) |",
        "| 3.3 | Блок выбора организации | FLD-6 «КПП» | Текст | см. описание поля |",
        1,
    )
    browser = """
### B-3. «Обновить» (кнопка браузера)

- **Видимость:** всегда (кнопка браузера)
- **При нажатии:** Осуществляется переход на [[ОНБ_В] ЭФ Клиента "Ввод данных организации/ИП с внешнего сайта"](scr-cl-01-org-data.md)

### B-4. «Вперед» (кнопка браузера)

- **Видимость:** всегда (кнопка браузера)
- **При нажатии:** Аналогично действиям по нажатию кнопки ЭФ "Открыть счёт"

"""
    if "### B-3. «Обновить»" not in card:
        card = card.replace("\n## 7. Сообщения", browser + "\n## 7. Сообщения", 1)
    return card


def patch_03(card: str, src: str) -> str:
    how = html_fragment_to_markdown(passport_cell_html(src, "Как перейти") or "")
    opn = html_fragment_to_markdown(
        passport_cell_html(src, "Дополнительные действия при открытии") or ""
    )
    card = replace_how(card, how)
    card = replace_ev1(card, opn)
    card = insert_layouts(card, layout_blocks(src))
    card = card.replace(
        "| 4.1 | Блок прохождения капчи | FLD-9 «Капча (ввод)» | Текст | условно — см. поле |",
        "| 4.1 | Блок прохождения капчи | FLD-9 «Капча (ввод)» | Текст | — |",
        1,
    )
    card = card.replace(
        "| 4.2 | Блок прохождения капчи | FLD-10 «Капча (информер)» | Текст | условно — см. поле |",
        "| 4.2 | Блок прохождения капчи | FLD-10 «Капча (информер)» | Текст | — |",
        1,
    )
    card = card.replace(
        "| 4.3 | Блок прохождения капчи | FLD-11 «Капча (отображение)» | Изображение | условно — см. поле |",
        "| 4.3 | Блок прохождения капчи | FLD-11 «Капча (отображение)» | Изображение | — |",
        1,
    )
    if "[ОНБ_В] Группа контролей №2" not in card:
        card = card.replace(
            'Осуществляется выполнение контролей "[CTL-GRP-2 При нажатии кнопки "Продолжить"](../../control/README.md)"',
            'Осуществляется выполнение контролей "[ОНБ_В] Группа контролей №2" ([CTL-GRP-2 При нажатии кнопки "Продолжить"](../../control/README.md))',
            1,
        )
    browser = """
### B-4. «Обновить» (кнопка браузера)

- **Видимость:** всегда (кнопка браузера)
- **При нажатии:** Осуществляется переход на [[ОНБ_В] ЭФ Клиента "Ввод данных организации/ИП с внешнего сайта"](scr-cl-01-org-data.md)

### B-5. «Вперед» (кнопка браузера)

- **Видимость:** всегда (кнопка браузера)
- **При нажатии:** Аналогично действиям по нажатию кнопки ЭФ "Продолжить"

"""
    if "### B-4. «Обновить»" not in card:
        card = card.replace("\n## 7. Сообщения", browser + "\n## 7. Сообщения", 1)
    return card


def patch_04(card: str, src: str) -> str:
    how = html_fragment_to_markdown(passport_cell_html(src, "Переход на ЭФ") or "")
    opn = html_fragment_to_markdown(
        passport_cell_html(src, "Дополнительные действия при открытии") or ""
    )
    card = replace_how(card, how)
    card = replace_ev1(card, opn)
    card = insert_layouts(card, layout_blocks(src))
    return card


SPECS = [
    (
        CLIENT / "scr-cl-01-org-data.md",
        CONF / "[ОНБ_В]-ЭФ-Клиента-Ввод-данных-организацииИП-с-внешнего-сайта.md",
        patch_01,
    ),
    (
        CLIENT / "scr-cl-02-org-data-no-dadata.md",
        CONF
        / "[ОНБ_В]-ЭФ-Клиента-Ввод-данных-организацииИП-с-внешнего-сайта.-Нет-данных-из-DADATA.md",
        patch_02,
    ),
    (
        CLIENT / "scr-cl-03-applicant.md",
        CONF / "[ОНБ_В]-ЭФ-Клиента-Ввод-данных-заявителя-с-внешнего-сайта.md",
        patch_03,
    ),
    (
        CLIENT / "scr-cl-04-phone-confirm.md",
        CONF / "[ОНБ_В]-ЭФ-Клиента-Подтверждение-номера-телефона.md",
        patch_04,
    ),
]


def main() -> None:
    for card_path, src_path, fn in SPECS:
        src = src_path.read_text(encoding="utf-8")
        card = card_path.read_text(encoding="utf-8")
        new = fn(card, src)
        card_path.write_text(new, encoding="utf-8")
        print("patched", card_path.name, "delta", len(new) - len(card))


if __name__ == "__main__":
    main()
