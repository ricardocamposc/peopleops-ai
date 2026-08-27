import json
import logging

from peopleops_api.observability import JsonFormatter, optional_langsmith_trace, request_id_context


def test_json_logs_include_correlation_and_stage(caplog):
    token = request_id_context.set("request-16")
    try:
        with caplog.at_level(logging.INFO):
            logging.getLogger("test").info(
                "stage complete",
                extra={"event": "stage", "stage": "synthesis", "status": "completed"},
            )
        record = caplog.records[-1]
        payload = json.loads(JsonFormatter().format(record))
        assert payload["request_id"] == "request-16"
        assert payload["stage"] == "synthesis"
        assert payload["status"] == "completed"
    finally:
        request_id_context.reset(token)


def test_langsmith_is_optional(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    with optional_langsmith_trace(name="test", request_id="request-16"):
        pass
