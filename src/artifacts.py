"""Per-book artifact paths and JSON/JSONL helpers.

All filesystem layout for a book lives here. Phases ask for paths via these
helpers and never construct paths themselves — this keeps the layout in one
place and the rest of the code free of hardcoded strings.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOKS_ROOT = REPO_ROOT / "data" / "books"
CONFIG_DIR = REPO_ROOT / "config"
PROMPTS_DIR = CONFIG_DIR / "prompts"
PLATFORM_DIR = REPO_ROOT / "platform"


@dataclass(frozen=True)
class BookPaths:
    book_id: str
    root: Path

    @property
    def raw(self) -> Path: return self.root / "raw"
    @property
    def analysis(self) -> Path: return self.root / "analysis"
    @property
    def canonical(self) -> Path: return self.root / "canonical"
    @property
    def retrieval(self) -> Path: return self.root / "retrieval"
    @property
    def extraction(self) -> Path: return self.root / "extraction"
    @property
    def graph(self) -> Path: return self.root / "graph"
    @property
    def learning(self) -> Path: return self.root / "learning"
    @property
    def eval_(self) -> Path: return self.root / "eval"
    @property
    def governance(self) -> Path: return self.root / "governance"
    @property
    def logs(self) -> Path: return self.root / "logs"

    @property
    def source_pdf(self) -> Path: return self.raw / "source.pdf"
    @property
    def pages_jsonl(self) -> Path: return self.raw / "pages.jsonl"
    @property
    def diagnosis_json(self) -> Path: return self.analysis / "diagnosis.json"
    @property
    def chunks_jsonl(self) -> Path: return self.canonical / "chunks.jsonl"
    @property
    def index_sqlite(self) -> Path: return self.retrieval / "index.sqlite"
    @property
    def phase_status_json(self) -> Path: return self.governance / "phase_status.json"
    @property
    def gate_report_json(self) -> Path: return self.governance / "gate_report.json"
    @property
    def run_manifest_jsonl(self) -> Path: return self.logs / "run_manifest.jsonl"
    @property
    def errors_jsonl(self) -> Path: return self.logs / "errors.jsonl"

    def ensure_dirs(self) -> None:
        for d in (self.raw, self.analysis, self.canonical, self.retrieval,
                  self.extraction, self.graph, self.learning, self.eval_,
                  self.governance, self.logs):
            d.mkdir(parents=True, exist_ok=True)


def book_paths(book_id: str, books_root: Path | None = None) -> BookPaths:
    root = (books_root or BOOKS_ROOT) / book_id
    return BookPaths(book_id=book_id, root=root)


# ---- JSON / JSONL helpers ------------------------------------------------

def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_jsonl(path: Path) -> Iterator[dict]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with open(tmp, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    os.replace(tmp, path)
    return n


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
