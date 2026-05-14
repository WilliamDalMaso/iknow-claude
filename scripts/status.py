"""CLI to print human-readable status for a book.

Usage: python scripts/status.py <book_id>

Full implementation lands in Step 1.
"""
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/status.py <book_id>", file=sys.stderr)
        return 2
    print(f"[status] book_id={sys.argv[1]} — status reporter not yet implemented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
