"""Flat JSON-file cache for judge calls.

Cache key is sha256(case, trace, model, temperature, k) - k (the repeat index) is part of
the key so each of the k repeated judge runs on the same item gets its own cache entry.
Without k in the key, reruns would always replay run 0's cached verdict for every k, making
flip-rate always read 0. Cache lives in gitignored benchmarks/.cache/ - never committed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from traceeval.core.schema import AgentTrace, EDDTestCase, EvaluationResult

DEFAULT_CACHE_DIR = Path("benchmarks/.cache")


def cache_key(case: EDDTestCase, trace: AgentTrace, model: str, temperature: float, k: int) -> str:
    payload = json.dumps(
        {
            "case": case.model_dump(mode="json"),
            "trace": trace.model_dump(mode="json"),
            "model": model,
            "temperature": temperature,
            "k": k,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JudgeCache:
    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Optional[EvaluationResult]:
        path = self._path(key)
        if not path.exists():
            return None
        return EvaluationResult.model_validate_json(path.read_text(encoding="utf-8"))

    def set(self, key: str, result: EvaluationResult) -> None:
        self._path(key).write_text(result.model_dump_json(indent=2), encoding="utf-8")
