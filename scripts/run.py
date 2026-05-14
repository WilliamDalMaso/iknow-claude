"""CLI entrypoint to run the pipeline on a book.

Usage: python scripts/run.py <book_id> [phase ...]

When no phases are given, runs the Step-1 set (P1–P4).
"""
import sys
from pathlib import Path

# Make the package importable when invoked as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator import PHASE_ORDER_FULL, PHASE_ORDER_STEP1, run  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/run.py <book_id> [phase ...]", file=sys.stderr)
        print("       phases default to P1–P4 (Step 1).", file=sys.stderr)
        return 2
    book_id = sys.argv[1]
    phases = sys.argv[2:] or None
    return run(book_id, phases=phases)


if __name__ == "__main__":
    raise SystemExit(main())
