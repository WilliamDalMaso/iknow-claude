"""P2 — Diagnose.

Input:  raw/pages.jsonl
Output: analysis/diagnosis.json

Everything except book_type_guess + language is deterministic heuristic.
Book type / language is one cheap LLM call over the first 5 pages.
"""
from __future__ import annotations

import re

from ..artifacts import read_jsonl, write_json
from ..gates import GateResult
from ..memory import load_lessons, log_action

# Deterministic detectors.
_FIG_RE = re.compile(r"\b(figure|fig\.)\s*\d", re.IGNORECASE)
_TBL_RE = re.compile(r"\btable\s*\d", re.IGNORECASE)
# Formula heuristic: math operators outside trivial usage, or LaTeX-ish leftovers.
_FORMULA_RE = re.compile(r"(\\frac|\\sum|\\int|≤|≥|≠|≈|∑|∫|√|\b[a-zA-Z]\s*=\s*[-+\d])")


def _heuristics(pages: list[dict]) -> dict:
    total_pages = len(pages)
    total_chars = sum(p["char_count"] for p in pages)
    has_figures = any(_FIG_RE.search(p["text"] or "") for p in pages)
    has_tables = any(p.get("has_tables_hint") for p in pages) or any(_TBL_RE.search(p["text"] or "") for p in pages)
    has_formulas = any(_FORMULA_RE.search(p["text"] or "") for p in pages)
    non_empty = sum(1 for p in pages if p["char_count"] > 0)
    coverage = non_empty / total_pages if total_pages else 0.0
    ocr_needed = coverage < 0.90

    avg_chars = total_chars / max(non_empty, 1)
    # Simple complexity proxy: density + structural features.
    complexity = 0.0
    if avg_chars > 2500: complexity += 0.30
    if has_figures:     complexity += 0.20
    if has_tables:      complexity += 0.20
    if has_formulas:    complexity += 0.30
    complexity = min(complexity, 1.0)

    return {
        "total_pages": total_pages,
        "total_chars": total_chars,
        "has_figures": has_figures,
        "has_tables": has_tables,
        "has_formulas": has_formulas,
        "ocr_needed": ocr_needed,
        "complexity_score": round(complexity, 3),
    }


def _opening_text(pages: list[dict], n: int = 5, max_chars: int = 12_000) -> str:
    """First `n` pages plus a peek at the rest to catch a TOC if it's later."""
    parts = []
    for p in pages[:n]:
        parts.append(f"--- page {p['page_no']} ---\n{p['text']}")
    out = "\n\n".join(parts)
    # Try to find a TOC-ish region by scanning the first ~30 pages for the word
    # "contents" — if found and beyond page n, append it.
    for p in pages[n:30]:
        t = p["text"] or ""
        if re.search(r"\b(table of contents|contents)\b", t, re.IGNORECASE):
            out += f"\n\n--- page {p['page_no']} (TOC-ish) ---\n{t}"
            break
    return out[:max_chars]


def run(book_id: str, ctx) -> None:
    paths = ctx.paths
    pages = list(read_jsonl(paths.pages_jsonl))
    print(f"[P2/diagnose] running heuristics on {len(pages)} pages")
    base = _heuristics(pages)

    # One cheap LLM call for book_type + language.
    first_pages_text = _opening_text(pages)
    lessons = load_lessons(phase="p2_diagnose", book_type=None)
    print(f"[P2/diagnose] classifying book type via cheap model")
    try:
        data, _u = ctx.llm.chat_json(
            "diagnose_book_type",
            variables={
                "first_pages_text": first_pages_text,
                "total_pages": base["total_pages"],
                "has_figures": base["has_figures"],
                "has_tables": base["has_tables"],
            },
            model_role="cheap",
            lessons=lessons,
            max_output_tokens=300,
        )
        book_type = data.get("book_type_guess") or "other"
        language = data.get("language") or "en"
        rationale = data.get("rationale") or ""
    except Exception as e:
        print(f"[P2/diagnose] LLM classification failed ({e}); falling back to 'other'/'en'")
        book_type, language, rationale = "other", "en", f"fallback: {e}"

    out = {**base, "book_type_guess": book_type, "language": language,
           "book_type_rationale": rationale}
    write_json(paths.diagnosis_json, out)
    log_action(paths, run_id=ctx.run_id, phase="p2_diagnose", action="write_diagnosis",
               output_path=str(paths.diagnosis_json), extra={"book_type": book_type})
    print(f"[P2/diagnose] book_type={book_type}  language={language}  "
          f"complexity={out['complexity_score']}")


def gate(book_id: str, ctx) -> GateResult:
    from ..artifacts import read_json
    d = read_json(ctx.paths.diagnosis_json)
    required = ["total_pages", "total_chars", "has_figures", "has_tables",
                "has_formulas", "ocr_needed", "complexity_score",
                "book_type_guess", "language"]
    missing = [k for k in required if k not in d]
    if missing:
        return GateResult(phase="p2_diagnose", passed=False,
                          metrics=d, issues=[f"missing fields: {missing}"],
                          message="diagnosis incomplete")
    if d["ocr_needed"]:
        return GateResult(phase="p2_diagnose", passed=False, metrics=d,
                          needs_human_review=True,
                          issues=["ocr_needed=true"],
                          message="OCR needed (out of scope for v1)")
    return GateResult(phase="p2_diagnose", passed=True, metrics=d,
                      message=f"book_type={d['book_type_guess']} language={d['language']}")
