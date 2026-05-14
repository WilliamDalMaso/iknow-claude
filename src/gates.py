"""GateResult — the verdict a phase emits after running."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class GateResult:
    phase: str
    passed: bool
    score: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    needs_human_review: bool = False
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
