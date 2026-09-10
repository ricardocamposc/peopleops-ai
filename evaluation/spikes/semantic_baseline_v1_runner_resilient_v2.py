"""Semantic Baseline v1 resilient runner with corrected reporting partitions.

Execution semantics remain frozen in semantic_baseline_v1_runner_resilient.
This wrapper changes only aggregate reporting so the fixed group-F comparison
suite is classified correctly even when an abstaining comparison has
``expected.comparison == null``.
"""
from __future__ import annotations

import semantic_baseline_v1_reporting_v2 as reporting
import semantic_baseline_v1_runner_resilient as resilient

RUNNER_VERSION = "semantic-baseline-v1-resilient-v2"

_original_aggregate = resilient._aggregate


def _corrected_aggregate(rows, cases):
    metrics = _original_aggregate(rows, cases)
    metrics = reporting.correct_partition_metrics(rows, metrics)
    metrics["runner_version"] = RUNNER_VERSION
    return metrics


def main() -> None:
    reporting.assert_reporting_contract()
    resilient._aggregate = _corrected_aggregate
    resilient.RUNNER_VERSION = RUNNER_VERSION
    resilient.main()


if __name__ == "__main__":
    main()
