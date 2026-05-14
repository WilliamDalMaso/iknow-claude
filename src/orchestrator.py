"""Deterministic state machine. To be implemented in Step 1."""

PHASES = [
    "p1_ingest",
    "p2_diagnose",
    "p3_chunk",
    "p4_embed",
    "p5_benchmark",
    "p6_retrieval_eval",
    "p7_blueprint",
    "p8_extract",
    "p9_graph",
    "p10_learning",
]


def run(book_id: str) -> None:
    raise NotImplementedError("orchestrator.run will be implemented in Step 1")
