"""Поиск локального Tesseract и языковых данных проекта."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytesseract

PROJECT_DIR = Path(__file__).resolve().parents[1]
TESSDATA_DIR = PROJECT_DIR / "vendor" / "tessdata"

_WINDOWS_CANDIDATES = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]


def configure_tesseract() -> Path | None:
    """Настраивает pytesseract. Возвращает путь к исполняемому файлу, если найден."""
    executable = _find_tesseract()
    if executable is not None:
        pytesseract.pytesseract.tesseract_cmd = str(executable)
    tessdata = _usable_tessdata_dir()
    if tessdata is not None:
        os.environ["TESSDATA_PREFIX"] = str(tessdata.parent)
    return executable


def tesseract_config(extra: str = "--oem 3 --psm 6") -> str:
    tessdata = _usable_tessdata_dir()
    if tessdata is not None:
        path = str(tessdata).replace("\\", "/")
        return f"--tessdata-dir {path} {extra}"
    return extra


def _usable_tessdata_dir() -> Path | None:
    """Tesseract на Windows ломается на не-ASCII путях, поэтому копируем данные."""
    if not TESSDATA_DIR.is_dir():
        return None
    try:
        TESSDATA_DIR.resolve().as_posix().encode("ascii")
        return TESSDATA_DIR
    except UnicodeEncodeError:
        pass
    fallback = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "online-dekanat" / "tessdata"
    fallback.mkdir(parents=True, exist_ok=True)
    for source in TESSDATA_DIR.glob("*.traineddata"):
        target = fallback / source.name
        if not target.is_file() or target.stat().st_size != source.stat().st_size:
            target.write_bytes(source.read_bytes())
    return fallback


def available_languages() -> set[str]:
    languages: set[str] = set()
    tessdata = _usable_tessdata_dir()
    if tessdata is not None:
        for path in tessdata.glob("*.traineddata"):
            languages.add(path.stem)
    if languages:
        return languages
    try:
        return set(pytesseract.get_languages(config=tesseract_config("")))
    except UnicodeDecodeError:
        return set()


def _find_tesseract() -> Path | None:
    which = shutil.which("tesseract")
    if which:
        return Path(which)
    for candidate in _WINDOWS_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None
