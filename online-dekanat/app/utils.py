"""Общие преобразования текста и дат."""

from __future__ import annotations

import re
from datetime import date

NOT_FOUND = "не найдено"

MONTHS = {
    "января": 1,
    "январь": 1,
    "февраля": 2,
    "февраль": 2,
    "марта": 3,
    "март": 3,
    "апреля": 4,
    "апрель": 4,
    "мая": 5,
    "май": 5,
    "июня": 6,
    "июнь": 6,
    "июля": 7,
    "июль": 7,
    "августа": 8,
    "август": 8,
    "сентября": 9,
    "сентябрь": 9,
    "октября": 10,
    "октябрь": 10,
    "ноября": 11,
    "ноябрь": 11,
    "декабря": 12,
    "декабрь": 12,
}


def normalize_text(value: str) -> str:
    """Нормализует пробелы и типографские кавычки, не меняя смысл."""
    value = value.translate(
        str.maketrans(
            {
                "\u00a0": " ",
                "\u00ad": "-",
                "\u2010": "-",
                "\u2011": "-",
            }
        )
    ).strip()
    value = re.sub(r"\s+", " ", value)
    return value.translate(str.maketrans({"«": '"', "»": '"', "“": '"', "”": '"'}))


def normalize_date(value: str) -> str:
    """Преобразует распространённые русские форматы даты в YYYY-MM-DD."""
    value = normalize_text(value).casefold().replace("ё", "е")

    iso_match = re.search(r"\b(\d{4})[-./](\d{1,2})[-./](\d{1,2})\b", value)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        return _iso_date(year, month, day)

    numeric_match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", value)
    if numeric_match:
        day, month, year = map(int, numeric_match.groups())
        return _iso_date(year, month, day)

    russian_match = re.search(
        r"\b(\d{1,2})\s+([а-я]+)\s+(\d{4})(?:\s*г(?:ода|\.)?)?\b", value
    )
    if russian_match:
        day = int(russian_match.group(1))
        month_name = russian_match.group(2)
        year = int(russian_match.group(3))
        month = MONTHS.get(month_name)
        if month:
            return _iso_date(year, month, day)

    return NOT_FOUND


def _iso_date(year: int, month: int, day: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return NOT_FOUND


def normalize_field_value(value: str, value_type: str) -> str:
    """Нормализует значения в соответствии с их типом из fields.yaml."""
    value = normalize_text(value).strip(" \t\r\n:;,.")
    if not value or re.fullmatch(r"[_—–.\-·\s]+", value):
        return NOT_FOUND
    if value_type == "date":
        return normalize_date(value)
    if value_type == "integer_string":
        match = re.search(r"\d+", value)
        return str(int(match.group())) if match else NOT_FOUND
    return value if value.casefold() != NOT_FOUND else NOT_FOUND
