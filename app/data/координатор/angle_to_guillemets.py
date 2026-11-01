# -*- coding: utf-8 -*-
r"""Нормализация нотации атрибута: `[Сущность](…).<Атрибут>` → `[Сущность](…).«Атрибут»`
(нотация техбука §7, conventions §5). Только позиция после `).` — ссылка на сущность/форму;
подстановки в дословных текстах (угловые скобки не после `).`) не трогаются.
Экранированная форма `.\<Атрибут\>` обрабатывается так же. HTML-теги (`<br>`, `<u>`…) не трогаются.
Блоки кода (```…```) пропускаются. EOL и кодировка файла сохраняются; неизменённый файл не перезаписывается.

Запуск:  python angle_to_guillemets.py --root <клон КК> [--write]
Без --write — сухой прогон: число файлов и вхождений.
"""
import argparse
import re
import sys
from pathlib import Path

HTML_TAGS = {"br", "u", "b", "i", "s", "p", "sup", "sub", "code", "span", "div", "a",
             "em", "strong", "tr", "td", "th", "table", "ul", "ol", "li", "hr", "img"}

# `).` + необязательный `\` + `<` + имя + необязательный `\` + `>`
PAT = re.compile(r"(\)\.)\\?<([^<>\n]{1,120}?)\\?>")


def _repl(m: "re.Match") -> str:
    inner = m.group(2).strip()
    if not inner or inner.split()[0].lower().strip("/") in HTML_TAGS:
        return m.group(0)
    if not re.match(r"[A-Za-zА-Яа-яЁё0-9]", inner):
        return m.group(0)
    return f"{m.group(1)}«{inner}»"


def process(text: str):
    out, n, fence = [], 0, False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
            out.append(line)
            continue
        if fence:
            out.append(line)
            continue
        cnt = [0]

        def _r(m, cnt=cnt):
            r = _repl(m)
            if r != m.group(0):
                cnt[0] += 1
            return r
        out.append(PAT.sub(_r, line))
        n += cnt[0]
    return "\n".join(out), n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    root = Path(a.root)
    scope = [root / "docs"]
    files, hits = 0, 0
    for base in scope:
        for p in sorted(base.rglob("*.md")):
            raw = p.read_bytes()
            text = raw.decode("utf-8")
            new, n = process(text)
            if n:
                files += 1
                hits += n
                if a.write and new != text:
                    p.write_bytes(new.encode("utf-8"))
    print(f"{'записано' if a.write else 'сухой прогон'}: файлов {files}, вхождений {hits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
