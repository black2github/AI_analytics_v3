#!/usr/bin/env python3
"""Детерминированный validator документации BA/SA, работающий только на чтение.

Коды выхода: 0 — новых ошибок нет, 1 — есть новые детерминированные ошибки,
2 — validator не смог достоверно завершить проверку. Дефекты baseline выводятся
только счётчиком и не превращаются в новые ошибки. Исключение — проверки устройства комплекта,
которые блокируют всегда, даже если дефект существовал в baseline:
E_TRACEABILITY_MISSING — в корне комплекта нет матрицы; E_TRACEABILITY_DUPLICATE — матрица лежит
не в корне комплекта (внутри другого комплекта); E_KIT_DOCS_WRAPPER — корень комплекта называется
`docs` (обёртка `docs/` недопустима).

Комплект — каталог, в котором лежит `srs/`, каталог бизнес-слоя или матрица. Репозиторий может
содержать один комплект в корне или несколько в подкаталогах (доменный репозиторий); репозиторий
без таких каталогов (базовые контракты, код) матрицы не имеет по устройству.

Имя матрицы и каталог-признак бизнес-слоя по умолчанию — раскладка Банка (traceability-matrix.md,
brd/); проект с иной раскладкой передаёт --layout <docs-kit-layout.yaml>, и значения берутся оттуда.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

# Раскладка комплекта: значения по умолчанию совпадают с раскладкой эталона, --layout переопределяет их
# из docs-kit-layout.yaml проекта (ключи traceability.file и business_layer.marker_dir).
MATRIX_FILE = "traceability-matrix.md"
BUSINESS_MARKER = "brd"


def apply_layout(path: Path | None) -> None:
    """Переопределить имя матрицы и признак бизнес-слоя из машинной раскладки; нечитаемый файл — умолчания."""
    global MATRIX_FILE, BUSINESS_MARKER
    if path is None or not path.is_file():
        return
    try:
        import yaml  # есть в образе агента; локально без него остаются умолчания
    except ImportError:  # pragma: no cover
        return
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return
    if not isinstance(data, dict):
        return
    matrix = (data.get("traceability") or {}).get("file")
    marker = (data.get("business_layer") or {}).get("marker_dir")
    if isinstance(matrix, str) and matrix:
        MATRIX_FILE = matrix
    if isinstance(marker, str) and marker:
        BUSINESS_MARKER = marker.rstrip("/")

try:
    import yaml
except ImportError as exc:  # pragma: no cover — нарушение контракта образа
    print(f"VALIDATOR_ERROR: PyYAML is unavailable: {exc}", file=sys.stderr)
    raise SystemExit(2)


SCRIPT_ROOT = Path(__file__).resolve().parent.parent
RULES_ROOT = SCRIPT_ROOT / "rules"
FRONTMATTER_FIELDS = ("id", "partOf", "type", "service", "version")
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCED_BLOCK = re.compile(r"^\s*(```|~~~)")
PATH_VARIABLE = re.compile(r"\{([^{}]+)\}")
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


class ValidatorFailure(RuntimeError):
    """Сбой инфраструктуры или конфигурации, а не дефект документа."""


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, "unhashable key", key_node.start_mark
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key: {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    line: int
    detail: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.code, self.path, self.detail


@dataclass(frozen=True)
class RefTarget:
    path: str
    document: Any
    fragment: str


def git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr if text else completed.stderr.decode("utf-8", "replace")
        raise ValidatorFailure(f"git {' '.join(args)}: {stderr.strip()}")
    return completed.stdout


def nul_paths(raw: bytes) -> set[str]:
    return {
        item.decode("utf-8", "surrogateescape").replace("\\", "/")
        for item in raw.split(b"\0")
        if item
    }


class Snapshot:
    def list_files(self) -> set[str]:
        raise NotImplementedError

    def read_bytes(self, relative: str) -> bytes:
        raise NotImplementedError

    def exists(self, relative: str) -> bool:
        raise NotImplementedError


class GitSnapshot(Snapshot):
    def __init__(self, repo: Path, ref: str):
        self.repo = repo
        self.ref = ref
        git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
        self._files = nul_paths(git(repo, "ls-tree", "-r", "--name-only", "-z", ref, text=False))
        self._cache: dict[str, bytes] = {}

    def list_files(self) -> set[str]:
        return set(self._files)

    def read_bytes(self, relative: str) -> bytes:
        if relative not in self._files:
            raise FileNotFoundError(relative)
        if relative not in self._cache:
            self._cache[relative] = git(self.repo, "show", f"{self.ref}:{relative}", text=False)
        return self._cache[relative]

    def exists(self, relative: str) -> bool:
        if relative in self._files:
            return True
        prefix = relative.rstrip("/") + "/"
        return any(path.startswith(prefix) for path in self._files)


class WorktreeSnapshot(Snapshot):
    def __init__(self, repo: Path):
        self.repo = repo.resolve()
        self._files = nul_paths(
            git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard", text=False)
        )
        self._files = {path for path in self._files if (self.repo / Path(path)).exists()}
        self._cache: dict[str, bytes] = {}

    def list_files(self) -> set[str]:
        return set(self._files)

    def _safe_path(self, relative: str) -> Path:
        candidate = self.repo / Path(relative)
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.repo)
        except ValueError as exc:
            raise PermissionError(f"path leaves repository: {relative}") from exc
        return candidate

    def read_bytes(self, relative: str) -> bytes:
        if relative not in self._files:
            raise FileNotFoundError(relative)
        if relative not in self._cache:
            self._cache[relative] = self._safe_path(relative).read_bytes()
        return self._cache[relative]

    def exists(self, relative: str) -> bool:
        try:
            self._safe_path(relative)
        except PermissionError:
            return False
        if relative in self._files:
            return True
        prefix = relative.rstrip("/") + "/"
        return any(path.startswith(prefix) for path in self._files)


def load_yaml_bytes(raw: bytes) -> Any:
    text = raw.decode("utf-8")
    return yaml.load(text, Loader=UniqueKeyLoader)


def load_rule_marker(name: str) -> dict[str, Any]:
    path = RULES_ROOT / name
    try:
        document = load_yaml_bytes(path.read_bytes())
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValidatorFailure(f"invalid role registry file {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValidatorFailure(f"role registry file must contain a mapping: {path}")
    return document


def validate_role(role: str) -> str:
    registry = load_rule_marker("common.yaml")
    aliases = registry.get("roleAliases")
    valid_aliases = isinstance(aliases, dict) and all(
        isinstance(key, str) and isinstance(value, str) for key, value in aliases.items()
    )
    if not valid_aliases:
        raise ValidatorFailure("common.yaml roleAliases must be a string mapping")
    normalized = aliases.get(role.upper(), role.lower())
    if normalized not in set(aliases.values()):
        raise ValidatorFailure(f"unsupported role: {role}")
    marker = load_rule_marker(f"{normalized}.yaml")
    if marker.get("role") != normalized:
        raise ValidatorFailure(f"role marker mismatch: {normalized}.yaml")
    return normalized


def decode(snapshot: Snapshot, path: str, findings: list[Finding]) -> str | None:
    try:
        return snapshot.read_bytes(path).decode("utf-8")
    except UnicodeDecodeError as exc:
        findings.append(Finding("ERROR", "E_INVALID_UTF8", path, 1, f"invalid UTF-8 at byte {exc.start}"))
    except PermissionError:
        findings.append(Finding("ERROR", "E_PATH_OUTSIDE_REPOSITORY", path, 1, "symlink leaves repository"))
    return None


def frontmatter(text: str, path: str, findings: list[Finding]) -> dict[str, Any] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        closing = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        findings.append(Finding("ERROR", "E_FRONTMATTER_INVALID", path, 1, "closing '---' is missing"))
        return None
    try:
        value = yaml.load("\n".join(lines[1:closing]), Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = (mark.line + 2) if mark else 1
        code = "E_FRONTMATTER_DUPLICATE_KEY" if "duplicate key" in str(exc) else "E_FRONTMATTER_INVALID"
        findings.append(Finding("ERROR", code, path, line, str(exc).splitlines()[0]))
        return None
    if value is None:
        return {}
    if not isinstance(value, dict):
        findings.append(Finding("ERROR", "E_FRONTMATTER_INVALID", path, 1, "frontmatter must be a mapping"))
        return None
    for field in FRONTMATTER_FIELDS:
        if field not in value:
            continue
        declared = value[field]
        if not isinstance(declared, (str, int, float)) or not str(declared).strip():
            findings.append(
                Finding(
                    "ERROR",
                    "E_FRONTMATTER_EMPTY_FIELD",
                    path,
                    1,
                    f"declared field '{field}' is empty or not scalar",
                )
            )
    return value


def strip_fenced_blocks(text: str) -> Iterable[tuple[int, str]]:
    fence: str | None = None
    for line_no, line in enumerate(text.splitlines(), start=1):
        marker = FENCED_BLOCK.match(line)
        if marker:
            current = marker.group(1)
            if fence is None:
                fence = current[0]
            elif current.startswith(fence):
                fence = None
            continue
        if fence is None:
            yield line_no, line


def strip_inline_code_spans(line: str) -> str:
    runs = list(re.finditer(r"`+", line))
    characters = list(line)
    run_index = 0
    while run_index < len(runs):
        opening = runs[run_index]
        preceding_backslashes = 0
        cursor = opening.start() - 1
        while cursor >= 0 and line[cursor] == "\\":
            preceding_backslashes += 1
            cursor -= 1
        if preceding_backslashes % 2:
            run_index += 1
            continue

        closing_index = next(
            (
                index
                for index in range(run_index + 1, len(runs))
                if len(runs[index].group()) == len(opening.group())
            ),
            None,
        )
        if closing_index is None:
            run_index += 1
            continue
        closing = runs[closing_index]
        characters[opening.start() : closing.end()] = " " * (closing.end() - opening.start())
        run_index = closing_index + 1
    return "".join(characters)


def normalize_target(source: str, raw_target: str) -> tuple[str | None, bool]:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if " " in target and not target.startswith(("http://", "https://")):
        target = target.split(maxsplit=1)[0]
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("#"):
        return None, False
    decoded = urllib.parse.unquote(parsed.path).replace("\\", "/")
    if not decoded:
        return None, False
    if decoded.startswith("/"):
        return decoded, True
    source_parent = PurePosixPath(source).parent
    parts: list[str] = []
    outside = False
    for part in (source_parent / decoded).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            else:
                outside = True
        else:
            parts.append(part)
    return "/".join(parts), outside


def check_links(snapshot: Snapshot, path: str, text: str, findings: list[Finding]) -> None:
    for line_no, line in strip_fenced_blocks(text):
        for match in MARKDOWN_LINK.finditer(strip_inline_code_spans(line)):
            target, outside = normalize_target(path, match.group(1))
            if outside:
                findings.append(
                    Finding("ERROR", "E_LOCAL_LINK_OUTSIDE_REPOSITORY", path, line_no, match.group(1).strip())
                )
            elif target and not snapshot.exists(target):
                findings.append(Finding("ERROR", "E_LOCAL_LINK_MISSING", path, line_no, target))


def parse_structured(snapshot: Snapshot, path: str, findings: list[Finding]) -> Any:
    try:
        raw = snapshot.read_bytes(path)
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".json":
            return json.loads(raw.decode("utf-8"))
        if suffix in {".yaml", ".yml"}:
            return load_yaml_bytes(raw)
        if suffix in {".xml", ".xsd", ".wsdl"}:
            ET.fromstring(raw.decode("utf-8"))
            return None
    except UnicodeDecodeError as exc:
        findings.append(Finding("ERROR", "E_INVALID_UTF8", path, 1, f"invalid UTF-8 at byte {exc.start}"))
    except (json.JSONDecodeError, yaml.YAMLError, ET.ParseError) as exc:
        line = getattr(exc, "lineno", None) or getattr(getattr(exc, "problem_mark", None), "line", 0) + 1
        findings.append(Finding("ERROR", "E_STRUCTURED_FILE_INVALID", path, int(line or 1), str(exc).splitlines()[0]))
    except PermissionError:
        findings.append(Finding("ERROR", "E_PATH_OUTSIDE_REPOSITORY", path, 1, "symlink leaves repository"))
    return None


def resolve_pointer_value(document: Any, fragment: str) -> tuple[bool, Any]:
    if not fragment:
        return True, document
    if not fragment.startswith("/"):
        return False, None
    current = document
    for token in fragment[1:].split("/"):
        token = urllib.parse.unquote(token).replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return False, None
    return True, current


def load_ref_document(snapshot: Snapshot, source: str, target: str, cache: dict[str, Any]) -> RefTarget | None:
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    ref_path = parsed.path
    if ref_path:
        normalized, outside = normalize_target(source, ref_path)
        if outside or not normalized or not snapshot.exists(normalized):
            return None
        resolved_path = normalized
    else:
        resolved_path = source
    if resolved_path not in cache:
        local_findings: list[Finding] = []
        cache[resolved_path] = parse_structured(snapshot, resolved_path, local_findings)
        if local_findings:
            return None
    document = cache[resolved_path]
    if document is None:
        return None
    return RefTarget(resolved_path, document, parsed.fragment)


def is_local_ref(target: str) -> bool:
    parsed = urllib.parse.urlsplit(target)
    return not parsed.scheme and not parsed.netloc


def resolve_ref_value(
    snapshot: Snapshot,
    source: str,
    ref: str,
    cache: dict[str, Any],
) -> tuple[bool, Any]:
    visited: set[tuple[str, str]] = set()
    current_source = source
    current_ref = ref
    while is_local_ref(current_ref):
        resolved = load_ref_document(snapshot, current_source, current_ref, cache)
        if resolved is None:
            return False, None
        target_key = (resolved.path, resolved.fragment)
        if target_key in visited:
            return False, None
        visited.add(target_key)
        found, value = resolve_pointer_value(resolved.document, resolved.fragment)
        if not found:
            return False, None
        nested_ref = value.get("$ref") if isinstance(value, dict) else None
        if not isinstance(nested_ref, str):
            return True, value
        current_source = resolved.path
        current_ref = nested_ref
    return False, None


def check_local_refs(
    snapshot: Snapshot,
    source: str,
    value: Any,
    findings: list[Finding],
    cache: dict[str, Any],
    visited: set[tuple[str, int]],
) -> None:
    if isinstance(value, dict):
        node_key = (source, id(value))
        if node_key in visited:
            return
        visited.add(node_key)

        ref = value.get("$ref")
        if isinstance(ref, str) and is_local_ref(ref):
            resolved = load_ref_document(snapshot, source, ref, cache)
            if resolved is None:
                findings.append(Finding("ERROR", "E_LOCAL_REF_UNRESOLVED", source, 1, ref))
            else:
                found, target_value = resolve_pointer_value(resolved.document, resolved.fragment)
                if not found:
                    findings.append(Finding("ERROR", "E_LOCAL_REF_UNRESOLVED", source, 1, ref))
                else:
                    check_local_refs(
                        snapshot,
                        resolved.path,
                        target_value,
                        findings,
                        cache,
                        visited,
                    )

        for nested in value.values():
            check_local_refs(snapshot, source, nested, findings, cache, visited)
    elif isinstance(value, list):
        node_key = (source, id(value))
        if node_key in visited:
            return
        visited.add(node_key)
        for nested in value:
            check_local_refs(snapshot, source, nested, findings, cache, visited)


def openapi_path_item_operation_ids(
    path_item: Any,
    visited: set[int],
) -> Iterable[str]:
    if not isinstance(path_item, dict) or id(path_item) in visited:
        return
    visited.add(id(path_item))
    for method, operation in path_item.items():
        if not isinstance(method, str) or method.lower() not in HTTP_METHODS:
            continue
        if not isinstance(operation, dict):
            continue
        operation_id = operation.get("operationId")
        if isinstance(operation_id, str) and operation_id:
            yield operation_id
        callbacks = operation.get("callbacks")
        if not isinstance(callbacks, dict):
            continue
        for callback in callbacks.values():
            if not isinstance(callback, dict):
                continue
            for expression, callback_path_item in callback.items():
                if expression == "$ref" or (isinstance(expression, str) and expression.startswith("x-")):
                    continue
                yield from openapi_path_item_operation_ids(callback_path_item, visited)


def declared_operation_ids(document: dict[str, Any]) -> Iterable[str]:
    if "openapi" in document:
        paths = document.get("paths")
        if isinstance(paths, dict):
            visited: set[int] = set()
            for path_item in paths.values():
                yield from openapi_path_item_operation_ids(path_item, visited)
        return

    version = document.get("asyncapi")
    major = version.split(".", maxsplit=1)[0] if isinstance(version, str) else ""
    if major == "2":
        channels = document.get("channels")
        if not isinstance(channels, dict):
            return
        for channel_item in channels.values():
            if not isinstance(channel_item, dict):
                continue
            for action in ("publish", "subscribe"):
                operation = channel_item.get(action)
                if not isinstance(operation, dict):
                    continue
                operation_id = operation.get("operationId")
                if isinstance(operation_id, str) and operation_id:
                    yield operation_id
        return

    if major == "3":
        operations = document.get("operations")
        if isinstance(operations, dict):
            for operation_id in operations:
                if isinstance(operation_id, str) and operation_id:
                    yield operation_id


def check_api(snapshot: Snapshot, path: str, document: Any, findings: list[Finding]) -> None:
    if not isinstance(document, dict) or not ({"openapi", "asyncapi"} & set(document)):
        return
    cache: dict[str, Any] = {path: document}
    operation_ids: dict[str, int] = {}
    check_local_refs(snapshot, path, document, findings, cache, set())
    for operation_id in declared_operation_ids(document):
        operation_ids[operation_id] = operation_ids.get(operation_id, 0) + 1
    for operation_id, count in operation_ids.items():
        if count > 1:
            findings.append(
                Finding("ERROR", "E_OPERATION_ID_DUPLICATE", path, 1, f"operationId={operation_id}")
            )
    if "openapi" not in document or not isinstance(document.get("paths"), dict):
        return
    for route, path_item in document["paths"].items():
        if not isinstance(route, str) or not isinstance(path_item, dict):
            continue
        variables = set(PATH_VARIABLE.findall(route))
        inherited = path_item.get("parameters", [])
        if not isinstance(inherited, list):
            inherited = []
        for method, operation in path_item.items():
            if not isinstance(method, str) or method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            own_parameters = operation.get("parameters", [])
            if not isinstance(own_parameters, list):
                own_parameters = []
            parameters = [*inherited, *own_parameters]
            bound: set[str] = set()
            has_unresolved_parameter_ref = False
            for parameter in parameters:
                if not isinstance(parameter, dict):
                    continue
                effective = parameter
                ref = parameter.get("$ref")
                if isinstance(ref, str):
                    found, value = resolve_ref_value(snapshot, path, ref, cache)
                    if not found or not isinstance(value, dict):
                        has_unresolved_parameter_ref = True
                        continue
                    effective = value
                if effective.get("in") == "path" and isinstance(effective.get("name"), str):
                    bound.add(effective["name"])
            if has_unresolved_parameter_ref:
                continue
            for variable in sorted(variables - bound):
                findings.append(
                    Finding("ERROR", "E_PATH_PARAMETER_UNBOUND", path, 1, f"{method.upper()} {route}: {variable}")
                )


SYSTEM_LAYER_DIR = "srs"  # каталог системного слоя — один для всех проектов Банка (канон комплекта)


def inside(path: str, root: str) -> bool:
    """Лежит ли путь строго внутри каталога `root` (``""`` — корень репозитория)."""
    if root == "":
        return path != ""
    return path.startswith(root + "/")


def kit_roots(files: set[str]) -> set[str]:
    """Корни комплектов: каталоги (включая корень репозитория, ``""``), где лежат каталоги слоёв (`srs/`,
    бизнес-слой) или матрица. Каталог со слоями внутри другого такого каталога корнем не считается — он
    часть внешнего комплекта. Каталог, где есть только матрица, становится корнем, лишь если не лежит
    внутри комплекта и не содержит комплектов: иначе его матрица — матрица вне корня комплекта.
    Кандидаты перебираются от короткого пути к длинному, чтобы внешний каталог проверялся раньше вложенного
    и результат не зависел от порядка обхода множества."""
    with_layers: set[str] = set()
    with_matrix: set[str] = set()
    for path in files:
        parts = path.split("/")
        for index, segment in enumerate(parts[:-1]):
            if segment in (SYSTEM_LAYER_DIR, BUSINESS_MARKER):
                with_layers.add("/".join(parts[:index]))
                break
        if parts[-1] == MATRIX_FILE:
            with_matrix.add("/".join(parts[:-1]))
    roots = {c for c in with_layers if not any(inside(c, other) for other in with_layers if other != c)}
    for candidate in sorted(with_matrix - roots, key=lambda c: (len(c), c)):
        if any(inside(candidate, root) or inside(root, candidate) for root in roots):
            continue
        roots.add(candidate)
    return roots


def check_matrix(files: set[str], findings: list[Finding]) -> None:
    """Устройство комплекта: матрица обязательна в корне каждого комплекта, матрица внутри чужого комплекта
    недопустима, корень комплекта не может называться `docs`. Репозиторий без комплектов (базовые контракты,
    код) матрицы не имеет по устройству — требований к нему нет."""
    roots = kit_roots(files)
    matrices = {path for path in files if PurePosixPath(path).name == MATRIX_FILE}
    for root in sorted(roots):
        expected = f"{root}/{MATRIX_FILE}" if root else MATRIX_FILE
        if PurePosixPath(root).name == "docs":
            findings.append(
                Finding("ERROR", "E_KIT_DOCS_WRAPPER", root + "/", 1, "kit root must not be a docs/ wrapper")
            )
        if expected not in matrices:
            findings.append(Finding("ERROR", "E_TRACEABILITY_MISSING", expected, 1, "required at kit root"))
    for path in sorted(matrices):
        parent = str(PurePosixPath(path).parent)
        parent = "" if parent == "." else parent
        if parent in roots:
            continue
        enclosing = next((root for root in sorted(roots, key=len, reverse=True) if inside(parent, root)), None)
        if enclosing is None:
            where = "outside any kit"
        elif enclosing == "":
            where = "inside kit at repository root"
        else:
            where = f"inside kit {enclosing}/"
        findings.append(Finding("ERROR", "E_TRACEABILITY_DUPLICATE", path, 1, f"matrix outside kit root ({where})"))


def check_duplicate_ids(snapshot: Snapshot, findings: list[Finding]) -> None:
    declared: dict[str, list[str]] = {}
    for path in sorted(snapshot.list_files()):
        if PurePosixPath(path).suffix.lower() != ".md":
            continue
        try:
            prefix = snapshot.read_bytes(path)[:65536].decode("utf-8")
        except (UnicodeError, PermissionError):
            continue
        local: list[Finding] = []
        metadata = frontmatter(prefix, path, local)
        if metadata and isinstance(metadata.get("id"), (str, int, float)):
            identifier = str(metadata["id"]).strip()
            if identifier:
                declared.setdefault(identifier, []).append(path)
    for identifier, paths in declared.items():
        if len(paths) > 1:
            for path in paths:
                findings.append(
                    Finding("ERROR", "E_DECLARED_ID_DUPLICATE", path, 1, f"id={identifier}; files={','.join(paths)}")
                )


def check_document_identity(path: str, metadata: dict[str, Any] | None, findings: list[Finding]) -> None:
    if metadata is None or "type" not in metadata:
        return
    has_id = isinstance(metadata.get("id"), (str, int, float)) and bool(str(metadata["id"]).strip())
    has_parent = isinstance(metadata.get("partOf"), (str, int, float)) and bool(
        str(metadata["partOf"]).strip()
    )
    if not has_id and not has_parent:
        findings.append(
            Finding(
                "ERROR",
                "E_DOCUMENT_IDENTITY_MISSING",
                path,
                1,
                "typed document must declare non-empty id or partOf",
            )
        )


def validate(snapshot: Snapshot) -> list[Finding]:
    findings: list[Finding] = []
    files = snapshot.list_files()
    check_matrix(files, findings)
    check_duplicate_ids(snapshot, findings)
    for path in sorted(files):
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".md":
            text = decode(snapshot, path, findings)
            if text is not None:
                metadata = frontmatter(text, path, findings)
                check_document_identity(path, metadata, findings)
                check_links(snapshot, path, text, findings)
        elif suffix in {".yaml", ".yml", ".json", ".xml", ".xsd", ".wsdl"}:
            document = parse_structured(snapshot, path, findings)
            if document is not None:
                check_api(snapshot, path, document, findings)
    unique = {finding.key: finding for finding in findings}
    return sorted(unique.values(), key=lambda item: (item.severity, item.path, item.line, item.code, item.detail))


def changed_paths(repo: Path, baseline: str, head: str, include_worktree: bool) -> set[str]:
    changed = nul_paths(
        git(repo, "diff", "--name-only", "--diff-filter=ACDMRTUXB", "-z", baseline, head, text=False)
    )
    if include_worktree:
        changed |= nul_paths(git(repo, "diff", "--name-only", "--diff-filter=ACDMRTUXB", "-z", text=False))
        changed |= nul_paths(
            git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB", "-z", text=False)
        )
        changed |= nul_paths(git(repo, "ls-files", "--others", "--exclude-standard", "-z", text=False))
    return changed


def format_finding(finding: Finding) -> str:
    return f"{finding.severity} {finding.code} {finding.path}:{finding.line} {finding.detail}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--role", required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--include-worktree", action="store_true")
    parser.add_argument("--format", choices=("compact", "json"), default="compact")
    parser.add_argument("--max-findings", type=int, default=30)
    parser.add_argument("--layout", type=Path, default=None, help="машинная раскладка комплекта (docs-kit-layout.yaml)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    apply_layout(args.layout)
    try:
        repo = args.repo.resolve(strict=True)
        if not (repo / ".git").exists():
            raise ValidatorFailure(f"not a git repository: {repo}")
        if args.max_findings < 1 or args.max_findings > 200:
            raise ValidatorFailure("--max-findings must be between 1 and 200")
        validate_role(args.role)
        head = str(git(repo, "rev-parse", "--verify", f"{args.head_ref}^{{commit}}")).strip()
        baseline = str(git(repo, "merge-base", args.base_ref, head)).strip()
        baseline_snapshot = GitSnapshot(repo, baseline)
        current_snapshot: Snapshot = WorktreeSnapshot(repo) if args.include_worktree else GitSnapshot(repo, head)
        changed = changed_paths(repo, baseline, head, args.include_worktree)
        baseline_findings = validate(baseline_snapshot)
        current_findings = validate(current_snapshot)
        baseline_keys = {finding.key for finding in baseline_findings}
        always_block = {"E_TRACEABILITY_MISSING", "E_TRACEABILITY_DUPLICATE", "E_KIT_DOCS_WRAPPER"}
        new_findings = [
            finding
            for finding in current_findings
            if finding.key not in baseline_keys or finding.code in always_block
        ]
        baseline_debt = sum(finding.key in baseline_keys for finding in current_findings)
        visible = new_findings[: args.max_findings]
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "findings": [finding.__dict__ for finding in visible],
                        "summary": {
                            "errors": len(new_findings),
                            "baseline": baseline_debt,
                            "changedFiles": len(changed),
                            "truncated": max(0, len(new_findings) - len(visible)),
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        else:
            for finding in visible:
                print(format_finding(finding))
            print(
                f"SUMMARY errors={len(new_findings)} warnings=0 baseline={baseline_debt} "
                f"changedFiles={len(changed)} truncated={max(0, len(new_findings) - len(visible))}"
            )
        return 1 if new_findings else 0
    except (OSError, ValidatorFailure) as exc:
        print(f"VALIDATOR_ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover — защитная граница workflow агента
        print(f"VALIDATOR_ERROR: internal failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
