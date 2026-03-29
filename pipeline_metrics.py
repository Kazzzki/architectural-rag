"""
pipeline_metrics.py - RAGパイプラインの各ステージの処理時間を計測する

使い方:
    timer = MetricsTimer()
    # ... query expansion ...
    timer.mark("query_expansion")
    # ... search ...
    timer.mark("search")
    metrics = timer.finalize()
    # metrics.to_dict() -> {"query_expansion_ms": 120.3, "search_ms": 450.1, "total_ms": 570.4}
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    query_expansion_ms: Optional[float] = None
    search_ms: Optional[float] = None
    merge_ms: Optional[float] = None
    rerank_ms: Optional[float] = None
    parent_resolve_ms: Optional[float] = None
    context_build_ms: Optional[float] = None
    generation_ms: Optional[float] = None
    total_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class MetricsTimer:
    def __init__(self):
        self.metrics = PipelineMetrics()
        self._start = time.monotonic()
        self._total_start = self._start

    def mark(self, stage: str):
        now = time.monotonic()
        setattr(self.metrics, f"{stage}_ms", round((now - self._start) * 1000, 1))
        self._start = now

    def finalize(self) -> PipelineMetrics:
        self.metrics.total_ms = round((time.monotonic() - self._total_start) * 1000, 1)
        logger.info(f"[PipelineMetrics] {self.metrics.to_dict()}")
        return self.metrics
