# -*- coding: utf-8 -*-
from pathlib import Path
import re

client = Path(r"C:\repos\serv-migr\src-onb-v\srs\screen-form\client")
pat = re.compile(
    r"(Размерности и имена макетов \(URL Figma в комплект не переносятся\):\n\n.*?\n\n)"
    r"\n?Размерности и имена макетов \(URL Figma в комплект не переносятся\):\n\n.*?\n\n"
    r"(?=## 1\. )",
    re.S,
)
for p in sorted(client.glob("scr-cl-0*.md")):
    text = p.read_text(encoding="utf-8")
    new, count = pat.subn(r"\1", text, count=1)
    print(p.name, "count=", count)
    if count == 1:
        p.write_text(new, encoding="utf-8")
