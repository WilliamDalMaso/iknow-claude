"""P4 — Embed.

Builds retrieval/index.sqlite containing:
  - chunks(chunk_id PK, page_no, text, embedding BLOB)  -- float32 little-endian
  - chunks_fts (FTS5 virtual table over text + chunk_id)

Embedding model: text-embedding-3-small via the LLMRouter.
For tests we monkey-patch ctx.llm.embed; production goes through OpenAI.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from ..artifacts import read_jsonl
from ..gates import GateResult
from ..memory import log_action


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id   TEXT PRIMARY KEY,
            page_no    INTEGER NOT NULL,
            text       TEXT NOT NULL,
            embedding  BLOB NOT NULL,
            dim        INTEGER NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(chunk_id UNINDEXED, text);
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)


def _vec_to_blob(v) -> bytes:
    arr = np.asarray(v, dtype=np.float32)
    return arr.tobytes(order="C")


def _blob_to_vec(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


def run(book_id: str, ctx) -> None:
    paths = ctx.paths
    chunks = list(read_jsonl(paths.chunks_jsonl))
    if not chunks:
        raise RuntimeError("no chunks to embed — did P3 produce chunks.jsonl?")

    # Reset the index so re-runs are deterministic.
    if paths.index_sqlite.exists():
        paths.index_sqlite.unlink()

    conn = _connect(paths.index_sqlite)
    try:
        _init_schema(conn)

        # Batch through the router (router handles internal batching too).
        batch = max(1, int(ctx.llm.config["models"]["embed"].get("batch_size", 100)))
        total = len(chunks)
        print(f"[P4/embed] embedding {total} chunks (batch={batch})")

        done = 0
        for start in range(0, total, batch):
            slice_ = chunks[start:start + batch]
            texts = [c["text"] for c in slice_]
            vectors = ctx.llm.embed(texts)
            with conn:
                conn.executemany(
                    "INSERT INTO chunks (chunk_id, page_no, text, embedding, dim) VALUES (?, ?, ?, ?, ?)",
                    [(c["chunk_id"], c["page_no"], c["text"], _vec_to_blob(v), len(v))
                     for c, v in zip(slice_, vectors)],
                )
                conn.executemany(
                    "INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)",
                    [(c["chunk_id"], c["text"]) for c in slice_],
                )
            done += len(slice_)
            print(f"[P4/embed] {done}/{total}  (cost so far ${ctx.llm.total_cost():.4f})")

        with conn:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                         ("model", ctx.llm.config["models"]["embed"]["name"]))
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                         ("dim", str(ctx.llm.config["models"]["embed"].get("dim", 0))))
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                         ("total_chunks", str(total)))

    finally:
        conn.close()

    log_action(paths, run_id=ctx.run_id, phase="p4_embed", action="build_index",
               output_path=str(paths.index_sqlite),
               extra={"chunks": len(chunks)})
    print(f"[P4/embed] wrote {paths.index_sqlite.name}")


def gate(book_id: str, ctx) -> GateResult:
    paths = ctx.paths
    if not paths.index_sqlite.exists():
        return GateResult(phase="p4_embed", passed=False,
                          message="index.sqlite missing", issues=["no index file"])

    conn = _connect(paths.index_sqlite)
    try:
        total_chunks = sum(1 for _ in read_jsonl(paths.chunks_jsonl))
        n_rows = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_nulls = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL OR length(embedding) = 0"
        ).fetchone()[0]
        # Sanity query: pick first chunk's embedding and verify dim.
        row = conn.execute("SELECT embedding, dim FROM chunks LIMIT 1").fetchone()
        if row is None:
            return GateResult(phase="p4_embed", passed=False,
                              message="index has no rows", issues=["empty chunks table"])
        sample = _blob_to_vec(row[0])
        ok_dim = (sample.shape[0] == row[1] and sample.shape[0] > 0)

        # FTS sanity: try a free-text search using a token from the first chunk.
        first_text = conn.execute("SELECT text FROM chunks LIMIT 1").fetchone()[0]
        token = next((w for w in first_text.split() if w.isalpha() and len(w) > 3),
                     "the")
        fts_hit = conn.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            (token,),
        ).fetchone()[0]
    finally:
        conn.close()

    metrics = {
        "expected_chunks": total_chunks,
        "indexed_chunks": n_rows,
        "null_embeddings": n_nulls,
        "sample_dim": int(sample.shape[0]),
        "fts_sample_token": token,
        "fts_sample_hits": int(fts_hit),
    }
    issues = []
    if n_rows != total_chunks:
        issues.append(f"row count mismatch: {n_rows} indexed vs {total_chunks} chunks")
    if n_nulls > 0:
        issues.append(f"{n_nulls} rows have null/empty embeddings")
    if not ok_dim:
        issues.append("embedding dim mismatch in sample row")
    if fts_hit == 0:
        issues.append(f"FTS returned 0 hits for sanity token '{token}'")

    if issues:
        return GateResult(phase="p4_embed", passed=False, metrics=metrics,
                          issues=issues, message="index sanity failed")
    return GateResult(phase="p4_embed", passed=True, metrics=metrics,
                      message=f"{n_rows} chunks embedded (dim={sample.shape[0]})")
