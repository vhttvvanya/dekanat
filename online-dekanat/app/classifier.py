"""Автоопределение типа документа по ключевым словам из YAML."""

from __future__ import annotations

from typing import Any

from app.utils import normalize_text


def detect_document_type(text: str, config: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """Возвращает наиболее вероятный тип и сырые баллы по каждому типу."""
    haystack = normalize_text(text).casefold().replace("ё", "е")
    scores: dict[str, int] = {}
    for document_type, document_config in config["document_types"].items():
        score = 0
        for keyword in document_config.get("detect_keywords", []):
            if keyword.casefold().replace("ё", "е") in haystack:
                score += 3
        for field_config in document_config["fields"].values():
            for alias in field_config.get("aliases", []):
                normalized = alias.casefold().replace("ё", "е")
                if len(normalized) >= 8 and normalized in haystack:
                    score += 1
        scores[document_type] = score
    best = max(scores, key=scores.get)
    return best, scores
