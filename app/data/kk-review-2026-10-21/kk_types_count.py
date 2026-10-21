# Распространённость типов замечаний по комплекту КК (только чтение)
import re
import sys
from collections import defaultdict
from pathlib import Path

K = Path("C:/doc-as-code/EAS/src-business-cards")
SRS = K / "docs/srs"
files = sorted(SRS.rglob("*.md"))
res = defaultdict(list)


def sec(text, head_re):
    m = re.search(head_re, text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"^## ", rest, re.M)
    return rest[:n.start()] if n else rest


for f in files:
    t = f.read_text(encoding="utf-8", errors="replace")
    rel = f.relative_to(SRS).as_posix()
    typ = (re.search(r"^type:\s*(\S+)", t, re.M) or [None, ""])[1]
    title = (re.search(r"^title:\s*'?(.*?)'?\s*$", t, re.M) or [None, ""])[1]
    # Т1 кнопки без «При нажатии» при наличии шагов
    for m in re.finditer(r"^### B-\d+\..*?(?=^### |^## |\Z)", t, re.M | re.S):
        b = m.group(0)
        if re.search(r"Шаг\s*\d|\*\*Шаг", b) and "При нажатии" not in b:
            res["T1 кнопка: шаги без «При нажатии»"].append(rel)
            break
    # Т2 самодельные разделы «дефект»
    if re.search(r"^#{2,4} .*[Дд]ефектн", t, re.M):
        res["T2 раздел «Дефектн…» в карточке"].append(rel)
    # Т3 сообщения ЭФ списком, не таблицей
    if typ == "screen-form":
        s = sec(t, r"^## \d+\. Сообщения\s*$")
        if s and re.search(r"^- MSG-\d+", s, re.M) and not re.search(r"^\| *MSG-\d+", s, re.M):
            res["T3 сообщения ЭФ списком, не таблицей"].append(rel)
    # Т4 не-функция в function: СПП / параметры вызова / состав
    if typ == "function" and re.search(r"СПП|Параметры вызова|Состав подписываем", title):
        res["T4 function — на деле СПП/параметры вызова"].append(rel + " — " + title[:70])
    # Т5 перенесённые «копии»
    if re.match(r"(\[[^\]]*\] )?Копия", title):
        res["T5 перенесена страница-«Копия»"].append(rel)
    # Т6 карточка вызова не тонкая
    if typ == "contract-call" and re.search(r"^### (Атрибутный состав|Паспорт метода|Логика работы|Структура ответа)", t, re.M):
        res["T6 CALL не тонкая (паспорт/состав/логика)"].append(rel)
    # Т7 способ отображения в контроле
    if "/control/" in "/" + rel and "способ отображения" in t:
        res["T7 способ отображения в контроле"].append(f"{rel} ×{t.count('способ отображения')}")
    # Т8 «Вызов функции»: перечень без ссылок
    s = sec(t, r"^## \d+\. Вызов функции\s*$")
    items = re.findall(r"^\s*[-*] (.+)$", s, re.M)
    nolink = [i for i in items if "](" not in i]
    if len(nolink) >= 3:
        res["T8 «Вызов функции»: ≥3 пунктов без ссылок"].append(f"{rel} ({len(nolink)} из {len(items)})")
    # Т9 склейка «Тип(N)Текст» — потерянный перенос
    if re.search(r"\| *[А-Яа-яA-Za-z]+\(\d+(,\d+)?\)[А-ЯA-Z][а-яa-z]", t):
        res["T9 склейка типа «Строка(19)Допустимый…»"].append(rel)
    # Т10 строки паспорта вне таблицы («Где используется:» отдельным абзацем)
    if re.search(r"^(Где используется|Привилегии|Входящие параметры|Исходящие параметры):\s*$", t, re.M):
        res["T10 строка паспорта вне таблицы"].append(rel)
    # Т11 «нет целевого артефакта … требуется заход» в теле карточки
    n = len(re.findall(r"нет целевого артефакта[^)\n]*требуется заход", t))
    if n:
        res["T11 долг формы 1 текстом в теле"].append(f"{rel} ×{n}")

print(f"файлов SRS: {len(files)}")
for k in sorted(res):
    v = res[k]
    print(f"\n{k}: {len(v)}")
    for x in v[:12]:
        print("   ", x)
    if len(v) > 12:
        print(f"    … ещё {len(v) - 12}")
