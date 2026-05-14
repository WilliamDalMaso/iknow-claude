"""Tests for P3 chunk."""
from src.artifacts import read_jsonl
from src.phases import p1_ingest, p2_diagnose, p3_chunk


def test_p3_produces_chunks_and_invariants(ctx):
    p1_ingest.run("testbook", ctx)
    p2_diagnose.run("testbook", ctx)
    p3_chunk.run("testbook", ctx)
    chunks = list(read_jsonl(ctx.paths.chunks_jsonl))
    assert len(chunks) >= 3, "expected at least one chunk per page"

    seen_ids = set()
    seen_pages = set()
    max_t = int(ctx.config["chunking"]["max_tokens"])
    for c in chunks:
        # Invariants per chunk:
        assert c["chunk_id"] not in seen_ids, "duplicate chunk_id"
        seen_ids.add(c["chunk_id"])
        assert c["page_no"] >= 1
        assert c["text"].strip(), "empty chunk text"
        assert c["token_count_estimate"] <= max_t
        seen_pages.add(c["page_no"])

    # All three pages produced chunks.
    assert seen_pages == {1, 2, 3}
    gr = p3_chunk.gate("testbook", ctx)
    assert gr.passed is True


def test_p3_never_crosses_page_boundary(ctx):
    p1_ingest.run("testbook", ctx)
    p2_diagnose.run("testbook", ctx)
    p3_chunk.run("testbook", ctx)
    pages = {p["page_no"]: p["text"] for p in read_jsonl(ctx.paths.pages_jsonl)}
    for c in read_jsonl(ctx.paths.chunks_jsonl):
        # Each chunk's text must come from its single declared page.
        # We approximate by requiring its first 60 chars to appear on that page.
        head = c["text"][:60]
        assert head in pages[c["page_no"]], (
            f"chunk {c['chunk_id']} text not found on declared page {c['page_no']}"
        )


def test_p3_gate_fails_on_oversized_chunks(ctx, monkeypatch):
    p1_ingest.run("testbook", ctx)
    p2_diagnose.run("testbook", ctx)
    # Force max_tokens very small so the gate flags real chunks as oversized
    # (we run chunker with default, then re-tighten the cap for the gate).
    p3_chunk.run("testbook", ctx)
    ctx.config["chunking"]["max_tokens"] = 1
    gr = p3_chunk.gate("testbook", ctx)
    assert gr.passed is False
    assert any("exceed max" in i for i in gr.issues)
