"""Streamlit-интерфейс локального пилота «Онлайн-деканат»."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.extractor import build_field_rows
from app.pipeline import (
    DEFAULT_COMPLETENESS_QUESTION,
    load_config,
    load_rules,
    process_document,
)
from app.requirements_check import check_tesseract
from app.validator import format_rules

st.set_page_config(page_title="Онлайн-деканат", page_icon="📄", layout="wide")


@st.cache_data
def cached_config() -> dict[str, Any]:
    return load_config()


@st.cache_data
def cached_rules() -> dict[str, str]:
    return load_rules()


@st.cache_data
def load_sample_manifest() -> tuple[dict[str, str], dict[str, str]]:
    manifest_path = PROJECT_DIR / "data" / "documents.json"
    samples = json.loads(manifest_path.read_text(encoding="utf-8"))
    sample_types = {item["document_id"]: item["document_type"] for item in samples}
    labels = {}
    config = cached_config()
    for sample in samples:
        kind_label = config["document_types"][sample_types[sample["document_id"]]]["label"]
        labels[sample["document_id"]] = f'{sample["document_id"]} · {kind_label}'
    return sample_types, labels


config = cached_config()
rules = cached_rules()
sample_types, sample_labels = load_sample_manifest()
document_types = config["document_types"]

st.title("Онлайн-деканат")
st.caption("Цифровой секретарь для чтения студенческих документов и предварительной проверки.")
st.info(
    "Пилот обрабатывает файл локально. Внешние OCR- и языковые API не используются. "
    "Проверка предварительная: решение всегда принимает сотрудник деканата."
)

with st.sidebar:
    st.header("Документ")
    ocr_ready, ocr_status = check_tesseract()
    if ocr_ready:
        st.caption(ocr_status)
    else:
        st.error(ocr_status)
    uploaded_file = st.file_uploader(
        "Загрузите JPG, PNG или одностраничный PDF",
        type=["jpg", "jpeg", "png", "pdf"],
        help="До 15 МБ. Многостраничные PDF пока не поддерживаются.",
    )
    sample_id = st.selectbox(
        "Или возьмите пример из набора",
        options=[""] + list(sample_labels),
        format_func=lambda value: "— не использовать пример —"
        if not value
        else sample_labels[value],
    )
    auto_detect = st.checkbox("Определить тип автоматически", value=True)
    default_type = sample_types.get(sample_id, "study_certificate")
    selected_type = st.selectbox(
        "Тип документа",
        options=list(document_types),
        index=list(document_types).index(default_type),
        format_func=lambda value: document_types[value]["label"],
        disabled=auto_detect,
    )

question = st.text_input(
    "Вопрос по документу",
    placeholder="Например: Какова дата выдачи? Если пусто — проверка комплектности.",
)
col_process, col_check = st.columns(2)
process_clicked = col_process.button("Обработать документ", type="primary", use_container_width=True)
completeness_clicked = col_check.button("Проверить комплектность", use_container_width=True)


def _get_input(uploaded_file: Any, sample_id: str) -> tuple[bytes, str, str]:
    if uploaded_file is not None:
        return uploaded_file.getvalue(), uploaded_file.name, "pilot-document"
    if not sample_id:
        raise ValueError("Загрузите файл или выберите пример из набора.")
    for extension in (".pdf", ".png", ".jpg"):
        sample_path = PROJECT_DIR / "data" / "documents" / f"{sample_id}{extension}"
        if sample_path.is_file():
            return sample_path.read_bytes(), sample_path.name, sample_id
    raise FileNotFoundError(f"Не найден пример {sample_id}.")


def _render_result(document_id: str, result: dict[str, Any], cfg: dict[str, Any]) -> None:
    document_type = result["document_type"]
    validation = result["validation"]
    answer = result["answer"]
    ocr_result = result["ocr"]

    st.subheader("Результат")
    st.caption(ocr_result.source)
    if result["detection_scores"]:
        st.caption(f"Определён тип: {cfg['document_types'][document_type]['label']}")
    if ocr_result.average_confidence is not None:
        st.caption(f"Средняя уверенность OCR: {ocr_result.average_confidence:.0f}%")

    if validation["status"] == "document_ok":
        st.success(
            f"Обязательные поля обнаружены. Основание: пункты "
            f"{format_rules(validation['sources'])}. Это не решение о принятии документа."
        )
    else:
        missing = [
            cfg["document_types"][document_type]["fields"][key]["label"]
            for key in validation["missing_fields"]
        ]
        st.warning(
            f"Не удалось подтвердить все обязательные сведения: {', '.join(missing)}. "
            f"Основание: пункты {format_rules(validation['sources'])}."
        )

    preview, details = st.columns([1.05, 0.95])
    with preview:
        st.markdown("#### Документ с подсветкой полей")
        st.image(result["annotated_image"], use_container_width=True)
    with details:
        st.markdown("#### Карточка документа")
        st.dataframe(
            build_field_rows(document_type, result["fields"], cfg),
            hide_index=True,
            use_container_width=True,
        )
        st.markdown("#### Ответ")
        st.write(answer["answer"])
        if answer["sources"]:
            st.caption("Источники: " + ", ".join(answer["sources"]))
        else:
            st.caption("Источник не найден.")

    with st.expander("Распознанный текст"):
        st.text(ocr_result.text or "Текст не распознан.")
    with st.expander("Пункты правил, использованные в ответе"):
        for source in answer["sources"]:
            if source.startswith("rule:"):
                rule_id = source.removeprefix("rule:")
                st.markdown(f"**Пункт {rule_id}.** {rules.get(rule_id, 'Текст пункта не найден.')}")

    payload = {
        "version": "1.0",
        "documents": [
            {
                "document_id": document_id,
                "document_type": document_type,
                "fields": result["fields"],
                "validation": validation,
                "answers": [{"question_id": f"{document_id}-Q1", **answer}],
            }
        ],
    }
    st.download_button(
        "Скачать результат JSON",
        data=json.dumps(payload, ensure_ascii=False, indent=2),
        file_name=f"{document_id}-result.json",
        mime="application/json",
    )


if process_clicked or completeness_clicked:
    try:
        file_bytes, filename, document_id = _get_input(uploaded_file, sample_id)
        asked = DEFAULT_COMPLETENESS_QUESTION if completeness_clicked else question
        with st.spinner("Читаю документ и сверяю его с правилами…"):
            result = process_document(
                file_bytes,
                filename,
                document_type=None if auto_detect else selected_type,
                question=asked,
                config=config,
                rules=rules,
                auto_detect=auto_detect,
            )
        _render_result(document_id, result, config)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        st.error(f"Не удалось обработать документ: {exc}")
