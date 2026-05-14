"""Tests for P4 embed. Uses FakeLLM — embeddings are deterministic stubs."""
import sqlite3

import numpy as np

from src.artifacts import read_jsonl
from src.phases import p1_ingest, p2_diagnose, p3_chunk, p4_embed


def _run_through_p4(ctx):
    p1_ingest.run("testbook", ctx)
    p2_diagnose.run("testbook", ctx)
    p3_chunk.run("testbook", ctx)
    p4_embed.run("testbook", ctx)


def test_p4_builds_index_with_one_row_per_chunk(ctx):
    _run_through_p4(ctx)
    chunks = list(read_jsonl(ctx.paths.chunks_jsonl))
    conn = sqlite3.connect(ctx.paths.index_sqlite)
    try:
        n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert n == len(chunks)
        nulls = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL OR length(embedding)=0"
        ).fetchone()[0]
        assert nulls == 0

        # All embeddings are the same dim and float32.
        row = conn.execute("SELECT embedding, dim FROM chunks LIMIT 1").fetchone()
        v = np.frombuffer(row[0], dtype=np.float32)
        assert v.shape[0] == row[1] == 1536

        # FTS finds something for a token from the corpus.
        hits = conn.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("frobnication",),
        ).fetchone()[0]
        assert hits >= 1

        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        assert meta["total_chunks"] == str(len(chunks))
    finally:
        conn.close()

    gr = p4_embed.gate("testbook", ctx)
    assert gr.passed is True
    assert gr.metrics["null_embeddings"] == 0
    assert gr.metrics["indexed_chunks"] == len(chunks)


def test_p4_run_is_idempotent(ctx):
    _run_through_p4(ctx)
    chunks = list(read_jsonl(ctx.paths.chunks_jsonl))
    # Second run should not duplicate rows.
    p4_embed.run("testbook", ctx)
    conn = sqlite3.connect(ctx.paths.index_sqlite)
    try:
        n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert n == len(chunks)
    finally:
        conn.close()


def test_p4_gate_fails_when_index_missing(ctx):
    # Pretend the index never got built.
    if ctx.paths.index_sqlite.exists():
        ctx.paths.index_sqlite.unlink()
    gr = p4_embed.gate("testbook", ctx)
    assert gr.passed is False
    assert "no index file" in gr.issues
