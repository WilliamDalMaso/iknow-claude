"""Tests for P1 ingest."""
import pytest

from src.artifacts import read_jsonl, write_jsonl
from src.phases import p1_ingest


def test_p1_writes_pages_and_passes_gate(ctx):
    p1_ingest.run("testbook", ctx)
    pages = list(read_jsonl(ctx.paths.pages_jsonl))
    assert len(pages) == 3
    for i, p in enumerate(pages, start=1):
        assert p["page_no"] == i
        assert p["char_count"] > 0
        assert isinstance(p["has_images"], bool)
        assert isinstance(p["has_tables_hint"], bool)
    gr = p1_ingest.gate("testbook", ctx)
    assert gr.passed is True
    assert gr.metrics["coverage"] == 1.0
    assert gr.metrics["ocr_needed"] is False


def test_p1_missing_pdf_raises(ctx):
    ctx.paths.source_pdf.unlink()
    with pytest.raises(FileNotFoundError):
        p1_ingest.run("testbook", ctx)


def test_p1_gate_fails_on_empty_pages(ctx):
    write_jsonl(ctx.paths.pages_jsonl, [
        {"page_no": 1, "text": "", "char_count": 0,
         "has_images": True, "has_tables_hint": False},
        {"page_no": 2, "text": "", "char_count": 0,
         "has_images": True, "has_tables_hint": False},
    ])
    gr = p1_ingest.gate("testbook", ctx)
    assert gr.passed is False
    assert gr.needs_human_review is True
    assert gr.metrics["ocr_needed"] is True
