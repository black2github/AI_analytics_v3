"""
Доменный сплиттер OpenAPI-спецификации.

Раскладывает единый OpenAPI-файл (JSON или YAML) на доменные папки + общий
components/<section>/common, сохраняя имена компонентов так, чтобы
`redocly bundle` собрал обратно структурно эквивалентную спеку.

Структура вывода:
    <out>/openapi.yaml                          точка входа ($ref на paths и компоненты)
    <out>/paths/<domain>/<file>.yaml            по файлу на каждый path item
    <out>/components/<section>/<folder>/<Name>.yaml
        section = schemas | parameters | responses | requestBodies | headers | examples ...
        folder  = домен, если компонент используется ровно одним доменом, иначе "common"
                  (доменное распределение применяется к schemas; прочие секции -> common)

Маппинг path -> домен задаётся:
  * файлом --domains config.json  (см. domains.example.json), ИЛИ
  * по умолчанию — группировкой по сегменту пути (--group-by N, 0-based).

Использование:
    python split_spec.py --src spec.json --out ./spec-split [--domains domains.json] [--group-by 2]
"""
import argparse
import json
import os
import re
from collections import defaultdict

import yaml

# Секции components, элементы которых выносим в отдельные файлы.
SPLIT_SECTIONS = ["schemas", "parameters", "responses", "requestBodies", "headers", "examples", "callbacks"]
# Секции, которые целиком остаются в точке входа (короткие, ссылаются по имени).
INLINE_SECTIONS = ["securitySchemes", "links"]


def load_spec(path):
    with open(path, encoding="utf-8") as f:
        if path.lower().endswith((".yaml", ".yml")):
            return yaml.safe_load(f)
        return json.load(f)


def sanitize(p):
    s = p.strip("/").replace("{", "").replace("}", "")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s or "root"


def make_domain_fn(domains_cfg, group_by):
    """Возвращает функцию path -> domain.

    С --domains: правила {prefix, domain}, побеждает самый длинный совпавший префикс.
    Без --domains: группировка по сегменту пути с индексом group_by.
    """
    if domains_cfg:
        rules = sorted(domains_cfg.get("rules", []), key=lambda r: len(r["prefix"]), reverse=True)
        default = domains_cfg.get("default", "misc")

        def fn(p):
            for r in rules:
                if p == r["prefix"] or p.startswith(r["prefix"].rstrip("/") + "/"):
                    return r["domain"]
            return default

        return fn

    def fn(p):
        parts = [x for x in p.split("/") if x]
        if not parts:
            return "misc"
        idx = group_by if len(parts) > group_by else len(parts) - 1
        return parts[idx]

    return fn


def component_refs(obj):
    """Все ссылки вида '#/components/<section>/<Name>' -> множество (section, name)."""
    out = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "$ref" and isinstance(v, str) and v.startswith("#/components/"):
                    parts = v.split("/")
                    if len(parts) >= 4:
                        out.add((parts[2], parts[3]))
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(obj)
    return out


def closure(start, graph):
    seen, stack = set(), list(start)
    while stack:
        n = stack.pop()
        if n in seen or n not in graph:
            continue
        seen.add(n)
        stack.extend(graph[n])
    return seen


def rewrite_refs(obj, current_dir, comp_path):
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/components/"):
                parts = v.split("/")
                key = (parts[2], parts[3]) if len(parts) >= 4 else None
                if key in comp_path:
                    rel = os.path.relpath(comp_path[key], current_dir).replace("\\", "/")
                    if not rel.startswith("."):
                        rel = "./" + rel
                    new[k] = rel
                else:
                    new[k] = v
            else:
                new[k] = rewrite_refs(v, current_dir, comp_path)
        return new
    if isinstance(obj, list):
        return [rewrite_refs(x, current_dir, comp_path) for x in obj]
    return obj


def dump_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=10_000)


def main():
    ap = argparse.ArgumentParser(description="Доменный сплит OpenAPI-спеки")
    ap.add_argument("--src", required=True, help="исходный файл (.json/.yaml)")
    ap.add_argument("--out", required=True, help="выходная папка")
    ap.add_argument("--domains", help="JSON-конфиг маппинга path->домен")
    ap.add_argument("--group-by", type=int, default=1, help="индекс сегмента пути для группировки (если нет --domains)")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    spec = load_spec(args.src)
    components = spec.get("components", {})
    paths = spec.get("paths", {})

    domains_cfg = load_spec(args.domains) if args.domains else None
    domain_of = make_domain_fn(domains_cfg, args.group_by)

    # граф ссылок между компонентами
    graph = {}
    for section in SPLIT_SECTIONS:
        for name, body in components.get(section, {}).items():
            graph[(section, name)] = component_refs(body)

    # домены, использующие каждый компонент (транзитивно от каждого path)
    comp_domains = defaultdict(set)
    for p, item in paths.items():
        dm = domain_of(p)
        for key in closure(component_refs(item), graph):
            comp_domains[key].add(dm)

    # папка компонента: для schemas — домен (если один) либо common; иначе common
    comp_folder = {}
    for section in SPLIT_SECTIONS:
        for name in components.get(section, {}):
            key = (section, name)
            doms = comp_domains.get(key, set())
            if section == "schemas" and len(doms) == 1:
                comp_folder[key] = next(iter(doms))
            else:
                comp_folder[key] = "common"

    comp_path = {
        (section, name): os.path.join(out, "components", section, comp_folder[(section, name)], name + ".yaml")
        for section in SPLIT_SECTIONS
        for name in components.get(section, {})
    }

    # файлы компонентов
    for (section, name), target in comp_path.items():
        body = components[section][name]
        dump_yaml(target, rewrite_refs(body, os.path.dirname(target), comp_path))

    # файлы path items
    path_file = {}
    for p, item in paths.items():
        dm = domain_of(p)
        target = os.path.join(out, "paths", dm, sanitize(p) + ".yaml")
        path_file[p] = target
        dump_yaml(target, rewrite_refs(item, os.path.dirname(target), comp_path))

    # точка входа
    entry = {k: spec[k] for k in ("openapi", "info", "servers", "security") if k in spec}
    if "tags" in spec:
        entry["tags"] = spec["tags"]
    entry["paths"] = {}
    for p in paths:
        rel = os.path.relpath(path_file[p], out).replace("\\", "/")
        entry["paths"][p] = {"$ref": "./" + rel}
    entry["components"] = {}
    for section in SPLIT_SECTIONS:
        if components.get(section):
            entry["components"][section] = {}
            for name in components[section]:
                rel = os.path.relpath(comp_path[(section, name)], out).replace("\\", "/")
                entry["components"][section][name] = {"$ref": "./" + rel}
    for section in INLINE_SECTIONS:
        if components.get(section):
            entry["components"][section] = components[section]

    dump_yaml(os.path.join(out, "openapi.yaml"), entry)

    # отчёт
    print(f"paths: {len(paths)}")
    for section in SPLIT_SECTIONS:
        items = components.get(section, {})
        if not items:
            continue
        by_folder = defaultdict(int)
        for name in items:
            by_folder[comp_folder[(section, name)]] += 1
        print(f"{section}: {len(items)}")
        for k in sorted(by_folder):
            print(f"  {k:14} {by_folder[k]}")
    print(f"output: {out}")


if __name__ == "__main__":
    main()
