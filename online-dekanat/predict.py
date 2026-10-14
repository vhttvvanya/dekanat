#!/usr/bin/env python3
"""Пакетная обработка набора документов в results.json."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.pipeline import (
    analyze_document,
    answer_analysis,
    build_result_record,
    load_config,
    load_rules,
)


def _resolve_file(data_dir: Path, item: dict) -> Path:
    for key in ("pdf", "image"):
        relative = item.get(key)
        if not relative:
            continue
        path = data_dir / relative
        if path.is_file():
            return path
        nested = data_dir / Path(relative).name
        if nested.is_file():
            return nested
    raise FileNotFoundError(f"Не найден файл документа {item['document_id']}")


def run(
    *,
    data_dir: Path,
    manifest_path: Path,
    questions_path: Path,
    output_path: Path,
    auto_detect: bool,
) -> dict:
    config = load_config()
    rules = load_rules()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    by_document: dict[str, list[dict]] = defaultdict(list)
    for item in questions:
        by_document[item["document_id"]].append(item)

    documents = []
    for item in manifest:
        document_id = item["document_id"]
        path = _resolve_file(data_dir, item)
        file_bytes = path.read_bytes()
        selected_type = None if auto_detect else item["document_type"]
        analysis = analyze_document(
            file_bytes,
            path.name,
            document_type=selected_type,
            config=config,
            rules=rules,
            auto_detect=auto_detect,
        )
        fields = analysis["fields"]
        validation = analysis["validation"]
        resolved_type = analysis["document_type"]
        answers = []
        for question in by_document[document_id]:
            result = answer_analysis(
                analysis, question["question"], config, rules
            )
            answers.append({"question_id": question["question_id"], **result["answer"]})
        documents.append(
            build_result_record(document_id, resolved_type, fields, validation, answers)
        )

    payload = {"version": "1.0", "documents": documents}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_DIR / "data")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--questions", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=PROJECT_DIR / "results" / "results.json")
    parser.add_argument("--auto-detect", action="store_true")
    args = parser.parse_args()
    manifest = args.manifest or args.data_dir / "documents.json"
    questions = args.questions or args.data_dir / "questions.json"
    run(
        data_dir=args.data_dir,
        manifest_path=manifest,
        questions_path=questions,
        output_path=args.output,
        auto_detect=args.auto_detect,
    )
    print(f"Записано: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
