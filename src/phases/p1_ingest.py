"""P1 — Ingest.

Input:  raw/source.pdf
Output: raw/pages.jsonl with one row per page:
        {page_no, text, char_count, has_images, has_tables_hint}

Gate:   ≥90% of pages must have non-empty text. Below that we flag
        ocr_needed and stop for human review (out of scope for v1).
"""
from __future__ import annotations

import re

import fitz  # PyMuPDF

from ..artifacts import write_jsonl, read_jsonl
from ..gates import GateResult
from ..memory import log_action

# Heuristic: tables often look like rows with 2+ aligned whitespace gaps.
_TABLE_HINT = re.compile(r"(?m)^(?:\S+\s{2,}){2,}\S+\s*$")


def _has_table_hint(text: str) -> bool:
    matches = _TABLE_HINT.findall(text or "")
    return len(matches) >= 2


def run(book_id: str, ctx) -> None:
    paths = ctx.paths
    pdf_path = paths.source_pdf
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"missing PDF at {pdf_path}. Drop your book at this exact path and re-run."
        )

    print(f"[P1/ingest] opening {pdf_path.name}")
    rows = []
    with fitz.open(pdf_path) as doc:
        total = doc.page_count
        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            text = text.replace("\x00", "").strip()
            images = page.get_images(full=False)
            row = {
                "page_no": i + 1,
                "text": text,
                "char_count": len(text),
                "has_images": bool(images),
                "has_tables_hint": _has_table_hint(text),
            }
            rows.append(row)
            if (i + 1) % 25 == 0 or i + 1 == total:
                print(f"[P1/ingest] page {i + 1}/{total}")

    n = write_jsonl(paths.pages_jsonl, rows)
    log_action(paths, run_id=ctx.run_id, phase="p1_ingest", action="write_pages",
               output_path=str(paths.pages_jsonl), extra={"pages": n})
    print(f"[P1/ingest] wrote {n} pages")


def gate(book_id: str, ctx) -> GateResult:
    paths = ctx.paths
    pages = list(read_jsonl(paths.pages_jsonl))
    total = len(pages)
    if total == 0:
        return GateResult(phase="p1_ingest", passed=False,
                          message="no pages extracted", issues=["empty PDF or unreadable"])

    non_empty = sum(1 for p in pages if p["char_count"] > 0)
    coverage = non_empty / total
    ocr_needed = coverage < 0.90
    metrics = {
        "total_pages": total,
        "non_empty_pages": non_empty,
        "coverage": round(coverage, 4),
        "ocr_needed": ocr_needed,
    }
    if ocr_needed:
        return GateResult(
            phase="p1_ingest", passed=False, score=coverage, metrics=metrics,
            needs_human_review=True,
            issues=[f"only {coverage:.0%} of pages have text — PDF likely scanned"],
            message="OCR needed (out of scope for v1)",
        )
    return GateResult(
        phase="p1_ingest", passed=True, score=coverage, metrics=metrics,
        message=f"{non_empty}/{total} pages have text",
    )
