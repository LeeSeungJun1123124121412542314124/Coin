"""Base analyzer ABC and shared data models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisResult:
    score: float
    signal: str
    details: dict[str, Any] = field(default_factory=dict)
    source: str = ""


class BaseAnalyzer(ABC):
    @abstractmethod
    def analyze(self, data: Any) -> AnalysisResult:
        """Run analysis and return a scored result."""

    def _clamp(self, value: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, value))

    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        if max_val == min_val:
            return 50.0
        raw = (value - min_val) / (max_val - min_val) * 100.0
        return self._clamp(raw)
