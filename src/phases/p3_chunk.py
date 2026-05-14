"""P3 — Chunk.

Paragraph-aware splitting. Targets 400–600 tokens per chunk; never splits mid
paragraph; never crosses page boundaries; preserves page provenance always.

Token count is approximated as chars/4 (deterministic, good enough for a
budget — the embedder counts real tokens itself).
"""
from __future__ import annotations

import re

from ..artifacts import read_json, read_jsonl, write_jsonl
from ..gates import GateResult
from ..memory import log_action

_PARA_SPLIT = re.compile(r"\n\s*\n+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _estimate_tokens(text: str) -> int:
    # Conservative ~4 chars/token. Good enough for budgeting.
    return max(1, (len(text) + 3) // 4)


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in _PARA_SPLIT.split(text or "")]
    return [p for p in parts if p]


def _split_long_paragraph(p: str, max_tokens: int) -> list[str]:
    """If one paragraph is itself larger than max_tokens, split on sentences."""
    if _estimate_tokens(p) <= max_tokens:
        return [p]
    sentences = _SENT_SPLIT.split(p)
    out: list[str] = []
    buf: list[str] = []
    buf_tok = 0
    for s in sentences:
        st = _estimate_tokens(s)
        if buf and buf_tok + st > max_tokens:
            out.append(" ".join(buf).strip())
            buf, buf_tok = [s], st
        else:
            buf.append(s)
            buf_tok += st
    if buf:
        out.append(" ".join(buf).strip())
    return out


def _chunk_page(page_text: str, page_no: int, *, target: int, min_t: int, max_t: int) -> list[dict]:
    """Produce chunks for one page. Never crosses page boundary."""
    paragraphs = _split_paragraphs(page_text)
    # Pre-split any monster paragraphs.
    expanded: list[str] = []
    for p in paragraphs:
        expanded.extend(_split_long_paragraph(p, max_tokens=max_t))

    chunks: list[dict] = []
    buf: list[str] = []
    buf_tok = 0
    para_idx = 0
    first_para_idx = 0

    def flush():
        nonlocal buf, buf_tok, first_para_idx, para_idx
        if not buf:
            return
        text = "\n\n".join(buf).strip()
        if not text:
            buf, buf_tok = [], 0
            return
        chunks.append({
            "page_no": page_no,
            "paragraph_no": first_para_idx,
            "text": text,
            "char_count": len(text),
            "token_count_estimate": _estimate_tokens(text),
        })
        buf, buf_tok = [], 0
        first_para_idx = para_idx

    for para in expanded:
        ptok = _estimate_tokens(para)
        # If adding this paragraph would push us beyond max, flush first
        # (unless buffer is empty — then it goes through on its own).
        if buf and buf_tok + ptok > max_t:
            flush()
        buf.append(para)
        buf_tok += ptok
        para_idx += 1
        # If we're already past the target, close the chunk.
        if buf_tok >= target:
            flush()

    # Final flush. If the last chunk is tiny and would be below min_t, merge
    # it into the previous chunk to avoid stub chunks.
    if buf:
        if chunks and buf_tok < min_t:
            prev = chunks[-1]
            merged = prev["text"] + "\n\n" + "\n\n".join(buf).strip()
            prev["text"] = merged
            prev["char_count"] = len(merged)
            prev["token_count_estimate"] = _estimate_tokens(merged)
        else:
            flush()

    return chunks


def run(book_id: str, ctx) -> None:
    paths = ctx.paths
    diag = read_json(paths.diagnosis_json)
    cfg = ctx.config.get("chunking", {})
    target = int(cfg.get("target_tokens", 500))
    min_t = int(cfg.get("min_tokens", 200))
    max_t = int(cfg.get("max_tokens", 800))

    print(f"[P3/chunk] target={target} min={min_t} max={max_t} tokens")
    all_chunks: list[dict] = []
    cid = 0
    pages = list(read_jsonl(paths.pages_jsonl))
    for page in pages:
        if not page["text"]:
            continue
        page_chunks = _chunk_page(page["text"], page["page_no"],
                                  target=target, min_t=min_t, max_t=max_t)
        for c in page_chunks:
            cid += 1
            c["chunk_id"] = f"c{cid:06d}"
            all_chunks.append(c)

    n = write_jsonl(paths.chunks_jsonl, all_chunks)
    log_action(paths, run_id=ctx.run_id, phase="p3_chunk", action="write_chunks",
               output_path=str(paths.chunks_jsonl),
               extra={"chunks": n, "pages": len(pages),
                      "book_type": diag.get("book_type_guess")})
    print(f"[P3/chunk] wrote {n} chunks from {len(pages)} pages")


def gate(book_id: str, ctx) -> GateResult:
    paths = ctx.paths
    cfg = ctx.config.get("chunking", {})
    max_t = int(cfg.get("max_tokens", 800))

    chunks = list(read_jsonl(paths.chunks_jsonl))
    if not chunks:
        return GateResult(phase="p3_chunk", passed=False,
                          message="no chunks produced",
                          issues=["empty chunks.jsonl"])

    missing_page = [c["chunk_id"] for c in chunks if not c.get("page_no")]
    too_big = [c["chunk_id"] for c in chunks if c["token_count_estimate"] > max_t]
    empty = [c["chunk_id"] for c in chunks if not c["text"].strip()]

    avg_tok = sum(c["token_count_estimate"] for c in chunks) / len(chunks)
    metrics = {
        "total_chunks": len(chunks),
        "avg_tokens": round(avg_tok, 1),
        "max_tokens_seen": max(c["token_count_estimate"] for c in chunks),
        "min_tokens_seen": min(c["token_count_estimate"] for c in chunks),
    }
    issues = []
    if missing_page: issues.append(f"{len(missing_page)} chunks missing page_no")
    if too_big:      issues.append(f"{len(too_big)} chunks exceed max {max_t} tokens (first: {too_big[:3]})")
    if empty:        issues.append(f"{len(empty)} empty chunks")

    if issues:
        return GateResult(phase="p3_chunk", passed=False, metrics=metrics,
                          issues=issues, message="chunk invariants violated")
    return GateResult(phase="p3_chunk", passed=True, metrics=metrics,
                      message=f"{len(chunks)} chunks, avg ~{int(avg_tok)} tokens")
