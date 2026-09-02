"""Phase 3.6.1 — typed request-shape isolation experiment.

The experiment isolates the stronger Phase 3.6 comparison discipline from
simple requests. A dedicated Structured Output call classifies only the request
shape as SIMPLE or COMPARISON. Deterministic code routes on that typed value;
it never inspects natural-language text.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

import semantic_understanding_phase343 as phase343
import semantic_understanding_phase36 as phase36


class RequestShapeV361(BaseModel):
    mode: Literal["SIMPLE", "COMPARISON"]


REQUEST_SHAPE_PROMPT_V361 = """
PHASE 3.6.1 — REQUEST SHAPE CLASSIFICATION

Classify only the semantic shape of the request. Do not resolve dates, units,
measures, fields, grouping, capabilities, or answerability.

Return COMPARISON only when the request asks to contrast, compare, relate, or
compute a change between TWO distinct analytical operands or scopes in the
same request. The request remains COMPARISON even if one operand is ambiguous
or unsupported; shape classification is separate from answerability.

Return SIMPLE when the request asks about one analytical scope, including a
single relative scope such as a current, previous, or rolling period. A single
ambiguous period is still SIMPLE if there is no second operand.

Do not infer a second operand merely because the request uses a relative term.
Do not decide whether the comparison is valid. Decide only whether two
analytical operands are requested.
"""


def understanding_prompt(mode: Literal["SIMPLE", "COMPARISON"]) -> str:
    """Select a frozen prompt from a typed semantic-shape decision."""
    if mode == "COMPARISON":
        return phase36.UNDERSTANDING_PROMPT_V36
    return phase343.UNDERSTANDING_PROMPT_V343


def assert_phase361_contract() -> None:
    phase36.assert_phase36_contract()
    contract = REQUEST_SHAPE_PROMPT_V361
    assert "TWO distinct analytical operands" in contract
    assert "single relative scope" in contract
    assert "shape classification is separate from answerability" in contract
    assert understanding_prompt("SIMPLE") == phase343.UNDERSTANDING_PROMPT_V343
    assert understanding_prompt("COMPARISON") == phase36.UNDERSTANDING_PROMPT_V36


if __name__ == "__main__":
    assert_phase361_contract()
    print("SEMANTIC_UNDERSTANDING_PHASE361_SELF_TEST_OK")
