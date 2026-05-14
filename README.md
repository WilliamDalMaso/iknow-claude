# iknow-claude

Autonomous document intelligence platform. Turns a PDF into an evidence-backed
learning system: retrieval index, knowledge graph, flashcards, learning paths,
and a gravity map — with page citations on every claim.

This is a deterministic state-machine engine with LLM nodes called inside phases.
It is **not** an agent framework. See `CONSTITUTION.md` for the laws.

## Prerequisites

- macOS, Apple Silicon (M-series) — tested target
- Python 3.11+
- An OpenAI API key

## Setup

```bash
cd ~/Desktop/iknow-claude
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env, paste your OPENAI_API_KEY
```

## Run on a book

```bash
mkdir -p data/books/test/raw
cp /path/to/your.pdf data/books/test/raw/source.pdf
python scripts/run.py test
python scripts/status.py test
```

The pipeline is resumable: re-running picks up from the last passed phase.

## Phases

| Phase | Name              | Produces                                                |
|-------|-------------------|---------------------------------------------------------|
| P1    | Ingest            | `raw/pages.jsonl`                                       |
| P2    | Diagnose          | `analysis/diagnosis.json`                               |
| P3    | Chunk             | `canonical/chunks.jsonl`                                |
| P4    | Embed             | `retrieval/index.sqlite`                                |
| P5    | Build Benchmark   | `eval/benchmark.jsonl`                                  |
| P6    | Retrieval Eval ⛔ | `eval/scores.json` — **must score ≥80% to proceed**     |
| P7    | Blueprint         | `analysis/taxonomy.json`, `analysis/ontology.json`      |
| P8    | Atomic Extraction | `extraction/aku.jsonl`                                  |
| P9    | Graph Build       | `graph/nodes.jsonl`, `graph/edges.jsonl`                |
| P10   | Learning Surfaces | `learning/cards.jsonl`, `paths.jsonl`, `gravity_map.json` |

## Current status

Bootstrap only — skeleton, constitution, prompt templates, config in place.
P1–P10 implementations come next.
