"""Правила ответов на вопросы: только извлечённые поля и пункты rules.md."""

from __future__ import annotations

from typing import Any

from app.utils import NOT_FOUND
from app.validator import format_rules, missing_field_labels

NO_ANSWER = (
    "В документе и в Положении нет информации для ответа на этот вопрос. "
    "Обратитесь в деканат."
)
FINAL_DECISION = "сотрудник деканата"


def answer_question(
    question: str,
    document_type: str,
    fields: dict[str, Any],
    validation: dict[str, Any],
    config: dict[str, Any],
    rules: dict[str, str],
) -> dict[str, Any]:
    """Возвращает ответ, воспроизводимое значение и точные источники."""
    normalized_question = question.casefold().replace("ё", "е")
    if _is_completeness_question(normalized_question):
        return _completeness_answer(document_type, validation, config, rules)

    if (
        "кто принимает окончательное решение" in normalized_question
        or "окончательное решение о принятии" in normalized_question
    ):
        if "1.3" not in rules:
            return _unanswerable()
        return {
            "answerable": True,
            "value": FINAL_DECISION,
            "answer": "Окончательное решение принимает сотрудник деканата, пункт 1.3 Положения.",
            "sources": ["rule:1.3"],
        }

    field_key = _resolve_field(normalized_question, document_type, config)
    if field_key:
        value = fields.get(field_key, NOT_FOUND)
        if value == NOT_FOUND or value is None:
            return _unanswerable()
        field_config = config["document_types"][document_type]["fields"][field_key]
        if isinstance(value, bool):
            printable = "Да, обнаружена" if value else "Нет, не обнаружена"
            structured_value = "true" if value else "false"
        else:
            printable = str(value)
            structured_value = str(value)
        return {
            "answerable": True,
            "value": structured_value,
            "answer": f"{field_config['label']}: {printable}.",
            "sources": [f"field:{field_key}"],
        }
    return _unanswerable()


def _is_completeness_question(question: str) -> bool:
    return any(
        keyword in question
        for keyword in (
            "обязательн",
            "комплект",
            "в порядке",
            "достаточно ли",
            "чего не хватает",
            "хватит ли",
            "все сведения",
            "предварительн",
        )
    )


def _resolve_field(
    question: str, document_type: str, config: dict[str, Any]
) -> str | None:
    candidates = []
    for key, field_config in config["document_types"][document_type]["fields"].items():
        if field_config["type"] == "boolean":
            continue
        terms = [field_config["label"], *field_config.get("aliases", [])]
        for term in terms:
            normalized_term = term.casefold().replace("ё", "е")
            if normalized_term in question:
                candidates.append((len(normalized_term), key))
    return max(candidates)[1] if candidates else None


def _completeness_answer(
    document_type: str,
    validation: dict[str, Any],
    config: dict[str, Any],
    rules: dict[str, str],
) -> dict[str, Any]:
    sources = validation["sources"]
    citations = format_rules(sources)
    if validation["status"] == "document_ok":
        answer = (
            f"Документ содержит все обязательные сведения по пунктам {citations} "
            "Положения. Окончательное решение примет сотрудник деканата."
        )
    else:
        labels = missing_field_labels(
            document_type, validation["missing_fields"], config
        )
        details = "; ".join(labels)
        answer = (
            f"Предварительно не хватает: {details}. Требования указаны в пунктах "
            f"{citations} Положения. Окончательное решение примет сотрудник деканата."
        )
    return {
        "answerable": True,
        "value": validation["status"],
        "answer": answer,
        "sources": sources,
    }


def _unanswerable() -> dict[str, Any]:
    return {"answerable": False, "value": None, "answer": NO_ANSWER, "sources": []}
