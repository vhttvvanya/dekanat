"""OCR и растеризация одностраничных изображений/PDF через Tesseract."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import pymupdf
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pytesseract import Output

from app.tesseract_setup import available_languages, configure_tesseract, tesseract_config

configure_tesseract()

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}


@dataclass
class OCRResult:
    text: str
    source: str
    image: Image.Image
    words: list[dict[str, Any]]
    average_confidence: float | None


def ocr_document(file_bytes: bytes, filename: str) -> OCRResult:
    """Читает текстовый слой PDF или распознаёт изображение локальным Tesseract."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError("Поддерживаются только JPG, PNG и одностраничные PDF.")
    if not file_bytes:
        raise ValueError("Файл пуст.")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("Размер файла превышает ограничение пилота 15 МБ.")

    image, pdf_text = _load_page(file_bytes, suffix)
    image = ImageOps.exif_transpose(image).convert("RGB")
    image = _correct_orientation(image)

    installed_languages = available_languages()
    missing_languages = {"rus"} - installed_languages
    if missing_languages:
        missing = ", ".join(sorted(missing_languages))
        raise RuntimeError(
            f"В Tesseract не найдены языковые данные: {missing}. "
            "Установите Tesseract с русским языковым пакетом."
        )

    processed = _preprocess(image)
    data = pytesseract.image_to_data(
        processed,
        lang="rus",
        config=tesseract_config(),
        output_type=Output.DICT,
    )
    words: list[dict[str, Any]] = []
    line_parts: dict[tuple[int, int, int, int], list[str]] = {}
    confidences: list[float] = []
    for index, raw_word in enumerate(data["text"]):
        word = str(raw_word).strip()
        if not word:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1
        if confidence >= 0:
            confidences.append(confidence)
        x = int(data["left"][index])
        y = int(data["top"][index])
        width = int(data["width"][index])
        height = int(data["height"][index])
        words.append(
            {
                "text": word,
                "confidence": confidence,
                "x1": x,
                "y1": y,
                "x2": x + width,
                "y2": y + height,
                "line_key": (
                    int(data["block_num"][index]),
                    int(data["par_num"][index]),
                    int(data["line_num"][index]),
                    int(data["page_num"][index]),
                ),
            }
        )
        line_parts.setdefault(words[-1]["line_key"], []).append(word)

    ocr_text = "\n".join(" ".join(parts) for parts in line_parts.values()).strip()
    # В PDF со встроенным текстом используем точные символы, но OCR всё равно
    # снимает координаты слов для визуальной проверки подписи и печати.
    has_pdf_text_layer = bool(pdf_text.strip())
    text = pdf_text.strip() if has_pdf_text_layer else ocr_text
    average_confidence = (
        sum(confidences) / len(confidences) if confidences else None
    )
    return OCRResult(
        text=text,
        source=(
            "Текстовый слой PDF; Tesseract проверил изображение отметок"
            if has_pdf_text_layer
            else "Локальный OCR: Tesseract (русский)"
        ),
        image=image,
        words=words,
        average_confidence=average_confidence,
    )


def _load_page(file_bytes: bytes, suffix: str) -> tuple[Image.Image, str]:
    if suffix != ".pdf":
        try:
            image = Image.open(BytesIO(file_bytes))
            image.load()
        except Exception as exc:
            raise ValueError("Не удалось открыть изображение. Проверьте файл.") from exc
        return image, ""

    try:
        document = pymupdf.open(stream=file_bytes, filetype="pdf")
        if document.is_encrypted:
            raise ValueError("PDF защищён паролем и не может быть обработан.")
        if len(document) != 1:
            raise ValueError(
                f"Пилот принимает только одностраничные PDF; в файле {len(document)} стр."
            )
        page = document[0]
        pdf_text = page.get_text("text")
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
        document.close()
        return image, pdf_text
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Не удалось прочитать PDF. Проверьте файл.") from exc


def _preprocess(image: Image.Image) -> Image.Image:
    """Улучшает контраст и слегка сглаживает фон перед OCR."""
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.35)
    gray = ImageEnhance.Sharpness(gray).enhance(1.2)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    return gray


def _correct_orientation(image: Image.Image) -> Image.Image:
    """Поворачивает страницу по OSD Tesseract, если угол кратен 90°."""
    try:
        osd = pytesseract.image_to_osd(image, config=tesseract_config("--psm 0"))
    except Exception:
        return image
    rotate = 0
    for line in str(osd).splitlines():
        if line.lower().startswith("rotate:"):
            try:
                rotate = int(line.split(":", 1)[1].strip())
            except ValueError:
                rotate = 0
    if rotate and rotate % 360 != 0:
        return image.rotate(360 - rotate, expand=True, fillcolor=(255, 255, 255))
    return image


def graphic_mark_present(
    image: Image.Image,
    words: list[dict[str, Any]],
    aliases: list[str],
    mark_kind: str,
) -> bool:
    """Оценивает графическую отметку рядом с напечатанной подписью/печатью.

    Проверяется только визуальная насыщенность области, не подлинность. Это
    эвристика пилота, а не надёжная экспертиза документа.
    """
    alias_words = {
        "".join(char for char in part.casefold().replace("ё", "е") if char.isalnum())
        for alias in aliases
        for part in alias.split()
    }
    anchors = [
        word
        for word in words
        if _word_matches_alias(str(word["text"]), alias_words)
    ]
    if not anchors:
        return False

    width, height = image.size
    # Слова Tesseract расположены по строкам, поэтому ищем место для графики
    # справа от подписи или небольшую область вокруг слов о печати.
    if mark_kind == "signature":
        # Внизу страницы может повторяться слово «Подпись» в дисклеймере.
        # Для графики нужна первая метка, расположенная в блоке документа.
        anchor = min(anchors, key=lambda item: int(item["y1"]))
    else:
        anchor = max(anchors, key=lambda item: int(item["x1"]))
    x1, y1, x2, y2 = (
        int(anchor["x1"]),
        int(anchor["y1"]),
        int(anchor["x2"]),
        int(anchor["y2"]),
    )
    if mark_kind == "signature":
        left = min(width, x2 + max(8, int(width * 0.015)))
        right = min(width, max(left + 10, int(width * 0.76)))
        top = max(0, y1 - 8)
        bottom = min(height, y2 + max(30, int(height * 0.035)))
        # Подпись отличаем от одной только печатной линии и текста подписи.
        # На открытых образцах есть разрыв между значениями с графикой и без.
        min_ink_fraction = 0.022
    else:
        padding_x = max(45, int(width * 0.035))
        padding_y = max(45, int(height * 0.04))
        left = max(0, x1 - padding_x)
        # Оттиск расположен справа от печатной метки; захватываем и эту область.
        right = min(width, x2 + max(padding_x, int(width * 0.22)))
        top = max(0, y1 - padding_y)
        bottom = min(height, y2 + padding_y)
        min_ink_fraction = 0.11

    if right <= left or bottom <= top:
        return False
    crop = image.crop((left, top, right, bottom)).convert("RGB")
    gray_histogram = crop.convert("L").histogram()
    pixel_count = max(1, crop.width * crop.height)
    dark_pixels = sum(gray_histogram[:145])
    dark_fraction = dark_pixels / pixel_count

    # Красные/синие штампы могут быть светлыми в градациях серого.
    saturation_histogram = crop.convert("HSV").getchannel("S").histogram()
    color_fraction = sum(saturation_histogram[55:]) / pixel_count
    return dark_fraction >= min_ink_fraction or (
        mark_kind == "seal" and color_fraction >= 0.015
    )


def _word_matches_alias(word: str, alias_words: set[str]) -> bool:
    normalized_word = "".join(
        char for char in word.casefold().replace("ё", "е") if char.isalnum()
    )
    if len(normalized_word) < 4:
        return False
    return normalized_word in alias_words
