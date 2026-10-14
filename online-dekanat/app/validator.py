"""Предварительная проверка обязательных полей по правилам вуза."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.utils import NOT_FOUND

RULE_PATTERN = re.compile(r"(?m)^\s*(\d+\.\d+)\.\s+(.+?)\s*$")


def parse_rules(rules_path: Path) -> dict[str, str]:
    """Читает нумерованные пункты из rules.md как единственный источник правил."""
    if not rules_path.is_file():
        raise FileNotFoundError(f"Файл правил не найден: {rules_path}")
    content = rules_path.read_text(encoding="utf-8")
    rules = {match.group(1): match.group(2).strip() for match in RULE_PATTERN.finditer(content)}
    if not rules:
        raise ValueError(
            "В rules.md не найдены нумерованные пункты. "
            "Используйте формат «3.1. Текст правила»."
        )
    return rules


def validate_document(
    document_type: str,
    fields: dict[str, Any],
    config: dict[str, Any],
    rules: dict[str, str],
) -> dict[str, Any]:
    """Проверяет наличие элементов; не оценивает подлинность и право на решение."""
    document_config = config["document_types"].get(document_type)
    if document_config is None:
        raise ValueError(f"Неизвестный тип документа: {document_type}")

    missing_fields: list[str] = []
    source_by_field: dict[str, str] = {}
    for key, field_config in document_config["fields"].items():
        value = fields.get(key, NOT_FOUND)
        if field_config["type"] == "boolean":
            absent = value is not True
        else:
            absent = not isinstance(value, str) or value.strip().casefold() == NOT_FOUND
        if absent:
            missing_fields.append(key)
            source_by_field[key] = str(field_config["rule"])

    if missing_fields:
        sources = _unique(
            source_by_field[key] for key in missing_fields if key in source_by_field
        )
        status = "missing_fields"
    else:
        sources = _unique(document_config["required_rules"])
        status = "document_ok"

    missing_rules = [source for source in sources if source not in rules]
    if missing_rules:
        raise ValueError(
            "В configs/fields.yaml указаны пункты, которых нет в data/rules.md: "
            + ", ".join(missing_rules)
        )
    return {
        "status": status,
        "missing_fields": missing_fields,
        "sources": [f"rule:{source}" for source in sources],
    }


def missing_field_labels(
    document_type: str, missing_fields: list[str], config: dict[str, Any]
) -> list[str]:
    fields = config["document_types"][document_type]["fields"]
    return [fields[key]["label"] for key in missing_fields]


def format_rules(sources: list[str]) -> str:
    return ", ".join(source.removeprefix("rule:") for source in sources)


def _unique(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values))
