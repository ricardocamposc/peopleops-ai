from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
API_SOURCE = REPO_ROOT / "apps" / "peopleops-api" / "src"
API_ENV_EXAMPLE = REPO_ROOT / "apps" / "peopleops-api" / ".env.example"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


def test_peopleops_api_has_no_synthetic_hris_credentials():
    env_text = API_ENV_EXAMPLE.read_text(encoding="utf-8")
    api_compose_block = COMPOSE_FILE.read_text(encoding="utf-8").split(
        "  reference-mcp-server:", 1
    )[0]

    forbidden = ("SYNTHETIC_HRIS", "HRIS_DATABASE", "HRIS_DB")
    assert not any(token in env_text for token in forbidden)
    assert not any(token in api_compose_block for token in forbidden)


def test_peopleops_api_does_not_contain_provider_side_query_logic():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in API_SOURCE.rglob("*.py")
        if "__pycache__" not in path.parts
    )

    forbidden = (
        "SYNTHETIC_HRIS_DATABASE",
        "hr_person",
        "employee_payroll",
        "overtime_records",
        "EXPLAIN",
    )
    assert not any(token in source for token in forbidden)
