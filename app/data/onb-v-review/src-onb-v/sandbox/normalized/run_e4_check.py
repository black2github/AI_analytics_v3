# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess
import sys

root = Path(r"C:\repos\serv-migr")
nt = root / "docs-o2new/_meta/tools/normalize_tables.py"
docs = root / "src-onb-v"
out_dir = docs / "sandbox/gate"
conf = (
    docs
    / "confluence/[ОНБ_В]-Сервис-открытия-1-го-счета-и-регистрации-клиента-во-внешней-части-сайта"
    / "[ОНБ_В]-Экранные-формы"
    / "[ОНБ_В]-ЭФ-Клиента"
)
pairs = [
    (
        "scr-cl-01",
        docs / "srs/screen-form/client/scr-cl-01-org-data.md",
        conf / "[ОНБ_В]-ЭФ-Клиента-Ввод-данных-организацииИП-с-внешнего-сайта.md",
    ),
    (
        "scr-cl-02",
        docs / "srs/screen-form/client/scr-cl-02-org-data-no-dadata.md",
        conf
        / "[ОНБ_В]-ЭФ-Клиента-Ввод-данных-организацииИП-с-внешнего-сайта.-Нет-данных-из-DADATA.md",
    ),
    (
        "scr-cl-03",
        docs / "srs/screen-form/client/scr-cl-03-applicant.md",
        conf / "[ОНБ_В]-ЭФ-Клиента-Ввод-данных-заявителя-с-внешнего-сайта.md",
    ),
    (
        "scr-cl-04",
        docs / "srs/screen-form/client/scr-cl-04-phone-confirm.md",
        conf / "[ОНБ_В]-ЭФ-Клиента-Подтверждение-номера-телефона.md",
    ),
]
for name, card, src in pairs:
    proc = subprocess.run(
        [sys.executable, str(nt), str(card), "--check", "--source", str(src), "--docs-root", str(docs)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (out_dir / f"E4-check-{name}.txt").write_text(
        f"exit={proc.returncode}\n\n{text}", encoding="utf-8"
    )
    print(name, "exit", proc.returncode)
