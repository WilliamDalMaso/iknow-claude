"""CLI entrypoint to run the pipeline on a book.

Usage: python scripts/run.py <book_id>

Full implementation lands in Step 1 once the orchestrator is wired.
"""
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/run.py <book_id>", file=sys.stderr)
        return 2
    book_id = sys.argv[1]
    print(f"[run] would run pipeline for book_id={book_id}")
    print("[run] orchestrator not yet implemented — see Step 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
