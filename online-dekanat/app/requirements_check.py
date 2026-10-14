"""Проверка локальных системных OCR-компонентов при запуске."""

from __future__ import annotations

import pytesseract

from app.tesseract_setup import available_languages, configure_tesseract

configure_tesseract()


def check_tesseract() -> tuple[bool, str]:
    try:
        version = str(pytesseract.get_tesseract_version()).splitlines()[0]
        languages = available_languages()
    except Exception as exc:
        return False, f"Tesseract недоступен: {exc}"
    if "rus" not in languages:
        return False, "В Tesseract отсутствует пакет языковых данных rus."
    return True, f"Tesseract {version}; русский язык доступен."
