"""
Проверка round-trip: bundled-файл структурно идентичен исходной спеке.
Сравнение порядко-независимое (рекурсивная сортировка ключей).

Использование:
    python verify_roundtrip.py --src spec.json --bundled bundled.yaml
"""
import argparse
import json

import yaml


def load(path):
    with open(path, encoding="utf-8") as f:
        if path.lower().endswith((".yaml", ".yml")):
            return yaml.safe_load(f)
        return json.load(f)


def norm(o):
    if isinstance(o, dict):
        return {k: norm(v) for k, v in sorted(o.items())}
    if isinstance(o, list):
        return [norm(x) for x in o]
    return o


def diff(x, y, path=""):
    if type(x) is not type(y):
        print(f"TYPE {path}: {type(x).__name__} vs {type(y).__name__}")
        return
    if isinstance(x, dict):
        for k in sorted(set(x) | set(y)):
            if k not in x:
                print(f"ONLY-IN-BUNDLED {path}/{k}")
            elif k not in y:
                print(f"ONLY-IN-SOURCE  {path}/{k}")
            else:
                diff(x[k], y[k], f"{path}/{k}")
    elif isinstance(x, list):
        if len(x) != len(y):
            print(f"LEN {path}: {len(x)} vs {len(y)}")
            return
        for i, (xi, yi) in enumerate(zip(x, y)):
            diff(xi, yi, f"{path}[{i}]")
    elif x != y:
        print(f"VAL {path}: {x!r:.60} vs {y!r:.60}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--bundled", required=True)
    args = ap.parse_args()

    a = norm(load(args.src))
    b = norm(load(args.bundled))
    if a == b:
        print("OK: bundled структурно идентичен исходнику")
        return 0
    print("DIFF: расхождения (первые):")
    diff(a, b)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
