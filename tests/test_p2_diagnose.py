"""Tests for P2 diagnose. Uses FakeLLM — no network calls."""
from src.artifacts import read_json
from src.phases import p1_ingest, p2_diagnose


def test_p2_writes_diagnosis_and_passes_gate(ctx):
    p1_ingest.run("testbook", ctx)
    p2_diagnose.run("testbook", ctx)
    d = read_json(ctx.paths.diagnosis_json)
    required = ["total_pages", "total_chars", "has_figures", "has_tables",
                "has_formulas", "ocr_needed", "complexity_score",
                "book_type_guess", "language"]
    for k in required:
        assert k in d, f"missing diagnosis field: {k}"
    assert d["total_pages"] == 3
    assert d["total_chars"] > 0
    assert d["ocr_needed"] is False
    # FakeLLM returns 'technical_nonfiction' / 'en'.
    assert d["book_type_guess"] == "technical_nonfiction"
    assert d["language"] == "en"
    gr = p2_diagnose.gate("testbook", ctx)
    assert gr.passed is True


def test_p2_heuristics_pick_up_figures_and_tables(ctx):
    p1_ingest.run("testbook", ctx)
    p2_diagnose.run("testbook", ctx)
    d = read_json(ctx.paths.diagnosis_json)
    # The fixture mentions "Figure 1" and "table 1".
    assert d["has_figures"] is True
    assert d["has_tables"] is True


def test_p2_llm_failure_falls_back(ctx):
    p1_ingest.run("testbook", ctx)

    def boom(*a, **kw):
        raise RuntimeError("simulated LLM outage")
    ctx.llm.chat_json = boom

    p2_diagnose.run("testbook", ctx)
    d = read_json(ctx.paths.diagnosis_json)
    assert d["book_type_guess"] == "other"
    assert d["language"] == "en"
    gr = p2_diagnose.gate("testbook", ctx)
    assert gr.passed is True
