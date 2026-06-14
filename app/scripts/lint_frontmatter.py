# app/scripts/lint_frontmatter.py
# Запуск вручную: python scripts/lint_frontmatter.py — просканирует всю папку requirements/. 
# При PR — автоматически на изменённые .md файлы.

import sys
import yaml
from pathlib import Path
from typing import Dict, List

REQUIRED_FIELDS = {
    "doc_id",
    "title",
    "doc_type",
    "requirement_type",
    "service_code",
    "status",
    "owner",
    "jira_id",
    "source",
}

VALID_STATUSES = {"draft", "review", "approved", "deprecated"}

VALID_REQUIREMENT_TYPES = {
    "BRD", "function", "control", "screenListForm", "screenItemForm", "integration",
    "dataModel", "notification", "process", "states",
    "agent", "printForm",
    "unknown",  # тип не удалось определить при миграции — аналитик проставит при ревью
}

VALID_DOC_TYPES = {"requirement", "template", "glossary"}

INTEGRATION_REQUIRED = {"target_system"}

COMMA_STR_FIELDS = {"jira_ids", "reviewed_by", "related", "tags"}


def parse_frontmatter(filepath: Path) -> Dict | None:
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        print(f"[ERROR] {filepath}: YAML parse error — {e}")
        return None


def lint_file(filepath: Path) -> List[str]:
    errors = []

    meta = parse_frontmatter(filepath)
    if meta is None:
        errors.append(f"{filepath}: no frontmatter found (file must start with ---)")
        return errors

    # Обязательные поля
    for field in REQUIRED_FIELDS:
        if not meta.get(field):
            errors.append(f"{filepath}: missing required field '{field}'")

    # Допустимые значения
    if meta.get("status") and meta["status"] not in VALID_STATUSES:
        errors.append(
            f"{filepath}: invalid status '{meta['status']}'"
            f" — allowed: {sorted(VALID_STATUSES)}"
        )

    if meta.get("requirement_type") and meta["requirement_type"] not in VALID_REQUIREMENT_TYPES:
        errors.append(
            f"{filepath}: invalid requirement_type '{meta['requirement_type']}'"
            f" — allowed: {sorted(VALID_REQUIREMENT_TYPES)}"
        )

    if meta.get("doc_type") and meta["doc_type"] not in VALID_DOC_TYPES:
        errors.append(
            f"{filepath}: invalid doc_type '{meta['doc_type']}'"
            f" — allowed: {sorted(VALID_DOC_TYPES)}"
        )

    # Условное: интеграции требуют target_system
    if meta.get("requirement_type") == "integration":
        for field in INTEGRATION_REQUIRED:
            if not meta.get(field):
                errors.append(
                    f"{filepath}: requirement_type=integration requires field '{field}'"
                )

    # Предупреждение: поля-списки должны быть строкой, не YAML-списком
    for field in COMMA_STR_FIELDS:
        if field in meta and isinstance(meta[field], list):
            errors.append(
                f"{filepath}: field '{field}' must be a comma-separated string,"
                f" not a YAML list — ChromaDB не поддерживает list в метаданных"
            )

    return errors


def main():
    # Принимает список файлов (от pre-commit) или сканирует requirements/
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:] if f.endswith(".md")]
    else:
        root = Path(__file__).parent.parent
        files = list(root.rglob("requirements/**/*.md"))

    if not files:
        print("No .md files to lint.")
        sys.exit(0)

    all_errors = []
    for filepath in files:
        all_errors.extend(lint_file(filepath))

    if all_errors:
        print(f"\n[FRONTMATTER LINT] {len(all_errors)} error(s) found:\n")
        for err in all_errors:
            print(f"  ✗ {err}")
        sys.exit(1)
    else:
        print(f"[FRONTMATTER LINT] OK — {len(files)} file(s) checked.")
        sys.exit(0)


if __name__ == "__main__":
    main()