# -*- coding: utf-8 -*-
"""Сборка производных документов (Вариант A) из debug/cs_rows.json.
BE: один многосущностный data-model файл, сквозные DM-NN, единые группы.
FE: отдельный screen-form файл на страницу (Первичный ввод данных, Анкеты, Подтверждение)."""
import json, re, os

OUTDIR = r"conf-requirements/cc/[КК]-Корпоративные-Карты/[КК_ВК]-Выпуск-корпоративной-карты/[КК_ВК]-Контроли-заявки-на-выпуск-карты-и-открытие-счета"
SRC = r"conf-requirements/cc/[КК]-Корпоративные-Карты/[КК_ВК]-Выпуск-корпоративной-карты/[КК_ВК]-Контроли-заявки-на-выпуск-карты-и-открытие-счета.md"
d = json.load(open("debug/cs_rows.json", encoding="utf-8"))

def extract_history(src_path):
    with open(src_path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"\*\*История изменений:\*\*\s*\n\n(\|.*?\|)\s*\n\n\*\*Описание:\*\*", text, re.S)
    if not m:
        return None
    return m.group(1).strip()

# --- порядок сущностей в BE (иерархия) ---
ENT_APP   = "Заявка на выпуск карты и открытие счета"
ENT_CARD  = "Выпускаемая карта"
ENT_HOLD  = "Держатель карты"
ENT_DOCA  = "Документы и вложения Заявки на выпуск карты и открытие счета"
ENT_DOCC  = "Документы и вложения Выпускаемой карты"
ENT_ORDER = [ENT_APP, ENT_CARD, ENT_HOLD, ENT_DOCA, ENT_DOCC]
# ссылки на сущности (относительные, как в исходнике)
ENT_LINK = {
 ENT_APP:  "[КК_ВК]-Модель-данных/[КК_ВК]-Заявка-на-выпуск-карты-и-открытие-счета.md",
 ENT_CARD: "[КК_ВК]-Модель-данных/[КК_ВК]-Заявка-на-выпуск-карты-и-открытие-счета/[КК_ВК]-Держатель-карты/[КК_ВК]-Выпускаемая-карта.md",
 ENT_HOLD: "[КК_ВК]-Модель-данных/[КК_ВК]-Заявка-на-выпуск-карты-и-открытие-счета/[КК_ВК]-Держатель-карты.md",
 ENT_DOCA: "[КК_ВК]-Модель-данных/[КК_ВК]-Заявка-на-выпуск-карты-и-открытие-счета/[КК_ВК]-Документы-и-вложения-Заявки-на-выпуск-карты-и-открытие-счета.md",
 ENT_DOCC: "[КК_ВК]-Модель-данных/[КК_ВК]-Заявка-на-выпуск-карты-и-открытие-счета/[КК_ВК]-Держатель-карты/[КК_ВК]-Выпускаемая-карта/[КК_ВК]-Документы-и-вложения-Выпускаемой-карты.md",
}

def norm_groups(g):
    out=[]
    for x in g:
        x=(x or "").replace("-","").strip()
        out.append("V" if "V" in x else "")
    return out

def block_entity(raw):
    if raw and raw.startswith("["):
        inner = raw[1:].split("](")[0]
    else:
        inner = raw or ""
    if inner.startswith("[КК_ВК] "): inner = inner[len("[КК_ВК] "):]
    return inner.strip()

# маркер: атрибут начинается с префикса сущности [[КК_ВК] X](link).
RE_PREFIX = re.compile(r'^\[\[КК_ВК\]\s*(?P<ent>[^\]]+?)\]\((?P<link>[^)]+)\)\.(?P<rest>.*)$', re.S)

def strip_angle(s):
    s=s.strip()
    # убрать только ВНЕШНИЕ треугольные скобки имени атрибута
    m=re.match(r'^<([^<>]+)>(.*)$', s, re.S)
    if m and not m.group(2).strip():
        return m.group(1).strip()
    # вложенные <A>.<B> -> A.B
    s2=re.sub(r'<([^<>]+)>', r'\1', s)
    return s2.strip()

# --- разбор строк, назначение сущности/класса ---
rows=[]
cur_block=None
for r in d:
    if r["type"]=="divider":
        cur_block=block_entity(r["entity"]); continue
    g=norm_groups(r["groups"])
    attr=r["attr"].strip()
    orig=r["orig"]
    name=r["name"].strip()
    logic=r["logic"].strip()
    msg=r["msg"].strip()
    is_aggregate=False; page=None; entity=None; field_name=attr
    # 1) агрегаты формы
    if attr.startswith("Обязательные поля") or attr.startswith("Наличие хотя бы") or attr.startswith("Количество"):
        is_aggregate=True
        if "Первичный-ввод-данных" in attr or "Первичный ввод" in attr: page="Первичный-ввод-данных"
        elif "страница-Анкеты" in attr or 'страница "Анкеты"' in attr or "Анкеты" in attr: page="Анкеты"
        elif "Подтверждение" in attr: page="Подтверждение"
        # имя поля-объекта формы — человекочитаемо, без markdown-ссылки
        prefix=re.split(r'\[\[?КК_ВК\]', attr)[0].strip()
        ptitle={"Первичный-ввод-данных":'Первичный ввод данных',"Анкеты":'Анкеты',"Подтверждение":'Подтверждение'}.get(page,'')
        if ptitle:
            connector=' странице ' if prefix.endswith('на') else ' страницы '
            field_name=f'{prefix}{connector}"{ptitle}"'.strip()
        else:
            field_name=re.sub(r'\s+',' ',prefix).strip() or attr
        # для orig 90 "Количество анкет" — это и правило кардинальности на Заявку
        if attr.startswith("Количество"):
            entity=ENT_APP
            field_name="Количество выпускаемых карт (анкет) в заявке"
    else:
        m=RE_PREFIX.match(attr)
        if m:
            entity=m.group("ent").strip()
            field_name=strip_angle(m.group("rest").strip())
        else:
            entity=cur_block
            field_name=strip_angle(attr)
    rows.append(dict(orig=orig, entity=entity, page=page, is_agg=is_aggregate,
                     field=field_name, name=name, logic=logic, msg=msg, g=g, block=cur_block))

# нормализация имени сущности к каноническим
def canon_entity(e):
    if not e: return None
    e=e.strip()
    if e.startswith("Заявка"): return ENT_APP
    if e.startswith("Выпускаемая"): return ENT_CARD
    if e.startswith("Держатель"): return ENT_HOLD
    if e.startswith("Документы и вложения Заявки"): return ENT_DOCA
    if e.startswith("Документы и вложения Выпускаемой"): return ENT_DOCC
    if e.startswith("Другое"): return ENT_APP
    return e
for r in rows:
    r["entity"]=canon_entity(r["entity"])

# --- классификация ---
DM_GR=[0,1,2,3,4,7,8,9]   # 7? нет: 7 — форменный. backend-группы:
DM_GR=[0,1,2,3,4,8,9]
SF_GR=[5,6,7]
def anyV(g,idxs): return any(g[i]=="V" for i in idxs)

def is_rule(logic, name):
    t=logic+" "+name
    if "](" in logic: return True  # ссылка на справочник/сущность/внешний док
    for kw in ["Справочник","Клиент Банка","ЕСК","РКО","БСК","соглашени","полномочи",
               "другой","эндпоинт","endpoint","сущност","Организац"]:
        if kw.lower() in t.lower(): return True
    return False

# DM-записи: всё, что помечено backend-группой ИЛИ вне матрицы со ссылкой/правилом; кроме чистых агрегатов формы
dm_rows=[]
for r in rows:
    if r["is_agg"] and not r["orig"]=="90":
        continue  # агрегаты формы — только в FE
    backend = anyV(r["g"], DM_GR)
    no_groups = not any(x=="V" for x in r["g"])
    if backend or (no_groups and is_rule(r["logic"], r["name"])):
        if r["entity"] is None: r["entity"]=ENT_APP
        dm_rows.append(r)

# сортировка DM по сущности (иерархия) с сохранением исходного порядка внутри
def ent_key(e):
    return ENT_ORDER.index(e) if e in ENT_ORDER else 99
dm_sorted=sorted(range(len(dm_rows)), key=lambda i:(ent_key(dm_rows[i]["entity"]), i))
dm_rows=[dm_rows[i] for i in dm_sorted]
for n,r in enumerate(dm_rows,1):
    r["dmid"]=f"DM-{n:02d}"
    r["type"]="rule" if is_rule(r["logic"], r["name"]) else "field"

# SF-записи: помечено форменной группой; страница по группе/агрегату
def sf_pages(r):
    pages=set()
    if r["is_agg"] and r["page"]:
        pages.add(r["page"]);
    if r["g"][5]=="V" or r["g"][6]=="V": pages.add("Первичный-ввод-данных")
    if r["g"][7]=="V": pages.add("Анкеты")
    return pages
PAGE_TITLE={"Первичный-ввод-данных":'Первичный ввод данных',"Анкеты":'Анкеты',"Подтверждение":'Подтверждение'}
PAGE_LINK={
 "Первичный-ввод-данных":'[КК_ВК]-Экранные-формы/[КК_ВК]-ЭФ-Клиента/[КК_ВК]-ЭФ-Клиента-Заявка-на-выпуск-карты-и-открытие-счета-в-режиме-созданияредактирования/[КК_ВК]-ЭФ-Клиента-страница-Первичный-ввод-данных.md',
 "Анкеты":'[КК_ВК]-Экранные-формы/[КК_ВК]-ЭФ-Клиента/[КК_ВК]-ЭФ-Клиента-Заявка-на-выпуск-карты-и-открытие-счета-в-режиме-созданияредактирования/[КК_ВК]-ЭФ-Клиента-страница-Анкеты.md',
 "Подтверждение":'[КК_ВК]-Экранные-формы/[КК_ВК]-ЭФ-Клиента/[КК_ВК]-ЭФ-Клиента-Заявка-на-выпуск-карты-и-открытие-счета-в-режиме-созданияредактирования/[КК_ВК]-ЭФ-Клиента-страница-Подтверждение.md',
}
sf_by_page={k:[] for k in PAGE_TITLE}
for r in rows:
    pages=sf_pages(r)
    # агрегат Подтверждение (217) попадает по page даже без формогруппы
    if r["is_agg"] and r["page"]=="Подтверждение": pages.add("Подтверждение")
    for p in pages:
        sf_by_page[p].append(r)
sf_counter={k:0 for k in PAGE_TITLE}
for p in PAGE_TITLE:
    for r in sf_by_page[p]:
        sf_counter[p]+=1
        r.setdefault("sfid",{})[p]=f"SF-{sf_counter[p]:02d}"

def cell(s):
    s=(s or "").replace("|","\\|").replace("\n"," ")
    return re.sub(r"\s+"," ",s).strip()

# ---------- запись BE ----------
os.makedirs(OUTDIR, exist_ok=True)
be_path=os.path.join(OUTDIR, "[КК_ВК]-BE-Контроли-заявки-на-выпуск-карты-и-открытие-счета.md")
L=[]
L.append("---")
L.append("doc_id: '{{CC: [КК_ВК] BE Контроли заявки на выпуск карты и открытие счета}}'")
L.append("title: '[КК_ВК] BE Контроли заявки на выпуск карты и открытие счета'")
L.append("description: 'Контроли, оперирующие атрибутами сущностей модели данных заявки на выпуск карты (Заявка, Выпускаемая карта, Держатель карты, Документы и вложения): обязательность, формат, справочники, межатрибутные и межсистемные правила. Зона 1 — публичный контракт, проецируется в OpenAPI через x-controls.'")
L.append("doc_type: requirement")
L.append("requirement_type: control")
L.append("control_kind: data-model")
L.append("service_code: CC")
L.append("source: CONFLUENCE")
L.append("confluence_page_id: '42674834'")
L.append("status: draft")
L.append("version: 1.0.0")
L.append("related: '{{CC:[КК_ВК] FE Контроли ЭФ Клиента страница Первичный ввод данных}}, {{CC:[КК_ВК] FE Контроли ЭФ Клиента страница Анкеты}}, {{CC:[КК_ВК] FE Контроли ЭФ Клиента страница Подтверждение}}'")
L.append("tags: [control, data-model, backend]")
L.append("---")
L.append("")
hist = extract_history(SRC)
if hist:
    L.append("**История изменений:**")
    L.append("")
    L.append(hist)
    L.append("")
L.append(f"> **Зона 1 (публичный контракт).** Эти проверки оперируют **атрибутами сущностей** заявки на выпуск карты — [[КК_ВК] {ENT_APP}]({ENT_LINK[ENT_APP]}) и связанной иерархии (Выпускаемая карта → Держатель карты → Документы и вложения). Выполняются сервисом при изменении статуса заявки в её жизненном цикле. Парные FE-документы описывают проверки полей экранных форм; одно и то же значение может проверяться и там, и здесь — это осознанное дублирование (форма — ранняя реакция, сервис — гарантия).")
L.append("")
L.append("## Назначение")
L.append("")
L.append("Контроли заявки на выпуск корпоративной карты и открытие счёта, оперирующие атрибутами сущностей модели данных и выполняемые при изменении статуса заявки. Применяются при создании/сохранении (DRAFT/NEW), импорте реестра держателей, подписании и ФЛК при приёме в банк.")
L.append("")
L.append("## Группы триггеров")
L.append("")
L.append("Группа — событие жизненного цикла, при котором запускается подмножество проверок. «V» на пересечении проверки и группы означает её выполнение при наступлении события. Группы **сквозные по всему документу** (одна сущность не порождает собственных групп — триггер проверяет все сущности, помеченные группой). Группы 5–7 — события экранных форм, вынесены в парные FE-документы.")
L.append("")
GR_DESC={
 0:"контроли, обязательные для сохранения заявки в статусе **DRAFT**.",
 1:"контроли, обязательные для сохранения заявки в статусе **NEW**.",
 2:'контроли по реквизитам, заполняемым данными из ЕСК, при нажатии «Подписать и отправить» — **до** проверки полномочий пользователя на подпись.',
 3:"контроли ФЛК в рамках приёма и проверки заявки в банк (шаг №2 процесса).",
 4:"контроли ФЛК при импорте реестра держателей карт (включая проверки структуры файла реестра).",
 8:"контроли загружаемых в заявку файлов со сканом ДУЛ (см. [[КК_ВК] Контроли приложенных документов]([КК_ВК]-Контроли-приложенных-документов.md)).",
 9:"контроли реквизитов держателя после поиска сотрудника через [[КК_ВК] Алгоритм поиска сотрудника Клиента] (см. [[КК_ВК] Контроли данных держателя карты]([КК_ВК]-Контроли-данных-держателя-карты.md)).",
}
for gi in [0,1,2,3,4,8,9]:
    L.append(f"- **Группа №{gi}** — {GR_DESC[gi]}")
L.append("")
L.append("## Контроли заявки")
L.append("")
L.append("`ID` — стабильный сквозной идентификатор; `Ориг.` — исходный № Confluence-страницы; `Тип` — `field` (автономное ограничение значения атрибута) или `rule` (нужен контекст: межатрибутное / справочник / другая сущность / внешняя система / полномочия).")
L.append("")
DM_COLS=[0,1,2,3,4,8,9]
hdr="| ID | Ориг. | Тип | Проверяемый атрибут | Название проверки | Условие | Сообщение об ошибке | "+" | ".join(f"Гр.{i}" for i in DM_COLS)+" |"
sep="|----|-------|-----|---------------------|-------------------|---------|---------------------|"+"".join(":--:|" for _ in DM_COLS)
for ent in ENT_ORDER:
    block=[r for r in dm_rows if r["entity"]==ent]
    if not block: continue
    L.append(f"### [КК_ВК] {ent}")
    L.append("")
    L.append(hdr); L.append(sep)
    for r in block:
        gv=" | ".join("V" if r["g"][i]=="V" else "" for i in DM_COLS)
        note="⚠️ вне групповой матрицы — выполняется по факту события; " if not any(x=='V' for x in r['g']) else ""
        L.append(f"| {r['dmid']} | {cell(r['orig'])} | {r['type']} | {cell(r['field'])} | {cell(r['name'])} | {note}{cell(r['logic'])} | {cell(r['msg'])} | {gv} |")
    L.append("")
# связь с openapi
L.append("## Связь с OpenAPI")
L.append("")
L.append("Операции жизненного цикла заявки ссылаются на этот документ через `x-controls`, указывая группу проверок. Все операции используют один `source`; различается только `group`. Стабильна структура `ControlViolation` (`code` + `message`), не наполнение.")
L.append("")
L.append("```yaml")
L.append("# POST /business-cards/request/card-issue/save  — создание/сохранение (DRAFT/NEW)")
L.append("post:")
L.append("  operationId: createOrUpdate_1")
L.append("  summary: Создать/обновить заявку на выпуск карты")
L.append("  x-controls:")
L.append('    source: "{{CC:[КК_ВК] BE Контроли заявки на выпуск карты и открытие счета}}"')
L.append("    group: [0, 1]")
L.append("---")
L.append("# POST /business-cards/request/card-issue/process-holder-list  — импорт реестра держателей")
L.append("post:")
L.append("  operationId: processExcelAndSaveRequestOnIssueCard")
L.append("  summary: Обогащение заявки данными из файла реестра держателей")
L.append("  x-controls:")
L.append('    source: "{{CC:[КК_ВК] BE Контроли заявки на выпуск карты и открытие счета}}"')
L.append("    group: 4")
L.append("---")
L.append("# POST /business-cards/request/card-issue/sign  — подписание / ФЛК")
L.append("post:")
L.append("  operationId: sign_1")
L.append("  summary: Подписать заявку на выпуск карты")
L.append("  x-controls:")
L.append('    source: "{{CC:[КК_ВК] BE Контроли заявки на выпуск карты и открытие счета}}"')
L.append("    group: [2, 3, 9]")
L.append("```")
L.append("")
L.append("> Группа 8 (контроли файлов со сканом ДУЛ) проецируется операцией загрузки/прикрепления документов к заявке; см. парный документ контролей приложенных документов.")
L.append("")
open(be_path,"w",encoding="utf-8").write("\n".join(L))

# ---------- запись FE ----------
def write_fe(page):
    rs=sf_by_page[page]
    if not rs: return None
    title=PAGE_TITLE[page]; link=PAGE_LINK[page]
    fname=f"[КК_ВК]-FE-Контроли-ЭФ-Клиента-страница-{page}.md"
    path=os.path.join(OUTDIR,fname)
    cols=[5,6] if page=="Первичный-ввод-данных" else ([7] if page=="Анкеты" else [])
    F=[]
    F.append("---")
    F.append(f"doc_id: '{{{{CC: [КК_ВК] FE Контроли ЭФ Клиента страница {title}}}}}'")
    F.append(f"title: '[КК_ВК] FE Контроли ЭФ Клиента: страница \"{title}\"'")
    F.append("description: 'Контроли, оперирующие полями экранной формы (обязательность полей страницы, формат и подтверждение полей при вводе). В OpenAPI не проецируются.'")
    F.append("doc_type: requirement")
    F.append("requirement_type: control")
    F.append("control_kind: screen-form")
    F.append("service_code: CC")
    F.append("source: CONFLUENCE")
    F.append("confluence_page_id: '42674834'")
    F.append("status: draft")
    F.append("version: 1.0.0")
    F.append("related: '{{CC:[КК_ВК] BE Контроли заявки на выпуск карты и открытие счета}}'")
    F.append("tags: [control, screen-form, frontend, ux]")
    F.append("---")
    F.append("")
    F.append(f"> **Зона 3.** Эти проверки оперируют **полями экранной формы** [[КК_ВК] ЭФ Клиента: страница \"{title}\"]({link}). Значения полей формы не обязаны совпадать с атрибутами сущности ни по составу, ни по реализации. В OpenAPI не проецируются — гарантия целостности лежит на проверках сущностей ([[КК_ВК] BE Контроли заявки на выпуск карты и открытие счета]([КК_ВК]-BE-Контроли-заявки-на-выпуск-карты-и-открытие-счета.md)). Часть полей проверяется и здесь, и в сущности — это осознанное дублирование.")
    F.append("")
    F.append("## Назначение")
    F.append("")
    F.append(f"Контроли полей страницы [[КК_ВК] ЭФ Клиента: страница \"{title}\"]({link}) формы заявки на выпуск карты, выполняемые на клиенте при работе с формой.")
    F.append("")
    F.append("## Группы триггеров")
    F.append("")
    if page=="Первичный-ввод-данных":
        F.append('- **Группа №5** — переход со страницы «Первичный ввод данных» на страницу «Анкеты» по кнопке «Продолжить».')
        F.append('- **Группа №6** — то же, если отметка «Открыть новый счёт» установлена в положение «Вкл».')
    elif page=="Анкеты":
        F.append('- **Группа №7** — переход со страницы «Анкеты» на страницу «Подтверждение» по кнопке «Продолжить».')
    else:
        F.append('- Страница «Подтверждение» завершается действием «Подписать и отправить» (серверное событие — см. BE-документ, группа 2). Отдельной группы-перехода формы у страницы нет; перечисленные ниже проверки выполняются при покидании страницы/подписании.')
    F.append("")
    F.append("## Контроли заявки")
    F.append("")
    F.append("`ID` — стабильный сквозной идентификатор; `Ориг.` — исходный № Confluence-страницы.")
    F.append("")
    if cols:
        gh=" | ".join(f"Гр.{i}" for i in cols)
        gsep="".join(":--:|" for _ in cols)
        F.append(f"| ID | Ориг. | Поле / объект формы | Название проверки | Условие | Сообщение об ошибке | {gh} |")
        F.append(f"|----|-------|---------------------|-------------------|---------|---------------------|{gsep}")
    else:
        F.append("| ID | Ориг. | Поле / объект формы | Название проверки | Условие | Сообщение об ошибке |")
        F.append("|----|-------|---------------------|-------------------|---------|---------------------|")
    for r in rs:
        sid=r["sfid"][page]
        if cols:
            gv=" | ".join("V" if r["g"][i]=="V" else "" for i in cols)
            F.append(f"| {sid} | {cell(r['orig'])} | {cell(r['field'])} | {cell(r['name'])} | {cell(r['logic'])} | {cell(r['msg'])} | {gv} |")
        else:
            F.append(f"| {sid} | {cell(r['orig'])} | {cell(r['field'])} | {cell(r['name'])} | {cell(r['logic'])} | {cell(r['msg'])} |")
    F.append("")
    open(path,"w",encoding="utf-8").write("\n".join(F))
    return (fname,len(rs))

made=[]
for p in ["Первичный-ввод-данных","Анкеты","Подтверждение"]:
    res=write_fe(p)
    if res: made.append(res)

print(f"BE: {os.path.basename(be_path)}  | DM-записей={len(dm_rows)}")
from collections import Counter
ec=Counter(r['entity'] for r in dm_rows)
for e in ENT_ORDER:
    if ec[e]: print(f'    {ec[e]:>3}  {e}')
print("FE:")
for fn,n in made: print(f'    {n:>3}  {fn}')
