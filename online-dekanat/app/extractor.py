"""Извлечение полей по конфигурации, без генеративных моделей."""

from __future__ import annotations

import re
from typing import Any

from PIL import Image

from app.ocr import OCRResult, graphic_mark_present
from app.utils import NOT_FOUND, normalize_field_value, normalize_text

_CYRILLIC_LOOKALIKE_TRANSLATION = str.maketrans(
    {
        "a": "а",
        "b": "в",
        "c": "с",
        "e": "е",
        "k": "к",
        "m": "м",
        "n": "п",
        "o": "о",
        "p": "р",
        "r": "г",
        "t": "т",
        "x": "х",
        "y": "у",
    }
)


def extract_fields(
    document_type: str,
    ocr_result: OCRResult,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Возвращает все поля типа документа, отсутствующие значения помечает."""
    document_config = config["document_types"].get(document_type)
    if document_config is None:
        raise ValueError(f"Неизвестный тип документа: {document_type}")

    fields: dict[str, Any] = {}
    for key, field_config in document_config["fields"].items():
        if field_config["type"] == "boolean":
            aliases = field_config.get("mark_aliases", field_config.get("aliases", []))
            fields[key] = graphic_mark_present(
                ocr_result.image,
                ocr_result.words,
                aliases,
                field_config.get("mark", ""),
            )
            continue

        raw_value = _find_labeled_value(ocr_result.text, field_config.get("aliases", []))
        fields[key] = (
            normalize_field_value(raw_value, field_config["type"])
            if raw_value is not None
            else NOT_FOUND
        )
    return fields


def locate_fields(
    document_type: str,
    ocr_result: OCRResult,
    config: dict[str, Any],
) -> dict[str, tuple[int, int, int, int]]:
    """Находит рамки полей по строкам OCR — для бонусной подсветки."""
    document_config = config["document_types"][document_type]
    lines: dict[tuple[int, int, int, int], list[dict[str, Any]]] = {}
    for word in ocr_result.words:
        lines.setdefault(word["line_key"], []).append(word)

    boxes: dict[str, tuple[int, int, int, int]] = {}
    for key, field_config in document_config["fields"].items():
        aliases = sorted(field_config.get("aliases", []), key=len, reverse=True)
        for words in lines.values():
            line_text = normalize_text(" ".join(str(word["text"]) for word in words))
            searchable = line_text.casefold().translate(_CYRILLIC_LOOKALIKE_TRANSLATION)
            if any(
                alias.casefold().translate(_CYRILLIC_LOOKALIKE_TRANSLATION) in searchable
                for alias in aliases
            ):
                boxes[key] = (
                    min(int(word["x1"]) for word in words),
                    min(int(word["y1"]) for word in words),
                    max(int(word["x2"]) for word in words),
                    max(int(word["y2"]) for word in words),
                )
                break
    return boxes


def _find_labeled_value(text: str, aliases: list[str]) -> str | None:
    lines = [normalize_text(line) for line in text.splitlines() if normalize_text(line)]
    aliases = sorted(aliases, key=len, reverse=True)
    for index, line in enumerate(lines):
        searchable_line = line.casefold().translate(_CYRILLIC_LOOKALIKE_TRANSLATION)
        for alias in aliases:
            searchable_alias = alias.casefold().translate(
                _CYRILLIC_LOOKALIKE_TRANSLATION
            )
            match = re.match(
                rf"^\s*{re.escape(searchable_alias)}\s*[:：—–-]\s*(.*?)\s*$",
                searchable_line,
            )
            if match:
                value = match.group(1).strip()
                if value:
                    delimiter = re.search(r"[:：—–-]", line)
                    if delimiter:
                        return line[delimiter.end() :].strip()
                next_value = _value_on_next_line(lines, index)
                if next_value:
                    return next_value
            # OCR sometimes drops punctuation or reads a dash as whitespace.
            match = re.match(
                rf"^\s*{re.escape(searchable_alias)}\s+(.+?)\s*$",
                searchable_line,
            )
            if match and match.group(1).strip():
                prefix_length = len(searchable_alias)
                return line[prefix_length:].strip(" :：—–-")
            if searchable_line.rstrip(" :：—–-") == searchable_alias:
                next_value = _value_on_next_line(lines, index)
                if next_value:
                    return next_value
    return None


def _value_on_next_line(lines: list[str], index: int) -> str | None:
    if index + 1 >= len(lines):
        return None
    candidate = lines[index + 1]
    if re.match(r".+[:：—–-]\s*", candidate) and len(candidate.split(":", 1)[0]) <= 40:
        return None
    return candidate


def build_field_rows(
    document_type: str, fields: dict[str, Any], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Подготавливает поля к выводу в Streamlit."""
    rows = []
    for key, field_config in config["document_types"][document_type]["fields"].items():
        value = fields[key]
        if isinstance(value, bool):
            display_value = "Есть" if value else "Не обнаружена"
        else:
            display_value = value
        rows.append({"Поле": field_config["label"], "Значение": display_value})
    return rows
