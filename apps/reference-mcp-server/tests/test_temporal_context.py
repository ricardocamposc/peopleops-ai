from datetime import date, datetime

from reference_mcp_server.temporal import TemporalContext


def test_temporal_context_is_provider_neutral_and_typed() -> None:
    context = TemporalContext(
        source_current_date=date(2026, 8, 29),
        source_current_timestamp=datetime(2026, 8, 29, 12),
        source_timezone="UTC",
        current_year=2026,
        current_month=8,
    )
    assert context.model_dump(mode="json") == {
        "source_current_date": "2026-08-29",
        "source_current_timestamp": "2026-08-29T12:00:00",
        "source_timezone": "UTC",
        "current_year": 2026,
        "current_month": 8,
    }
