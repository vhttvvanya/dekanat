"""Подсветка найденных полей на снимке документа."""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw


def annotate_fields(
    image: Image.Image,
    boxes: dict[str, tuple[int, int, int, int]],
    focus_key: str | None = None,
) -> Image.Image:
    """Рисует рамки вокруг найденных полей. Нужное поле выделяется ярче."""
    annotated = image.convert("RGB").copy()
    draw = ImageDraw.Draw(annotated)
    for key, box in boxes.items():
        color = (16, 160, 80) if key == focus_key else (30, 90, 200)
        width = 4 if key == focus_key else 2
        x1, y1, x2, y2 = box
        pad = 4
        draw.rectangle(
            (max(0, x1 - pad), max(0, y1 - pad), x2 + pad, y2 + pad),
            outline=color,
            width=width,
        )
    return annotated


def source_field_key(answer: dict[str, Any]) -> str | None:
    for source in answer.get("sources") or []:
        if isinstance(source, str) and source.startswith("field:"):
            return source.removeprefix("field:")
    return None
