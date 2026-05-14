"""Deterministic state machine.

Reads governance/phase_status.json, runs phases in order, checks gates, and
persists status after each phase. Skips phases already marked "passed".
Exits cleanly when a gate fails or needs human review.

Phase modules expose two functions:
    run(book_id, ctx) -> None
    gate(book_id, ctx) -> GateResult
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .artifacts import (
    BookPaths,
    CONFIG_DIR,
    book_paths,
    read_json,
    write_json,
)
from .gates import GateResult
from .llm import LLMRouter, get_router
from .memory import Timer, log_action, log_error, log_failure_slice, new_run_id


PHASE_ORDER_STEP1 = [
    "p1_ingest",
    "p2_diagnose",
    "p3_chunk",
    "p4_embed",
]

PHASE_ORDER_FULL = [
    "p1_ingest", "p2_diagnose", "p3_chunk", "p4_embed",
    "p5_benchmark", "p6_retrieval_eval", "p7_blueprint",
    "p8_extract", "p9_graph", "p10_learning",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_pipeline_config() -> dict:
    with open(CONFIG_DIR / "pipeline.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Context:
    book_id: str
    paths: BookPaths
    run_id: str
    config: dict
    llm: LLMRouter
    # Convenience: phase_status mutated in-memory then persisted via save_status().
    status: dict = field(default_factory=dict)


# ---- phase_status.json helpers -------------------------------------------

def _empty_status(book_id: str, phases: list[str]) -> dict:
    return {
        "book_id": book_id,
        "current_phase": phases[0],
        "human_review_required": False,
        "runtime_authority_ready": True,
        "phases": {p: {"status": "pending", "attempts": 0, "gate": None} for p in phases},
    }


def load_status(paths: BookPaths, phases: list[str]) -> dict:
    p = paths.phase_status_json
    if not p.exists():
        return _empty_status(paths.book_id, phases)
    data = read_json(p)
    # Ensure all phases are present (forward-compat).
    for ph in phases:
        data["phases"].setdefault(ph, {"status": "pending", "attempts": 0, "gate": None})
    return data


def save_status(paths: BookPaths, status: dict) -> None:
    write_json(paths.phase_status_json, status)


# ---- runner --------------------------------------------------------------

def _resolve_phase_module(name: str):
    return importlib.import_module(f"src.phases.{name}")


def run(book_id: str, *, phases: list[str] | None = None) -> int:
    """Run the pipeline for `book_id`. Returns POSIX exit code."""
    phases = phases or PHASE_ORDER_STEP1
    paths = book_paths(book_id)
    paths.ensure_dirs()

    run_id = new_run_id()
    config = load_pipeline_config()

    # Wire the LLM router's per-call hook to the run manifest.
    def on_call(row: dict) -> None:
        log_action(
            paths,
            run_id=run_id,
            phase=row.get("phase", "llm"),
            action=row.get("kind", "llm_call"),
            model=row.get("model"),
            ms=row.get("ms"),
            tokens=row.get("tokens"),
            cost_usd=row.get("cost_usd"),
            extra={"prompt": row.get("prompt"), "batch": row.get("batch")},
        )

    llm = get_router(on_call=on_call)
    status = load_status(paths, phases)
    ctx = Context(book_id=book_id, paths=paths, run_id=run_id, config=config, llm=llm, status=status)

    print(f"[run] book_id={book_id}  run_id={run_id}  phases={phases}")

    for phase_name in phases:
        ph_state = status["phases"][phase_name]
        if ph_state.get("status") == "passed":
            print(f"[skip] {phase_name} already passed at {ph_state.get('passed_at')}")
            continue

        status["current_phase"] = phase_name
        ph_state["status"] = "running"
        ph_state["attempts"] = ph_state.get("attempts", 0) + 1
        save_status(paths, status)

        print(f"\n=== {phase_name}  (attempt {ph_state['attempts']}) ===")
        mod = _resolve_phase_module(phase_name)

        try:
            with Timer() as t:
                mod.run(book_id, ctx)
            log_action(paths, run_id=run_id, phase=phase_name, action="run", ms=t.ms)
        except Exception as e:
            ph_state["status"] = "failed"
            ph_state["last_error"] = str(e)
            save_status(paths, status)
            log_error(paths, phase=phase_name, error=str(e), context={"action": "run"})
            print(f"[error] {phase_name} crashed: {e}")
            return 1

        try:
            gr: GateResult = mod.gate(book_id, ctx)
        except Exception as e:
            ph_state["status"] = "failed"
            ph_state["last_error"] = f"gate raised: {e}"
            save_status(paths, status)
            log_error(paths, phase=phase_name, error=str(e), context={"action": "gate"})
            print(f"[error] {phase_name} gate crashed: {e}")
            return 1

        ph_state["gate"] = gr.to_dict()
        if gr.passed:
            ph_state["status"] = "passed"
            ph_state["passed_at"] = _now()
            save_status(paths, status)
            score_str = f"  score={gr.score:.3f}" if gr.score is not None else ""
            print(f"[gate] {phase_name} PASSED{score_str}  {gr.message}")
        else:
            ph_state["status"] = "blocked"
            if gr.needs_human_review:
                status["human_review_required"] = True
            save_status(paths, status)
            log_failure_slice(
                book_id=book_id, phase=phase_name,
                input_summary=str(ctx.paths.root),
                expected=gr.message or "gate pass",
                actual=str(gr.metrics),
                diagnosis="; ".join(gr.issues),
            )
            print(f"[gate] {phase_name} BLOCKED: {gr.message}")
            for issue in gr.issues:
                print(f"       - {issue}")
            return 2

    totals = llm.totals()
    print(f"\n[done] cost so far: ${totals['cost_usd']:.4f}  models: "
          + ", ".join(f"{m}({d['calls']} calls)" for m, d in totals["by_model"].items()))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.orchestrator <book_id>", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(sys.argv[1]))
