"""Быстрые проверки дат, извлечения, QA и валидации без OCR-запуска."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.classifier import detect_document_type
from app.extractor import extract_fields
from app.ocr import OCRResult, graphic_mark_present
from app.qa import answer_question
from app.utils import normalize_date, normalize_field_value
from app.validator import parse_rules, validate_document


class PilotPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = yaml.safe_load(
            (PROJECT_DIR / "configs" / "fields.yaml").read_text(encoding="utf-8")
        )
        cls.rules = parse_rules(PROJECT_DIR / "data" / "rules.md")

    def test_date_normalization(self) -> None:
        self.assertEqual(normalize_date("01.09.2026"), "2026-09-01")
        self.assertEqual(normalize_date("1 ноября 2026 года"), "2026-11-01")
        self.assertEqual(normalize_date("2026-09-01"), "2026-09-01")
        self.assertEqual(normalize_date("31.02.2026"), "не найдено")
        self.assertEqual(normalize_field_value("________________", "string"), "не найдено")
        self.assertEqual(normalize_field_value("ОБ\u00ad1001", "string"), "ОБ-1001")
        self.assertEqual(normalize_field_value("ЖР\u00ad25\u00ad1", "string"), "ЖР-25-1")

    def test_detects_stamp_to_the_right_of_its_label(self) -> None:
        image = Image.new("RGB", (1190, 1684), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((914, 1375, 1047, 1500), outline=(190, 20, 30), width=5)
        draw.ellipse((923, 1384, 1038, 1491), outline=(190, 20, 30), width=4)
        words = [
            {
                "text": "Печать:",
                "x1": 722,
                "y1": 1423,
                "x2": 805,
                "y2": 1440,
            }
        ]
        self.assertTrue(graphic_mark_present(image, words, ["печать"], "seal"))
        self.assertFalse(
            graphic_mark_present(
                Image.new("RGB", image.size, "white"), words, ["печать"], "seal"
            )
        )

    def test_extracts_text_fields_and_defaults_missing(self) -> None:
        text = "\n".join(
            [
                "ФИО студента: Александров Артём Игоревич",
                "Название вуза: Учебный университет «Меридиан»",
                "Форма обучения: очная",
                "Дата выдачи: 01.09.2026",
            ]
        )
        result = OCRResult(text, "test", Image.new("RGB", (800, 1100), "white"), [], 98)
        fields = extract_fields("study_certificate", result, self.config)
        self.assertEqual(fields["student_name"], "Александров Артём Игоревич")
        self.assertEqual(fields["university"], 'Учебный университет "Меридиан"')
        self.assertEqual(fields["issue_date"], "2026-09-01")
        self.assertEqual(fields["program"], "не найдено")
        self.assertIs(fields["signature_present"], False)
        self.assertIs(fields["seal_present"], False)

    def test_recovers_latin_lookalikes_in_russian_labels(self) -> None:
        result = OCRResult(
            "Учебная rpynna: ЖР-25-1",
            "test",
            Image.new("RGB", (800, 1100), "white"),
            [],
            90,
        )
        fields = extract_fields("academic_leave_application", result, self.config)
        self.assertEqual(fields["group"], "ЖР-25-1")

    def test_missing_fields_refer_only_to_rules_for_missing_items(self) -> None:
        fields = {
            "student_name": "Тестовый Студент",
            "university": "Тестовый вуз",
            "program": "09.03.01",
            "study_form": "очная",
            "study_start": "2025-09-01",
            "study_end": "2026-08-31",
            "document_number": "А-10",
            "issue_date": "не найдено",
            "signature_present": True,
            "seal_present": True,
        }
        validation = validate_document(
            "study_certificate", fields, self.config, self.rules
        )
        self.assertEqual(validation["status"], "missing_fields")
        self.assertEqual(validation["missing_fields"], ["issue_date"])
        self.assertEqual(validation["sources"], ["rule:3.1"])

    def test_answer_is_grounded_or_declines(self) -> None:
        fields = {"student_name": "Иванов Иван Иванович"}
        validation = {
            "status": "missing_fields",
            "missing_fields": ["issue_date"],
            "sources": ["rule:3.1"],
        }
        answer = answer_question(
            "Укажи ФИО студента",
            "study_certificate",
            fields,
            validation,
            self.config,
            self.rules,
        )
        self.assertEqual(answer["value"], "Иванов Иван Иванович")
        self.assertEqual(answer["sources"], ["field:student_name"])

        unknown = answer_question(
            "Какова стоимость обучения?",
            "study_certificate",
            fields,
            validation,
            self.config,
            self.rules,
        )
        self.assertIs(unknown["answerable"], False)
        self.assertIsNone(unknown["value"])
        self.assertEqual(unknown["sources"], [])

    def test_detects_document_type_from_keywords(self) -> None:
        kind, scores = detect_document_type(
            "СПРАВКА О ПРАКТИКЕ\nНазвание организации: ООО Тест",
            self.config,
        )
        self.assertEqual(kind, "internship_certificate")
        self.assertGreater(
            scores["internship_certificate"], scores["study_certificate"]
        )

    def test_detects_type_in_pdf_text_with_nonbreaking_spaces(self) -> None:
        kind, scores = detect_document_type(
            "ЗАЯВЛЕНИЕ\u00a0НА\u00a0АКАДЕМИЧЕСКИЙ\u00a0ОТПУСК\n"
            "Учебная\u00a0группа: ЖР\u00ad25\u00ad1",
            self.config,
        )
        self.assertEqual(kind, "academic_leave_application")
        self.assertGreater(
            scores["academic_leave_application"], scores["study_certificate"]
        )

    def test_completeness_question_without_exact_phrase(self) -> None:
        validation = {
            "status": "document_ok",
            "missing_fields": [],
            "sources": ["rule:3.1", "rule:3.2", "rule:3.3"],
        }
        answer = answer_question(
            "Хватит ли документа для предварительной проверки?",
            "study_certificate",
            {},
            validation,
            self.config,
            self.rules,
        )
        self.assertEqual(answer["value"], "document_ok")
        self.assertEqual(answer["sources"], validation["sources"])


if __name__ == "__main__":
    unittest.main()
