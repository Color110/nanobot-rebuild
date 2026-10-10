from __future__ import annotations

import json
from pathlib import Path

from .models import EvalCase, EvalSuiteResult


def load_eval_cases(path: str | Path) -> tuple[EvalCase, ...]:
    source = Path(path)
    cases: list[EvalCase] = []
    with source.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                cases.append(EvalCase.model_validate_json(stripped))
            except Exception as exc:
                raise ValueError(f"非法 EvalCase: {source}:{lineno}: {exc}") from exc
    if not cases:
        raise ValueError(f"Eval 文件为空: {source}")
    return tuple(cases)


def save_eval_report(report: EvalSuiteResult, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return target
