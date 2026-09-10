"""Evaluation entrypoint for Phase 3 with strict understanding comparisons.

Keeps the Phase 3 semantic contract unchanged; only fixes evaluator coverage so
missing order_by is detected as well as incorrect order_by.
"""
from __future__ import annotations

from typing import Any

import semantic_understanding_phase3 as phase3


_original_understanding_differences = phase3.understanding_differences


def strict_understanding_differences(
    case: dict[str, Any],
    understanding: phase3.SemanticUnderstanding,
) -> list[str]:
    differences = _original_understanding_differences(case, understanding)
    expected_order = case["understanding"].get("order_by", [])
    actual_order = [item.model_dump(exclude_none=True) for item in understanding.order_by]
    if actual_order != expected_order and "UNDERSTANDING_ORDER" not in differences:
        differences.append("UNDERSTANDING_ORDER")
    return differences


def main() -> None:
    phase3.understanding_differences = strict_understanding_differences
    phase3.main()


if __name__ == "__main__":
    main()
