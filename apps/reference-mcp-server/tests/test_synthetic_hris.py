import os
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from reference_mcp_server.discovery import build_catalog

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "synthetic-hris" / "migrations"
SEED = ROOT / "synthetic-hris" / "seeds" / "seed.sql"
DATABASE_URL = os.getenv("SYNTHETIC_HRIS_TEST_DATABASE_URL")


def _connection() -> psycopg.Connection:
    if not DATABASE_URL:
        pytest.skip("SYNTHETIC_HRIS_TEST_DATABASE_URL is not configured")
    try:
        return psycopg.connect(DATABASE_URL)
    except psycopg.OperationalError as exc:
        pytest.skip(f"synthetic HRIS test PostgreSQL is not available: {exc}")


@pytest.fixture()
def migrated_database():
    connection = _connection()
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA public CASCADE")
        cursor.execute("CREATE SCHEMA public")
    connection.close()

    config = Config(str(ROOT / "synthetic-hris" / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    connection = _connection()
    yield connection
    connection.close()


def _seed(connection: psycopg.Connection) -> None:
    connection.execute(SEED.read_text(encoding="utf-8"))
    connection.commit()


def test_migration_creates_all_reference_entities(migrated_database) -> None:
    with migrated_database.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name <> 'alembic_version' "
            "ORDER BY table_name"
        )
        names = {row[0] for row in cursor.fetchall()}
    assert names == {
        "attendance_incident",
        "attendance_record",
        "contract",
        "department",
        "employee",
        "employee_payroll",
        "leave_request",
        "overtime_record",
        "payroll_concept",
        "payroll_item",
        "payroll_period",
        "position",
        "vacation_balance",
        "vacation_request",
    }


def test_discovery_catalog_maps_to_real_reference_tables(migrated_database) -> None:
    catalog = build_catalog()
    physical_sources = {entity.physical_source for entity in catalog.entities}
    with migrated_database.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
        )
        actual_tables = {row[0] for row in cursor.fetchall()}
    assert physical_sources == actual_tables


def test_seed_is_deterministic_and_preserves_referential_integrity(migrated_database) -> None:
    _seed(migrated_database)
    with migrated_database.cursor() as cursor:
        cursor.execute("SELECT count(*), min(employee_code), max(employee_code) FROM employee")
        first_snapshot = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM employee_payroll p "
            "JOIN employee e ON e.id = p.employee_id "
            "JOIN payroll_period pp ON pp.id = p.payroll_period_id"
        )
        assert cursor.fetchone()[0] == 5
    _seed(migrated_database)
    with migrated_database.cursor() as cursor:
        cursor.execute("SELECT count(*), min(employee_code), max(employee_code) FROM employee")
        assert cursor.fetchone() == first_snapshot


def test_ground_truth_scenarios_are_coherent(migrated_database) -> None:
    _seed(migrated_database)
    with migrated_database.cursor() as cursor:
        cursor.execute(
            "SELECT e.employee_code, vb.available_days, vr.requested_days "
            "FROM employee e JOIN vacation_balance vb ON vb.employee_id = e.id "
            "JOIN vacation_request vr ON vr.employee_id = e.id "
            "WHERE e.employee_code IN ('E-100', 'E-101') ORDER BY e.employee_code"
        )
        assert cursor.fetchall() == [("E-100", 12, 10), ("E-101", 2, 5)]

        cursor.execute(
            "SELECT e.employee_code, c.end_date FROM employee e "
            "JOIN contract c ON c.employee_id = e.id WHERE e.employee_code = 'E-100'"
        )
        assert cursor.fetchone() == ("E-100", __import__("datetime").date(2025, 12, 31))

        cursor.execute(
            "SELECT e.employee_code, "
            "(SELECT SUM(approved_minutes) / 60.0 FROM overtime_record "
            " WHERE employee_id = e.id), "
            "COALESCE((SELECT SUM(pi.quantity) FROM payroll_item pi "
            " JOIN payroll_concept pc ON pc.id = pi.payroll_concept_id "
            " JOIN employee_payroll ep ON ep.id = pi.employee_payroll_id "
            " WHERE ep.employee_id = e.id AND pc.code = 'OT'), 0) "
            "FROM employee e WHERE e.employee_code = 'E-103'"
        )
        assert cursor.fetchone() == ("E-103", 10.0, 0)


def test_payroll_checks_are_true_for_seeded_rows(migrated_database) -> None:
    _seed(migrated_database)
    with migrated_database.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM employee_payroll "
            "WHERE net_amount <> gross_amount - deduction_amount"
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            "SELECT count(*) FROM vacation_balance "
            "WHERE available_days <> earned_days - used_days - scheduled_days"
        )
        assert cursor.fetchone()[0] == 0
