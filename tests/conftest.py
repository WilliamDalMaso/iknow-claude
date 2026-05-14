"""Shared pytest fixtures for P1–P4 tests.

Builds a tiny synthetic PDF, wires a fake LLM router that does not hit the
network, and yields a Context object pointing at a temporary book root.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytest

# Make the package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.artifacts import BookPaths, book_paths  # noqa: E402
from src.llm import load_models_config  # noqa: E402
from src.orchestrator import load_pipeline_config  # noqa: E402


@dataclass
class FakeUsage:
    in_tokens: int = 0
    out_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0


class FakeLLM:
    """Stub LLMRouter. Returns deterministic JSON and deterministic embeddings."""

    def __init__(self):
        self.config = load_models_config()
        self.usage: dict = {}
        self.on_call = None
        self.chat_responses = {
            # default response — tests can override
            "diagnose_book_type": {
                "book_type_guess": "technical_nonfiction",
                "language": "en",
                "rationale": "synthetic test fixture",
            },
        }

    def chat_json(self, prompt_name, variables, *, model_role, lessons=None,
                  system=None, max_output_tokens=None):
        data = self.chat_responses.get(prompt_name, {})
        return data, FakeUsage()

    def embed(self, texts, *, model_role="embed"):
        # Deterministic 1536-dim vectors: hash the string into the first slot,
        # rest zeros. Stable across runs.
        dim = int(self.config["models"]["embed"].get("dim", 1536))
        out = []
        for t in texts:
            v = np.zeros(dim, dtype=np.float32)
            v[0] = float((abs(hash(t)) % 10_000) / 10_000.0)
            v[1] = float(len(t) % 1000) / 1000.0
            out.append(v.tolist())
        return out

    def total_cost(self) -> float: return 0.0
    def totals(self) -> dict: return {"cost_usd": 0.0, "by_model": {}}


@dataclass
class FakeCtx:
    book_id: str
    paths: BookPaths
    run_id: str
    config: dict
    llm: FakeLLM
    status: dict = field(default_factory=dict)


def _build_pdf(path: Path) -> None:
    """Create a small 3-page PDF with text content sufficient for chunking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page_texts = [
        "Introduction to Frobnication\n\n"
        "Frobnication is the art of adjusting widgets in a non-destructive manner. "
        "It originated in the late 20th century and remains a cornerstone of "
        "widget engineering today.\n\n"
        "Figure 1 shows the canonical frobnication apparatus.\n\n"
        "The frobnicator consists of three primary components: an input stage, "
        "a coupling stage, and an output stage. Each stage has well-defined "
        "responsibilities that are described in detail in the chapters that "
        "follow. " * 3,

        "Chapter 2: Methods\n\n"
        "The method of frobnication proceeds in four steps:\n"
        "1. Align the widget.\n"
        "2. Apply the coupling agent.\n"
        "3. Engage the frobnicator.\n"
        "4. Verify the result against table 1.\n\n"
        "Each step has a recommended duration. Practitioners should consult "
        "the original literature for the exact tolerances applicable to their "
        "specific widget class. " * 3,

        "Chapter 3: Results\n\n"
        "Empirical results show that proper frobnication reduces widget "
        "failure rates by approximately 42%. The mechanism behind this "
        "improvement is well understood and described in chapter 4. "
        "Notation: x = f(w) where w is the widget and f is the frobnication "
        "operator. " * 4,
    ]
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    doc.save(path)
    doc.close()


@pytest.fixture
def book_root(tmp_path: Path) -> Path:
    return tmp_path / "books"


@pytest.fixture
def ctx(book_root: Path) -> FakeCtx:
    paths = book_paths("testbook", books_root=book_root)
    paths.ensure_dirs()
    _build_pdf(paths.source_pdf)
    return FakeCtx(
        book_id="testbook",
        paths=paths,
        run_id="r_test",
        config=load_pipeline_config(),
        llm=FakeLLM(),
    )
