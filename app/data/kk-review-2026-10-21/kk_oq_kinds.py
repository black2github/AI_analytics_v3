# Раскладка незакрытых OQ КК по видам (эвристика по заголовку и полю «Вопрос»)
import re
from collections import Counter, defaultdict
from pathlib import Path

t = Path("C:/doc-as-code/EAS/src-business-cards/open-questions.md").read_text(encoding="utf-8")
parts = re.split(r"^(?=## OQ-\d+)", t, flags=re.M)[1:]
KINDS = [
    ("потеря: не перенесено / алгоритм / пропуск", r"не перенесен|не перенесён|пропущен|потер|не мигрир"),
    ("дефект источника (опечатки, пусто, противоречие)", r"дефект\w* (текста|источник|выгрузк)|опечатк|противореч|рассогласован|пуст\w* ячейк|легаси"),
    ("цель/дозаход: нет артефакта, долг", r"нет целевого|долг|дозаход|требуется заход|вне комплекта|вне входа|вне плана"),
    ("классификация / тип / размещение", r"классификац|тип\b|не data-model|разбивк|гранулярн|размещени|зона\b|отнесени"),
    ("фиксация решения захода / отклонения", r"фиксаци|решени\w* захода|sanctioned|deviation|отклонени|развилк|решение"),
    ("инструмент / гейт / прибор", r"гейт|selfcheck|прибор|сторож|ложн\w* срабат|--check"),
    ("доступ к источнику / внешний владелец", r"доступ|владел\w*|внешн\w* pageId|viewpage|chужо|чужой|чужие"),
]
cnt = Counter()
ex = defaultdict(list)
total = 0
for p in parts:
    m = re.search(r"^- Статус:\s*(.+)$", p, re.M)
    s = (m.group(1).strip().lower() if m else "")
    if s.startswith("закрыт") or s.startswith("реализован") or s.startswith("решён"):
        continue
    total += 1
    head = p.splitlines()[0]
    q = (re.search(r"^- Вопрос:\s*(.+)$", p, re.M) or [None, ""])[1]
    txt = head + " " + q[:400]
    for name, rx in KINDS:
        if re.search(rx, txt, re.I):
            cnt[name] += 1
            ex[name].append(head[3:110])
            break
    else:
        cnt["прочее"] += 1
        ex["прочее"].append(head[3:110])
print("незакрытых:", total)
for k, v in cnt.most_common():
    print(f"\n{k}: {v}")
    for e in ex[k][:4]:
        print("   ", e)
