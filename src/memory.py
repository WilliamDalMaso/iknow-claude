"""Run manifest, failure slices, and lessons.

Three persistent streams:
- run_manifest.jsonl  (per-book, every meaningful action)
- failure_slices.jsonl (cross-book, every gate failure)
- lessons.jsonl        (cross-book, distilled after passing phases)

Lessons are filtered by phase + book_type and injected into prompts at runtime.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import (
    BookPaths,
    PLATFORM_DIR,
    append_jsonl,
    read_jsonl,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    return "r_" + uuid.uuid4().hex[:10]


def log_action(
    paths: BookPaths,
    *,
    run_id: str,
    phase: str,
    action: str,
    status: str = "ok",
    ms: int | None = None,
    model: str | None = None,
    tokens: dict | None = None,
    cost_usd: float | None = None,
    input_hash: str | None = None,
    output_path: str | None = None,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    row = {
        "ts": _now_iso(),
        "run_id": run_id,
        "phase": phase,
        "action": action,
        "status": status,
        "ms": ms,
        "model": model,
        "tokens": tokens or {},
        "cost_usd": cost_usd,
        "input_hash": input_hash,
        "output_path": output_path,
        "error": error,
    }
    if extra:
        row.update(extra)
    append_jsonl(paths.run_manifest_jsonl, row)


def log_error(paths: BookPaths, *, phase: str, error: str, context: dict | None = None) -> None:
    append_jsonl(paths.errors_jsonl, {
        "ts": _now_iso(),
        "phase": phase,
        "error": error,
        "context": context or {},
    })


def log_failure_slice(
    *,
    book_id: str,
    phase: str,
    input_summary: str,
    expected: str,
    actual: str,
    diagnosis: str = "",
    fix_attempted: str = "",
    result_after_fix: str = "",
) -> None:
    append_jsonl(PLATFORM_DIR / "failure_slices.jsonl", {
        "ts": _now_iso(),
        "book_id": book_id,
        "phase": phase,
        "input_summary": input_summary,
        "expected": expected,
        "actual": actual,
        "diagnosis": diagnosis,
        "fix_attempted": fix_attempted,
        "result_after_fix": result_after_fix,
    })


def append_lesson(*, phase: str, book_type: str, lesson: str, evidence_run: str = "") -> None:
    if not lesson:
        return
    append_jsonl(PLATFORM_DIR / "lessons.jsonl", {
        "ts": _now_iso(),
        "phase": phase,
        "book_type": book_type,
        "lesson": lesson,
        "evidence_run": evidence_run,
    })


def load_lessons(*, phase: str, book_type: str | None, limit: int = 8) -> list[str]:
    """Return up to `limit` recent lesson strings filtered by phase (+ book_type when present)."""
    path = PLATFORM_DIR / "lessons.jsonl"
    if not path.exists():
        return []
    matched: list[str] = []
    for row in read_jsonl(path):
        if row.get("phase") != phase:
            continue
        if book_type and row.get("book_type") not in (book_type, "any", ""):
            continue
        if row.get("lesson"):
            matched.append(row["lesson"])
    return matched[-limit:]


def format_lessons_block(lessons: list[str]) -> str:
    if not lessons:
        return "(none yet)"
    return "\n".join(f"- {l}" for l in lessons)


class Timer:
    """Tiny stopwatch in milliseconds."""

    def __enter__(self) -> "Timer":
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.ms = int((time.perf_counter() - self.t0) * 1000)
