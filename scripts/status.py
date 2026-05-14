"""Print a human-readable status for a book.

Usage: python scripts/status.py <book_id>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.artifacts import book_paths, read_json, read_jsonl  # noqa: E402

ICON = {"passed": "✓", "running": "…", "blocked": "✗", "failed": "✗",
        "pending": "·"}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/status.py <book_id>", file=sys.stderr)
        return 2
    book_id = sys.argv[1]
    paths = book_paths(book_id)

    if not paths.phase_status_json.exists():
        print(f"[status] no phase_status.json for {book_id} — nothing has run yet.")
        return 0

    status = read_json(paths.phase_status_json)
    print(f"Book: {status['book_id']}")
    print(f"Current phase: {status.get('current_phase')}")
    print(f"Human review required: {status.get('human_review_required')}")
    print()
    print(f"{'phase':<22} {'status':<10} {'attempts':>8}  score  message")
    print("-" * 90)
    for phase, ph in status["phases"].items():
        st = ph.get("status", "pending")
        icon = ICON.get(st, "?")
        gr = ph.get("gate") or {}
        score = gr.get("score")
        score_s = f"{score:.3f}" if isinstance(score, (int, float)) else "  -  "
        msg = (gr.get("message") or ph.get("last_error") or "")[:40]
        print(f"{icon} {phase:<20} {st:<10} {ph.get('attempts', 0):>8}  {score_s}  {msg}")

    # Cost from run_manifest.
    if paths.run_manifest_jsonl.exists():
        cost = 0.0
        actions = 0
        for row in read_jsonl(paths.run_manifest_jsonl):
            c = row.get("cost_usd")
            if isinstance(c, (int, float)):
                cost += c
            actions += 1
        print()
        print(f"Manifest entries: {actions}  total cost: ${cost:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
