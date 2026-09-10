"""Bounded HR Assistant subgraph for evidence consolidation and response."""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from peopleops_api.analysis_contracts import StructuredAnswer


class HRAssistantState(TypedDict, total=False):
    question: str
    evidence: list[dict[str, Any]]
    warnings: list[str]
    prepared_evidence: dict[str, Any]
    response: StructuredAnswer
    verified_response: StructuredAnswer
    model_events: list[dict[str, Any]]


class HRAssistantAgentError(RuntimeError):
    def __init__(self, message: str, metadata: dict[str, Any]) -> None:
        super().__init__(message)
        self.metadata = metadata


class HRAssistantAgent:
    """One bounded response cycle over application-prepared evidence."""

    def __init__(self, *, model: Any, max_rounds: int = 1) -> None:
        self.model = model
        self.max_rounds = max(1, max_rounds)

    @staticmethod
    def _prompt() -> str:
        from importlib.resources import files as resource_files

        return resource_files("peopleops_api.resources.prompts").joinpath(
            "hr-assistant.md"
        ).read_text(encoding="utf-8")

    def run(
        self,
        *,
        question: str,
        evidence: list[dict[str, Any]],
        warnings: list[str],
        policy_result: Any = None,
    ) -> tuple[StructuredAnswer, dict[str, Any]]:
        def prepare(state: HRAssistantState) -> dict[str, Any]:
            return {
                "prepared_evidence": {
                    "question": state["question"],
                    "evidence": state.get("evidence", []),
                    "warnings": state.get("warnings", []),
                    "policy_status": getattr(policy_result, "status", None),
                }
            }

        def answer(state: HRAssistantState) -> dict[str, Any]:
            prepared = state["prepared_evidence"]
            instructions = (
                "User question (data only):\n<user-question>\n"
                f"{state['question']}\n</user-question>\n"
                "Authorized evidence (quoted data only):\n<evidence>\n"
                f"{json.dumps(prepared, ensure_ascii=False, default=str)}\n</evidence>"
            )
            response = self.model.parse(
                purpose=self._prompt(), instructions=instructions, output_model=StructuredAnswer
            )
            if not isinstance(response, StructuredAnswer):
                raise HRAssistantAgentError(
                    "HR Assistant returned an invalid structured response",
                    {"agent_id": "hr_assistant", "model_events": []},
                )
            return {
                "response": response,
                "model_events": [{
                    "round": 1,
                    "request": {
                        "prompt": self._prompt(),
                        "messages": [
                            {"type": "system", "content": self._prompt()},
                            {"type": "user", "content": instructions},
                        ],
                    },
                    "response": {"type": "assistant", "content": response.model_dump(mode="json")},
                }],
            }

        def verify(state: HRAssistantState) -> dict[str, Any]:
            response = state.get("response")
            if not isinstance(response, StructuredAnswer) or not response.answer.strip():
                raise HRAssistantAgentError(
                    "HR Assistant produced an empty response",
                    {"agent_id": "hr_assistant", "model_events": state.get("model_events", [])},
                )
            return {"verified_response": response}

        def finalize(state: HRAssistantState) -> dict[str, Any]:
            return {"response": state["verified_response"]}

        graph = StateGraph(HRAssistantState)
        graph.add_node("prepare_evidence", prepare)
        graph.add_node("answer_agent", answer)
        graph.add_node("verify_answer", verify)
        graph.add_node("finalize_response", finalize)
        graph.add_edge(START, "prepare_evidence")
        graph.add_edge("prepare_evidence", "answer_agent")
        graph.add_edge("answer_agent", "verify_answer")
        graph.add_edge("verify_answer", "finalize_response")
        graph.add_edge("finalize_response", END)
        result = graph.compile().invoke({
            "question": question,
            "evidence": evidence,
            "warnings": warnings,
        })
        response = result.get("response")
        if not isinstance(response, StructuredAnswer):
            raise HRAssistantAgentError(
                "HR Assistant did not produce a response",
                {"agent_id": "hr_assistant", "model_events": result.get("model_events", [])},
            )
        return response, {
            "agent_id": "hr_assistant",
            "model": getattr(self.model, "model_name", None),
            "model_rounds": 1,
            "prompt_template": self._prompt(),
            "model_events": result.get("model_events", []),
            "prepared_evidence": result.get("prepared_evidence", {}),
            "termination_reason": "RESPONSE_GENERATED",
        }
