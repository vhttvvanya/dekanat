"""Общий пайплайн: OCR → поля → проверка → ответ."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.classifier import detect_document_type
from app.extractor import extract_fields, locate_fields
from app.highlight import annotate_fields, source_field_key
from app.ocr import ocr_document
from app.qa import answer_question
from app.validator import parse_rules, validate_document

PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "fields.yaml"
RULES_PATH = PROJECT_DIR / "data" / "rules.md"
DEFAULT_COMPLETENESS_QUESTION = (
    "Содержит ли документ все обязательные сведения по Положению?"
)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def load_rules(path: Path = RULES_PATH) -> dict[str, str]:
    return parse_rules(path)


def analyze_document(
    file_bytes: bytes,
    filename: str,
    *,
    document_type: str | None,
    config: dict[str, Any],
    rules: dict[str, str],
    auto_detect: bool = False,
) -> dict[str, Any]:
    ocr_result = ocr_document(file_bytes, filename)
    resolved_type = document_type
    detection_scores: dict[str, int] = {}
    if auto_detect or not resolved_type:
        resolved_type, detection_scores = detect_document_type(ocr_result.text, config)
    if resolved_type not in config["document_types"]:
        raise ValueError(f"Неизвестный тип документа: {resolved_type}")

    fields = extract_fields(resolved_type, ocr_result, config)
    boxes = locate_fields(resolved_type, ocr_result, config)
    validation = validate_document(resolved_type, fields, config, rules)
    return {
        "document_type": resolved_type,
        "detection_scores": detection_scores,
        "fields": fields,
        "boxes": boxes,
        "validation": validation,
        "ocr": ocr_result,
    }


def answer_analysis(
    analysis: dict[str, Any],
    question: str,
    config: dict[str, Any],
    rules: dict[str, str],
) -> dict[str, Any]:
    asked = question.strip() or DEFAULT_COMPLETENESS_QUESTION
    answer = answer_question(
        asked,
        analysis["document_type"],
        analysis["fields"],
        analysis["validation"],
        config,
        rules,
    )
    annotated = annotate_fields(
        analysis["ocr"].image,
        analysis["boxes"],
        source_field_key(answer),
    )
    return {
        **analysis,
        "question": asked,
        "answer": answer,
        "annotated_image": annotated,
    }


def process_document(
    file_bytes: bytes,
    filename: str,
    *,
    document_type: str | None,
    question: str,
    config: dict[str, Any],
    rules: dict[str, str],
    auto_detect: bool = False,
) -> dict[str, Any]:
    analysis = analyze_document(
        file_bytes,
        filename,
        document_type=document_type,
        config=config,
        rules=rules,
        auto_detect=auto_detect,
    )
    return answer_analysis(analysis, question, config, rules)


def build_result_record(
    document_id: str,
    document_type: str,
    fields: dict[str, Any],
    validation: dict[str, Any],
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "document_type": document_type,
        "fields": fields,
        "validation": validation,
        "answers": answers,
    }
