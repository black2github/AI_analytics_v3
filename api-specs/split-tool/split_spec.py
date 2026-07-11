"""
Доменный сплиттер для business-cards-client.json (фактически JSON).

Раскладывает единую OpenAPI-спеку на доменные папки + общий components/common,
сохраняя имена схем так, чтобы `redocly bundle` собрал обратно эквивалентную спеку.

Структура вывода:
    <out>/openapi.yaml                 — точка входа (info/servers/security + $ref на paths и schemas)
    <out>/paths/<domain>/<file>.yaml   — по файлу на каждый path item
    <out>/components/<folder>/<Name>.yaml — по файлу на каждую схему
        folder = домен, если схема используется ровно одним доменом, иначе "common"

Использование:
    python split_spec.py            # split
"""
import json
import os
import re
import sys
from collections import defaultdict

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # api-specs/
SRC = os.path.join(ROOT, "business-cards-client.json")
OUT = os.path.join(ROOT, "business-cards-client-split")

# ---- маппинг path -> домен (3-й сегмент под /request, иначе по разделу) ----
REQUEST_MAP = {
    "card-issue": "issuance",
    "set-limits": "limits",
    "batch-set-limits": "limits",
    "blocking": "blocking",
    "batch-blocking": "blocking",
}


def path_domain(p: str) -> str:
    parts = [x for x in p.split("/") if x]
    if len(parts) >= 2 and parts[1] == "request":
        seg = parts[2] if len(parts) > 2 else "request"
        return REQUEST_MAP.get(seg, "request-misc")
    if len(parts) >= 2 and parts[1] == "reports":
        return "reports"
    return "misc"


def sanitize(p: str) -> str:
    s = p.strip("/").replace("{", "").replace("}", "")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s or "root"


def schema_refs(obj) -> set:
    out = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "$ref" and isinstance(v, str):
                    out.add(v.split("/")[-1])
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    return out


def closure(start, graph) -> set:
    seen, stack = set(), list(start)
    while stack:
        n = stack.pop()
        if n in seen or n not in graph:
            continue
        seen.add(n)
        stack.extend(graph[n])
    return seen


def rewrite_refs(obj, current_dir, schema_path):
    """Заменяет '#/components/schemas/X' на относительный путь к файлу схемы X."""
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/components/schemas/"):
                name = v.split("/")[-1]
                target = schema_path[name]
                rel = os.path.relpath(target, current_dir).replace("\\", "/")
                if not rel.startswith("."):
                    rel = "./" + rel
                new[k] = rel
            else:
                new[k] = rewrite_refs(v, current_dir, schema_path)
        return new
    if isinstance(obj, list):
        return [rewrite_refs(x, current_dir, schema_path) for x in obj]
    return obj


def dump_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=10_000)


def main():
    spec = json.load(open(SRC, encoding="utf-8"))
    schemas = spec["components"]["schemas"]
    paths = spec["paths"]

    graph = {name: schema_refs(body) for name, body in schemas.items()}

    # домены, использующие каждую схему (через транзитивное замыкание per-path)
    schema_domains = defaultdict(set)
    for p, item in paths.items():
        dm = path_domain(p)
        for sc in closure(schema_refs(item), graph):
            schema_domains[sc].add(dm)

    # папка схемы: домен если ровно один, иначе common; неиспользуемые -> common
    schema_folder = {}
    for name in schemas:
        doms = schema_domains.get(name, set())
        schema_folder[name] = next(iter(doms)) if len(doms) == 1 else "common"

    # абсолютные пути файлов схем (для расчёта относительных $ref)
    schema_path = {
        name: os.path.join(OUT, "components", schema_folder[name], name + ".yaml")
        for name in schemas
    }

    # пишем файлы схем
    for name, body in schemas.items():
        target = schema_path[name]
        dump_yaml(target, rewrite_refs(body, os.path.dirname(target), schema_path))

    # пишем файлы path items
    path_file = {}
    for p, item in paths.items():
        dm = path_domain(p)
        fname = sanitize(p) + ".yaml"
        target = os.path.join(OUT, "paths", dm, fname)
        path_file[p] = target
        dump_yaml(target, rewrite_refs(item, os.path.dirname(target), schema_path))

    # точка входа
    entry = {
        "openapi": spec["openapi"],
        "info": spec["info"],
        "servers": spec["servers"],
        "security": spec["security"],
        "paths": {},
        "components": {
            "schemas": {},
            "securitySchemes": spec["components"]["securitySchemes"],
        },
    }
    for p in paths:
        rel = os.path.relpath(path_file[p], OUT).replace("\\", "/")
        entry["paths"][p] = {"$ref": "./" + rel}
    for name in schemas:
        rel = os.path.relpath(schema_path[name], OUT).replace("\\", "/")
        entry["components"]["schemas"][name] = {"$ref": "./" + rel}

    dump_yaml(os.path.join(OUT, "openapi.yaml"), entry)

    # отчёт
    by_folder = defaultdict(int)
    for f in schema_folder.values():
        by_folder[f] += 1
    print(f"schemas: {len(schemas)}  paths: {len(paths)}")
    print("schemas per folder:")
    for k in sorted(by_folder):
        print(f"  {k:14} {by_folder[k]}")
    print(f"output: {OUT}")


if __name__ == "__main__":
    main()
