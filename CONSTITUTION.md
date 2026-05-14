# iknow-claude Constitution

This document is load-bearing. Every phase, every commit, every refactor must respect it.

## The Three Architectural Laws

### Law 1 — Engine before autonomy
Build the working pipeline first (PDF → retrieval → KG → learning). Autonomy primitives
(run manifest, failure slices, lessons, phase status) are baked in from day 1, but they
wrap working code, not aspirational structure.

### Law 2 — Deterministic state machine with LLM nodes
The orchestrator is plain Python. LLMs are called inside phases for content tasks
(classification, extraction, judgment). LLMs do **not** drive control flow. Control flow
is deterministic, resumable, and inspectable.

### Law 3 — Artifacts are the message bus
Phases communicate by reading and writing files under `data/books/<book_id>/`. No
in-memory passing between phases. No global state. If a phase cannot be resumed from
disk artifacts, it is wrong.

## Anti-Goals — Do NOT Build These

- ❌ No "agents" as autonomous LLM loops driving control flow
- ❌ No 5-overseer class hierarchy — just module groupings under `src/phases/`
- ❌ No agent frameworks (LangGraph, CrewAI, AutoGen, LlamaIndex agents, LangChain agents)
- ❌ No vector database service — local SQLite + numpy is fine for the first book
- ❌ No web UI
- ❌ No premature multi-book abstraction — make one book work first, then generalize via config
- ❌ No hardcoded book paths anywhere in `src/`

## Win Conditions

Given a PDF and 20 ground-truth Q&A, the system wins when:
1. It answers ≥80% correctly with page citations
2. Knowledge graph nodes/edges all have provenance back to a chunk and page
3. Learning surfaces (cards, paths, gravity map) are useful to a human
4. It runs on a second book without code changes — config only
5. It logs failures, accumulates lessons, applies them on future runs

## Discipline Rules — Non-Negotiable

1. Commit at every phase boundary. Format: `P{N} {phase_name}: {one-line summary}`
2. Every phase ships with a test.
3. Never silent-fail. All exceptions logged to `logs/errors.jsonl` with full context.
4. Print loud status for the user.
5. No hardcoded book paths in `src/`.
6. Cite everything — every AKU, answer, edge has page_no + chunk_id.
7. Always resumable from the last passed gate.
