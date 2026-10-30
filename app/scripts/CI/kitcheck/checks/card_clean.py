# app/scripts/CI/kitcheck/checks/card_clean.py
"""Проверки карточки: чистовик — ссылки, упоминания, OQ и page_id в теле, формула ТУЗ.

Перенесено из `normalize_tables.py` дословно (Д-50, 2026-10-30); `normalize_tables`
сохраняет прежние имена (переходный реэкспорт на один релиз)."""
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
from .. import fs as _fs
from ..html import _fm_body, _fm_head
from .card_common import _norm_ws, blank_table_breaks


_OQ_PAGE_WORD_RE = re.compile(r"page[_ ]?id|confluence", re.I)
_OQ_PAGE_NUM_RE = re.compile(r"(?<![-\w.])\d{9,10}(?![-\w.])")


def check_oq_page_refs(md_path: Path) -> Tuple[List[str], bool]:
    """К-17 (2026-08-17): page_id в ТЕКСТАХ open-questions — носители
    page_id только frontmatter карточек и матрица; страница источника в
    OQ именуется title дословно + файлом выгрузки. ПРЕДУПРЕЖДЕНИЕ, не
    брак: легаси-фон старых записей (locks 23, file-storage 18 строк)
    вычищается при будущих касаниях, жёсткий брак заставил бы
    переписывать историю реестров разом (ужесточение — после вычистки
    фона, по механике серой зоны волны D)."""
    if not md_path.is_file():
        return [], True
    warns: List[str] = []
    for i, ln in enumerate(
            _fs.read_text(md_path, encoding="utf-8",
                              errors="replace").splitlines(), 1):
        if _OQ_PAGE_WORD_RE.search(ln) or _OQ_PAGE_NUM_RE.search(ln):
            warns.append(
                f"предупреждение: строка {i}: page_id/отсылка к Confluence "
                "в тексте реестра — страница источника именуется title + "
                f"файлом выгрузки: {ln.strip()[:60]!r}")
    return warns[:20], True


def check_service_table_integrity(md_path: Path) -> Tuple[List[str], bool]:
    """Структурная целостность таблиц СЛУЖЕБНОГО реестра (матрица,
    open-questions): только К-16 (разрывы пустой строкой) — колонные
    роли и литералы к реестрам не применяются (К-4)."""
    lines = _fs.read_text(md_path, encoding="utf-8").splitlines()
    breaks = blank_table_breaks(lines)
    if not breaks:
        return [], True
    return [f"строка {k}: пустая строка разрывает таблицу реестра — "
            "хвост рендерится плоским текстом ✗ НИЖЕ ПОРОГА"
            for k in breaks], False


# --- Сторож чистовика (волна D, Э-6) ---------------------------------
# Карточка комплекта не должна нести: битые относительные ссылки, ссылки
# вне docs/ (в т.ч. на выгрузку sources/), изображения, critic-маркеры,
# ссылки-заглушки «](#)». Внешние http(s) вне белого списка — ПРЕДУПРЕЖДЕНИЕ
# (софт-сигнал; решение аналитика 2026-08-17: фон не промерен — жёсткий
# брак спровоцировал бы агента «чинить» легитимные ссылки; ужесточение —
# после описи кросс-стендового прогона D4).
# figma.com — решение владельца 2026-08-29: URL макетов Figma обязаны
# переноситься (единственная связь аналитики с макетами)
# группы GitLab контура — адресаты межсервисных ссылок (документ адресации:
# базовые контракты EAN/docs-external-contracts, комплекты сервисов EAS/EAN,
# контракты API в ECO_BE/ms-<service-id>); до 2026-10-12 в списке был
# только техбук, и законные ссылки через HEAD давали ⚠ «вне белого списка»
# (отчёт FIN-01 lk-mp: 8 строк на docs-external-contracts)
_HTTP_WHITELIST = ("https://gitlab.gboteam.ru/ED/",
                   "https://gitlab.gboteam.ru/EAN/",
                   "https://gitlab.gboteam.ru/EAS/",
                   "https://gitlab.gboteam.ru/ECO_BE/",
                   "https://www.figma.com/")


def _md_link_targets(text: str) -> List[Tuple[int, str]]:
    """Адреса markdown-ссылок [текст](адрес) с позициями; скобки текста и
    адреса — балансом (те же инциденты, что у _strip_markdown_links)."""
    out: List[Tuple[int, str]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "[":
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j + 1 < n and text[j + 1] == "(":
            pdepth, k = 0, j + 1
            while k < n:
                if text[k] == "(":
                    pdepth += 1
                elif text[k] == ")":
                    pdepth -= 1
                    if pdepth == 0:
                        break
                k += 1
            if k < n:
                out.append((i, text[j + 2:k].strip()))
                i = k + 1
                continue
        i = j + 1
    return out



def _allowed_kit_roots(docs_root: Path,
                       allow_sibling_docs: bool = False) -> List[Path]:
    """Корни, внутри которых разрешены относительные ссылки чистовика.

    По умолчанию — только переданный корень комплекта. С `allow_sibling_docs` —
    также соседние пакеты того же монорепо, у которых есть `srs/` или `brd/`
    (топология ЦР: `<repo>/<service-id>/`).
    """
    root = docs_root.resolve()
    roots: List[Path] = [root]
    if not allow_sibling_docs:
        return roots
    if (root / 'srs').is_dir() or (root / 'brd').is_dir():
        monorepo = root.parent
    elif root.name == 'docs':
        monorepo = root.parent.parent
    else:
        monorepo = root.parent
    if not monorepo.is_dir():
        return roots
    for sibling in sorted(monorepo.iterdir()):
        if not sibling.is_dir():
            continue
        try:
            if sibling.resolve() == root:
                continue
        except OSError:
            continue
        if (sibling / 'srs').is_dir() or (sibling / 'brd').is_dir():
            r = sibling.resolve()
            if r not in roots:
                roots.append(r)
    return roots


def _under_any_kit_root(resolved: Path, roots: List[Path]) -> bool:
    for r in roots:
        try:
            resolved.relative_to(r)
            return True
        except ValueError:
            continue
    return False


def check_clean_document(md_path: Path,
                         docs_root: Optional[Path] = None,
                         allow_sibling_docs: bool = False
                         ) -> Tuple[List[str], bool]:
    """Сторож чистовика: (а) битые относительные ссылки, (б) цели вне
    комплекта (при allow_sibling_docs — вне sibling-пакетов с srs|brd),
    (в) изображения, (г) critic-маркеры — брак; внешние http(s)
    вне белого списка — предупреждение (видимо и при ✓)."""
    from urllib.parse import unquote
    text = _fs.read_text(md_path, encoding="utf-8")
    report: List[str] = []
    ok = True
    # (г) critic-маркеры в чистовике — разметка правок источника
    for pat in ("{++", "{--", "{~~", 'class="critic-'):
        cnt = text.count(pat)
        if cnt:
            ok = False
            report.append(
                f"critic-маркер «{pat}» ×{cnt} в чистовике: разметка правок "
                "в карточку не переносится — переносится ЦЕЛЕВОЙ текст "
                "(правило create-artifact) ✗ НИЖЕ ПОРОГА")
    # (в) изображения: бинарники в комплект не переносятся
    cnt = len(re.findall(r"<img\b", text)) + len(re.findall(r"!\[", text))
    if cnt:
        ok = False
        report.append(
            f"изображение (<img>/![…]) ×{cnt} в чистовике: изображения в "
            "комплект не переносятся (факт макетов — строкой паспорта) "
            "✗ НИЖЕ ПОРОГА")
    # (а)/(б) ссылки
    warns: List[str] = []
    roots = (_allowed_kit_roots(docs_root, allow_sibling_docs)
             if docs_root is not None else [])
    scope_label = ("комплекта и sibling-пакетов (srs|brd)" if allow_sibling_docs
                   else "docs/")
    root = roots[0] if roots else None
    for pos, target in _md_link_targets(text):
        if not target or target == "#":
            ok = False
            report.append(
                f"ссылка-заглушка «](#)» (позиция {pos}): цель обязана "
                "существовать или ссылка снимается ✗ НИЖЕ ПОРОГА")
            continue
        if target.startswith("#"):
            continue  # внутрифайловый якорь: файловая часть отсутствует
        if target.startswith(("http://", "https://")):
            if not target.startswith(_HTTP_WHITELIST):
                warns.append(
                    f"предупреждение: внешняя ссылка вне белого списка — "
                    f"{target[:80]} (опись серой зоны; решение об "
                    "ужесточении — после кросс-стендового прогона)")
            continue
        if target.startswith("mailto:"):
            continue
        fpath = unquote(target.split("#", 1)[0])
        if not fpath:
            continue
        try:
            resolved = (md_path.parent / fpath).resolve()
        except OSError:
            resolved = None
        if resolved is None or not resolved.exists():
            ok = False
            report.append(
                f"битая относительная ссылка: {target[:80]} — цель не "
                "существует ✗ НИЖЕ ПОРОГА")
            continue
        if roots:
            if _under_any_kit_root(resolved, roots):
                pass
            else:
                # мини-комплект зоны «вне Экосистемы» рядом с docs/ — законная
                # цель карточки вызова (Д-46: контракт интерфейса модуля); это старое
                # место, переходный период — по Д-49 зона в docs/modules/<имя>/, и
                # ссылка туда — цель внутри комплекта, сюда не доходит
                allowed_modules = False
                if root is not None:
                    try:
                        resolved.relative_to((root.parent / "modules").resolve())
                        allowed_modules = True
                    except ValueError:
                        pass
                if allowed_modules:
                    continue
                ok = False
                report.append(
                    f"ссылка ведёт ВНЕ {scope_label}: {target[:80]} — карточки "
                    "ссылаются только внутрь комплекта и в мини-комплекты "
                    "modules/ (выгрузка/sources — источник, не цель) ✗ НИЖЕ ПОРОГА")
    return report + warns, ok


# --- сторож формулы ТУЗ (решение аналитика 2026-08-19) ---
#
# Правило и образец — шаблон function §2 «Доступность»; здесь третий
# элемент триады (правило+образец+сторож): без него правка шаблона не
# персистентна для дозаходов (прецедент rbac → К-27).

_TUZ_BOLD_RE = re.compile(r"\*\*[^*\n]*вызов с ТУЗ[^*\n]*\*\*", re.I)


def check_tuz_formula(card_text: str) -> Tuple[List[str], bool]:
    hits = _TUZ_BOLD_RE.findall(card_text)
    if not hits:
        return [], True
    return [f"формула ТУЗ обёрнута в жирный ×{len(hits)}: фиксированная "
            "формула доступности FUN-SYS пишется ОБЫЧНЫМ шрифтом "
            "(шаблон function §2, решение 2026-08-19) ✗ НИЖЕ ПОРОГА"], False


# --- сторож упоминаний целей (кандидат волны E, вытянут 2026-08-19) ---
#
# Инвариант контура: титул Confluence-страницы несёт квадратно-скобочный
# тег сервиса («[РРКО_ИПИ] …», «[ПЭД] …») — маркер упоминания цели сам
# ТЕГ, а не перечень известных имён (имена заранее не перечислимы).
# Требование: упоминание в теле карточки — ЛИБО markdown-ссылка на
# существующую карточку комплекта, ЛИБО долг в матрице трассировки.
# Слепые зоны (честно): упоминания без тега; коллективные долги матрицы
# со свободной формулировкой могут не совпасть с иглой — потому уровень
# ПРЕДУПРЕЖДЕНИЕ (⚠, вердикт не трогает): по асимметрии ошибок шум
# лучше молчаливой потери; ужесточение — после боевой статистики.

_MENTION_TAG_RE = re.compile(
    r"\[(?=[^\]\n]*[А-ЯЁA-Z])[А-ЯЁA-Z0-9_]{2,20}\]\s+(?=[«\"(А-ЯЁA-Z])")
# границы хвоста упоминания: конец строки/ячейки, жирный, кавычки,
# точка с пробелом, запятая, точка с запятой (внутренние скобки —
# часть титулов: «…(стейт-машина)» — НЕ граница)
_MENTION_END_RE = re.compile(r"\n|\||\*\*|[»\"”;,]|\.\s|&[a-z]+;?")
# &[a-z]+;? — HTML-сущность выгрузки (&lt;атрибут&gt; после имени):
# без границы игла несла хвост «.&lt» и упоминание не находилось
# (отчёт КК 2026-10-05: «[КК] ТЕССА_Входящие параметры &lt» ×5)


def _mention_core(tail: str) -> str:
    """Ядро имени цели после тега. Непарная закрывающая скобка режет
    хвост — упоминание жило в скобках источника («…(см. [ЦРМ] Ролевая
    модель клиента) и статусом…», ложняк STS-03 z03/z04); скобка ВНУТРИ
    имени («…(Блокировка/Закрытие…)») парна и не режет."""
    e = _MENTION_END_RE.search(tail)
    core = (tail[:e.start()] if e else tail).strip().rstrip(".,;:")
    p = core.find(")")
    if p != -1 and "(" not in core[:p]:
        core = core[:p].strip().rstrip(".,;:")
    return core

_TARGET_INDEX_CACHE: Dict[str, List[Tuple[str, str]]] = {}


def _blank_md_links(text: str) -> str:
    """Заменить спаны [текст](адрес) ЦЕЛИКОМ пробелами: ссылочное
    упоминание уже оформлено и сторожу не видно (в отличие от
    _strip_markdown_links, сохраняющего текст-название). Скобки —
    балансом (инциденты intc-014 / К-11)."""
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "[":
            out.append(text[i])
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j + 1 < n and text[j + 1] == "(":
            pdepth, k = 0, j + 1
            while k < n:
                if text[k] == "(":
                    pdepth += 1
                elif text[k] == ")":
                    pdepth -= 1
                    if pdepth == 0:
                        break
                k += 1
            if k < n:
                out.append(" " * (k + 1 - i))
                i = k + 1
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _docs_card_titles(docs_root: Path) -> List[Tuple[str, str]]:
    """[(title, отн. путь)] карточек комплекта с ТЕГОВЫМ титулом из
    frontmatter (без тега прозовые коллизии неизбежны — слепая зона).
    Кэш на процесс: селфчек зовёт по каждой карточке."""
    key = str(docs_root.resolve())
    if key in _TARGET_INDEX_CACHE:
        return _TARGET_INDEX_CACHE[key]
    out: List[Tuple[str, str]] = []
    for p in sorted(docs_root.rglob("*.md")):
        try:
            head = _fm_head(_fs.read_text(p, encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if not head:
            continue
        m = re.search(r"^title:\s*(.+)$", head, re.M)
        if not m:
            continue
        title = m.group(1).strip().strip("'\"").strip()
        if re.match(r"^\[[^\]]+\]\s+\S", title):
            out.append((title, str(p.relative_to(docs_root)).replace(
                "\\", "/")))
    _TARGET_INDEX_CACHE[key] = out
    return out


def check_target_mentions(card_text: str, md_path: Path,
                          docs_root: Path) -> Tuple[List[str], bool]:
    """Софт-сторож: теговые упоминания целей вне markdown-ссылок.
    Существующая карточка → «оформить ссылкой»; неизвестная цель без
    следа в матрице → «ссылка или долг». Вердикт не меняет (⚠)."""
    body = _fm_body(card_text)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    body = _blank_md_links(body)
    warns: List[str] = []
    # (а) дословные титулы существующих карточек вне ссылок
    try:
        self_rel = str(md_path.resolve().relative_to(
            docs_root.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        self_rel = ""
    # регистр и переносы строк СОХРАНЯЮТСЯ: теговый регекс различает
    # регистр, а \n — граница упоминания (схлопывание пробелов до скана
    # протаскивало хвост упоминания через заголовки соседних разделов);
    # титулы поперёк переносов ловятся паттерном с \s+ между словами
    flat = body
    titles = sorted(_docs_card_titles(docs_root),
                    key=lambda t: -len(t[0]))  # длинный титул раньше:
    # вложенный короткий не двоит счёт (вычёркивание по месту)
    for title, rel in titles:
        if rel == self_rel:
            continue
        pat = re.compile(
            r"\s+".join(re.escape(w) for w in title.split()), re.I)
        cnt = 0
        m = pat.search(flat)
        while m:
            cnt += 1
            flat = (flat[:m.start()] + " " * (m.end() - m.start())
                    + flat[m.end():])
            m = pat.search(flat)
        if cnt:
            warns.append(
                f"предупреждение: имя существующей карточки без ссылки — "
                f"«{title[:70]}» ×{cnt} → {rel} (упоминание оформляется "
                "markdown-ссылкой на карточку; ссылка НЕ конфликтует со "
                "сторожем теговых упоминаний — дефейс только у слов без "
                "тега ВНЕ ссылки)")
    # (б) остальные теговые упоминания: след в матрице обязателен
    matrix = docs_root / "traceability-matrix.md"
    try:
        mtext = _norm_ws(_fs.read_text(matrix, encoding="utf-8",
                                          errors="replace"))
    except OSError:
        mtext = ""
    seen: Dict[str, Tuple[str, int]] = {}
    for m in _MENTION_TAG_RE.finditer(flat):
        tail = flat[m.end():m.end() + 120]
        core = _mention_core(tail)
        if not core:
            continue
        # игла — БЕЗ тега, первые ≤3 слова: реестр ID и долги матрицы
        # пишут имена без тегов; свободные формулировки длиннее иглы
        words = core.split()
        needle = " ".join(words[:3]).casefold()
        mention = re.sub(r"\s+", " ",
                         flat[m.start():m.end()] + core)[:70]
        if needle in mtext:
            continue
        key, (mm, cnt) = needle, seen.get(needle, (mention, 0))
        seen[key] = (mm, cnt + 1)
    for needle, (mention, cnt) in sorted(seen.items()):
        warns.append(
            f"предупреждение: упоминание цели «{mention}» ×{cnt} — "
            "карточки в комплекте нет и следа в матрице не найдено: "
            "либо markdown-ссылка на карточку, либо долг в матрице "
            "(правило долгов канона)")
    return warns, True


# --- К-33 (2026-08-19): вложенные/обёрнутые markdown-ссылки ---
#
# След генераторных правок дозахода 5.5: скрипт массовой простановки
# ссылок оборачивал уже олинкованные упоминания второй раз
# («[[[[…] …](fun-cl-08…)]](fun-cl-08…)» в fun-sys-02 прошло ВСЕ
# сторожа — цели валидны, К-32 доволен) и вкладывал ссылку внутрь
# title. Инвариант: внутри текста-названия ссылки не бывает другой
# ссылки; ссылка не оборачивается в дополнительные квадратные скобки.
# Легитимно: скобочный ТЕГ в дисплее («[[РРКО_ИПИ] Имя](file.md)») —
# внешняя скобка там принадлежит самой ссылке, сосед-скобок нет.


def _link_spans(text: str) -> List[Tuple[int, int, str]]:
    """(начало, конец, текст-название) каждой ссылки [текст](адрес);
    скобки балансом; шаг на 1 символ при не-ссылке — иначе внутренняя
    ссылка в «[[x](y)]» пропускается."""
    out: List[Tuple[int, int, str]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "[":
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j + 1 < n and text[j + 1] == "(":
            pdepth, k = 0, j + 1
            while k < n:
                if text[k] == "(":
                    pdepth += 1
                elif text[k] == ")":
                    pdepth -= 1
                    if pdepth == 0:
                        break
                k += 1
            if k < n:
                out.append((i, k, text[i + 1:j]))
                i = k + 1
                continue
        i += 1
    return out


def check_nested_links(card_text: str) -> Tuple[List[str], bool]:
    bad: List[str] = []
    for start, end, disp in _link_spans(card_text):
        nested = bool(_link_spans(disp))
        wrapped = ((start > 0 and card_text[start - 1] == "[")
                   or (end + 1 < len(card_text)
                       and card_text[end + 1] == "]"))
        if nested or wrapped:
            frag = re.sub(r"\s+", " ", card_text[
                max(0, start - 1):end + 2])[:60]
            bad.append(frag)
    if not bad:
        return [], True
    return [f"К-33 вложенная/обёрнутая markdown-ссылка ×{len(bad)} "
            f"(фрагмент: …{bad[0]!r}…) — след генераторной правки: "
            "ссылка не вкладывается в текст другой ссылки и не "
            "оборачивается в скобки; оставить ОДНУ ссылку с дословным "
            "текстом ✗ НИЖЕ ПОРОГА"], False


# --- К-32 (2026-08-19): анти-дефейс теговых упоминаний источника ---
#
# Пилот-2: агент «погасил» предупреждения сторожа упоминаний удалением
# тегов из дословного текста («см в [РРКО_ИПИ] Методы» → «см в Методы»)
# — упоминание ушло из зоны видимости, дословность и трассировка
# потеряны, долгов ноль. Закон обходов: инвариант — теговое упоминание
# ИСТОЧНИКА (целевой вид) сохраняется в карточке: тег на месте ЛИБО
# упоминание внутри markdown-ссылки (в ссылке тег легитимно заменяется
# на ID карточки: «[ENT-001 Инкассовое…](…)»). Слова без тега вне
# ссылки = дефейс, брак (доказуем текстом карточки). Полное отсутствие
# упоминания — предупреждение (зона могла легитимно не переноситься).


def _md_link_texts(text: str) -> str:
    """Конкатенация текстов-названий всех markdown-ссылок (балансом,
    как _strip_markdown_links)."""
    parts: List[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "[":
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j + 1 < n and text[j + 1] == "(":
            pdepth, k = 0, j + 1
            while k < n:
                if text[k] == "(":
                    pdepth += 1
                elif text[k] == ")":
                    pdepth -= 1
                    if pdepth == 0:
                        break
                k += 1
            if k < n:
                parts.append(text[i + 1:j])
                i = k + 1
                continue
        i = j + 1
    return "\n".join(parts)


# YAML-блок в самом начале файла выгрузки: от первой строки «---» до
# ближайшей строки «---»; нет закрывающей строки — ничего не снимается
_SRC_FRONTMATTER_RE = re.compile(
    r"\A﻿?---[ \t]*\r?\n.*?^---[ \t]*\r?$\n?", re.S | re.M)


def check_source_tag_mentions(card_text: str, src_text: str,
                              docs_root: Optional[Path] = None
                              ) -> Tuple[List[str], bool]:
    """К-32: каждое теговое упоминание источника — в карточке с тегом
    или ссылкой; слова без тега вне ссылки = дефейс (✗), отсутствие —
    предупреждение (⚠, вердикт не трогает).

    Исключение (реестровая конвенция, прецедент README функций и
    матрицы): имя СУЩЕСТВУЮЩЕЙ карточки без тега легитимно, когда файл
    ссылается на файл этой карточки (реестры пишут имена без тегов со
    ссылкой рядом; ссылка с ID-переименованием «[FUN-CL-05 …]» дисплеем
    иглу не несёт). Цели БЕЗ карточки исключения не имеют.

    Frontmatter источника упоминаний не несёт (FB-10 «Корпоративных
    карт», 2026-10-05): это служебные поля выгрузки, а не текст
    страницы. Строка «doc_id: '{{код: [ТЕГ] Имя страницы}}'» давала
    упоминание с хвостом «}}'» — у имён до трёх слов игла несла мусор
    и предупреждение было неустранимым. Собственное имя страницы
    сторожит check_title (дословный title)."""
    plain = re.sub(r"<[^>]+>", " ", _SRC_FRONTMATTER_RE.sub("", src_text, 1))
    mentions: Dict[str, str] = {}  # игла (норм.) -> «[ТЕГ] ядро» для отчёта
    for m in _MENTION_TAG_RE.finditer(plain):
        tail = plain[m.end():m.end() + 120]
        core = _mention_core(tail)
        if not core:
            continue
        needle = _norm_ws(" ".join(core.split()[:3]))
        tag = plain[m.start():m.end()].strip()
        mentions.setdefault(needle, re.sub(r"\s+", " ", f"{tag} {core}")[:70])
    if not mentions:
        return [], True
    card_nolinks = _norm_ws(_blank_md_links(card_text))
    card_links = _norm_ws(_md_link_texts(card_text))
    # реестровое исключение: базовые имена файлов, на которые ссылается
    # карточка, и титулы существующих карточек без тега
    linked_names = {t.split("#", 1)[0].replace("\\", "/").rsplit("/", 1)[-1]
                    for _, t in _md_link_targets(card_text)}
    titled_cards = ([(t, r) for t, r in _docs_card_titles(docs_root)]
                    if docs_root is not None else [])
    report: List[str] = []
    ok = True
    for needle, shown in sorted(mentions.items()):
        if any(_norm_ws(t.split("]", 1)[-1]).startswith(needle)
               and r.rsplit("/", 1)[-1] in linked_names
               for t, r in titled_cards):
            continue  # имя существующей карточки, файл на неё ссылается
        # тег на месте: «[тег] игла» встречается вне ссылок или в ссылке
        tagged = _norm_ws(shown.split("]")[0] + "] " + needle)
        if tagged in card_nolinks or tagged in card_links:
            continue
        if needle in card_links:
            continue  # оформлено ссылкой (тег в ссылке легитимно → ID)
        if needle in card_nolinks:
            ok = False
            report.append(
                f"К-32 дефейс тегового упоминания источника: «{shown}» — "
                "в карточке те же слова БЕЗ тега вне ссылки: тег — часть "
                "дословного текста и трассировка; возврат тега + ссылка "
                "на карточку или долг в матрице ✗ НИЖЕ ПОРОГА")
        else:
            report.append(
                f"предупреждение: теговое упоминание источника «{shown}» "
                "в карточке не найдено — если зона переносилась, "
                "упоминание обязано сохраниться (тег/ссылка)")
    return report, ok


def _fc_nested_links(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # К-33 (2026-08-19): вложенные/обёрнутые ссылки — след генераторных
    # правок (двойная обёртка проходила все сторожа: цели валидны)
    nl_report, nl_ok = check_nested_links(text)
    report.extend(nl_report)
    ok = ok and nl_ok
    return report, ok


def _fc_oq_refs_in_body(fx: "_FileCtx") -> Tuple[List[str], bool]:
    text, = fx.text,
    report: List[str] = []
    ok = True
    # К-21 (2026-08-18): отсылка к OQ в ТЕЛЕ карточки — брак (правило
    # create-artifact «отсылок к OQ в документах не делай» было без
    # сторожа: дозаход 3.1 inkasso-run1 создал rbac-заглушку со
    # «см. OQ-014»; в экзамене такие снимали руками).
    oq_refs = re.findall(r"\bOQ-\d+\b", text)
    if oq_refs:
        ok = False
        report.append(
            f"отсылка к открытым вопросам в теле карточки ×{len(oq_refs)} "
            f"({', '.join(sorted(set(oq_refs))[:3])}) — судьба вопроса живёт "
            "в open-questions.md, документ на него не ссылается "
            "✗ НИЖЕ ПОРОГА")
    return report, ok
