# Статусы OQ КК и связь открытых OQ с типами замечаний
import re
from collections import Counter
from pathlib import Path

t = Path("C:/doc-as-code/EAS/src-business-cards/open-questions.md").read_text(encoding="utf-8")
parts = re.split(r"^(?=## OQ-\d+)", t, flags=re.M)[1:]
st = Counter()
open_ = []
for p in parts:
    head = p.splitlines()[0]
    m = re.search(r"^- Статус:\s*(.+)$", p, re.M)
    s = (m.group(1).strip() if m else "—")
    key = "закрыт" if s.lower().startswith("закрыт") else ("открыт" if s.lower().startswith("открыт") else s[:40])
    st[key] += 1
    if key != "закрыт":
        open_.append((head, p))
print("всего", len(parts), dict(st.most_common(8)))
keys = {
    "кнопк/ЭФ scr-cl-19": r"scr-cl-19|SCR-CL-19|Заявка на выпуск карты\" в режиме созд",
    "СПП/параметры ЭП": r"СПП|универсальн\w* функци\w* (электронной )?подпис|fun-cl-5[01]|FUN-CL-5[01]|Параметры вызова",
    "CALL-EXT / представления / thin": r"CALL-EXT-0(0[1-9]|1[01])|VW_RPT|представлени",
    "копии": r"Копия|копи[яи] страниц",
    "контроль: способ отображения": r"способ отображ|место показа",
    "Вызов функции / FUN-SYS-10/19": r"FUN-SYS-1[09]|fun-sys-1[09]|Вызов функции",
    "INTC паспорт": r"INTC-00[1-7]|intc-00[1-7]",
    "proc-003 / УС_РЕК": r"PROC-003|proc-003|УС_РЕК|УС ПИН",
}
for k, rx in keys.items():
    hits = [h for h, p in open_ if re.search(rx, p)]
    print(f"\n{k}: открытых {len(hits)}")
    for h in hits[:6]:
        print("   ", h[:150])
