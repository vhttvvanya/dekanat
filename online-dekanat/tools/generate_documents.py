"""Создаёт учебные PNG/PDF по эталонным полям открытого набора."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pymupdf

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.utils import NOT_FOUND

FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]

TITLES = {
    "study_certificate": "СПРАВКА ОБ ОБУЧЕНИИ",
    "academic_leave_application": "ЗАЯВЛЕНИЕ НА АКАДЕМИЧЕСКИЙ ОТПУСК",
    "internship_certificate": "СПРАВКА О ПРАКТИКЕ",
}

FIELD_ROWS = {
    "study_certificate": [
        ("student_name", "ФИО студента"),
        ("university", "Название вуза"),
        ("program", "Направление подготовки"),
        ("study_form", "Форма обучения"),
        ("study_start", "Начало периода обучения"),
        ("study_end", "Окончание периода обучения"),
        ("document_number", "Номер справки"),
        ("issue_date", "Дата выдачи"),
    ],
    "academic_leave_application": [
        ("student_name", "ФИО студента"),
        ("group", "Учебная группа"),
        ("course", "Курс"),
        ("leave_reason", "Причина отпуска"),
        ("leave_start", "Дата начала отпуска"),
        ("leave_end", "Дата окончания отпуска"),
        ("application_date", "Дата заявления"),
    ],
    "internship_certificate": [
        ("student_name", "ФИО студента"),
        ("organization", "Название организации"),
        ("internship_start", "Дата начала практики"),
        ("internship_end", "Дата окончания практики"),
        ("supervisor_name", "ФИО руководителя практики"),
        ("grade", "Оценка"),
        ("document_number", "Номер справки"),
        ("issue_date", "Дата выдачи"),
    ],
}

RUSSIAN_MONTHS = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def _font_path() -> Path:
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Не найден системный TTF-шрифт с кириллицей.")


def _format_value(key: str, value: object, document_id: str) -> str:
    if value is True or value is False:
        return ""
    text = str(value)
    if text.casefold() == NOT_FOUND:
        return ""
    if _is_iso_date(text):
        parsed = datetime.strptime(text, "%Y-%m-%d")
        if int(document_id.split("-")[-1]) % 3 == 0:
            return f"{parsed.day} {RUSSIAN_MONTHS[parsed.month]} {parsed.year} года"
        return parsed.strftime("%d.%m.%Y")
    return text


def _is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _draw_signature(page: pymupdf.Page, origin: tuple[float, float]) -> None:
    x, y = origin
    shape = page.new_shape()
    shape.draw_line((x, y + 8), (x + 28, y - 10))
    shape.draw_line((x + 24, y - 8), (x + 70, y + 12))
    shape.draw_line((x + 66, y + 10), (x + 118, y - 6))
    shape.draw_curve((x + 10, y + 14), (x + 40, y + 22), (x + 90, y + 4))
    shape.finish(color=(0.22, 0.12, 0.08), width=1.8)
    shape.commit()


def _draw_seal(page: pymupdf.Page, center: tuple[float, float]) -> None:
    shape = page.new_shape()
    shape.draw_circle(center, 34)
    shape.draw_circle(center, 28)
    shape.finish(color=(0.75, 0.08, 0.08), width=2.4)
    shape.commit()
    page.insert_text(
        (center[0] - 18, center[1] + 4),
        "М.П.",
        fontsize=9,
        fontname="DocFont",
        color=(0.75, 0.08, 0.08),
    )


def render_document(item: dict, output_dir: Path, fontfile: Path) -> None:
    document_id = item["document_id"]
    document_type = item["document_type"]
    fields = item["fields"]
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="DocFont", fontfile=str(fontfile))

    page.insert_text((56, 56), TITLES[document_type], fontsize=16, fontname="DocFont")
    page.insert_text(
        (56, 78),
        "Учебный университет «Меридиан» · предварительная проверка",
        fontsize=9,
        fontname="DocFont",
        color=(0.25, 0.25, 0.25),
    )

    y = 120
    for key, label in FIELD_ROWS[document_type]:
        value = _format_value(key, fields[key], document_id)
        line = f"{label}: {value}".rstrip()
        page.insert_text((56, y), line, fontsize=12, fontname="DocFont")
        y += 28

    signature_y = 720
    page.insert_text((56, signature_y), "Подпись:", fontsize=12, fontname="DocFont")
    if fields.get("signature_present") is True:
        _draw_signature(page, (130, signature_y - 6))

    if "seal_present" in fields:
        page.insert_text((360, signature_y), "Печать:", fontsize=12, fontname="DocFont")
        if fields.get("seal_present") is True:
            _draw_seal(page, (490, signature_y - 4))

    pdf_path = output_dir / f"{document_id}.pdf"
    png_path = output_dir / f"{document_id}.png"
    doc.save(pdf_path)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
    pixmap.save(png_path)
    doc.close()


def main() -> None:
    reference = json.loads(
        (PROJECT_DIR / "data" / "reference_results.json").read_text(encoding="utf-8")
    )
    output_dir = PROJECT_DIR / "data" / "documents"
    output_dir.mkdir(parents=True, exist_ok=True)
    fontfile = _font_path()
    for item in reference["documents"]:
        render_document(item, output_dir, fontfile)
        print(item["document_id"])


if __name__ == "__main__":
    main()
