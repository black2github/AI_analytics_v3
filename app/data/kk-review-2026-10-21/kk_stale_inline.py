# Пометки «нет целевого артефакта <тип> «имя» … требуется заход» в теле карточек КК:
# у скольких цель с таким title уже есть в комплекте (устаревшая пометка)
import re
from collections import Counter
from pathlib import Path

SRS = Path("C:/doc-as-code/EAS/src-business-cards/docs/srs")
titles = {}
for f in SRS.rglob("*.md"):
    m = re.search(r"^title:\s*'?(.*?)'?\s*$", f.read_text(encoding="utf-8", errors="replace"), re.M)
    if m:
        t = m.group(1).replace("''", "'")
        titles[re.sub(r"\s+", " ", t).strip().lower()] = f
        titles[re.sub(r"^\[[^\]]+\]\s*", "", re.sub(r"\s+", " ", t).strip().lower())] = f
RX = re.compile(r"нет целевого артефакта\s+([\w./-]+)(?:\s+«([^»]+)»)?[^)\n]*?требуется заход\s+([\w-]+)")
total = stale = 0
kinds = Counter()
ex = []
for f in SRS.rglob("*.md"):
    t = f.read_text(encoding="utf-8", errors="replace")
    for m in RX.finditer(t):
        total += 1
        kinds[m.group(3)] += 1
        name = (m.group(2) or "").strip().lower()
        if name and (name in titles or re.sub(r"^\[[^\]]+\]\s*", "", name) in titles):
            stale += 1
            if len(ex) < 8:
                ex.append(f"{f.relative_to(SRS).as_posix()}: «{m.group(2)}» → {titles.get(name, titles.get(re.sub(r'^\[[^\]]+\]\s*', '', name))).relative_to(SRS).as_posix()}")
print(f"пометок в теле: {total}; цель уже есть (по title): {stale}")
print("по скиллу дозахода:", dict(kinds.most_common(8)))
for e in ex:
    print("  ", e)
