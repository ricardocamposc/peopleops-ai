"""Provider-side read-only probe used as supplementary MCP baseline evidence."""

from __future__ import annotations

import json
import os

import psycopg

from reference_mcp_server.execution import (
    PhysicalQuery,
    QueryExecutionError,
    validate_physical_query,
)


STATEMENTS = (
    "INSERT INTO employee (employee_code) VALUES ('MUTATION')",
    "UPDATE employee SET status = 'inactive'",
    "DELETE FROM employee",
    "DROP TABLE employee",
    "ALTER TABLE employee ADD COLUMN unsafe text",
    "CREATE TABLE unsafe (id integer)",
    "TRUNCATE employee",
    "SELECT 1; UPDATE employee SET status = 'inactive'",
)


def main() -> None:
    results = []
    application_rejections = True
    for statement in STATEMENTS:
        try:
            validate_physical_query(PhysicalQuery(statement, (), []))
        except QueryExecutionError as exc:
            results.append(
                {"statement": statement, "rejected": exc.code == "PHYSICAL_QUERY_INVALID"}
            )
            application_rejections &= exc.code == "PHYSICAL_QUERY_INVALID"
        else:
            results.append({"statement": statement, "rejected": False})

    database_unchanged = False
    database_url = os.environ.get(
        "SYNTHETIC_HRIS_TEST_DATABASE_URL",
        "postgresql://synthetic_hris_app:synthetic_hris_local_placeholder@127.0.0.1:5437/synthetic_hris",
    )
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM employee")
                before = cursor.fetchone()[0]
            try:
                with connection.transaction():
                    connection.execute("SET LOCAL transaction_read_only = on")
                    connection.execute("UPDATE employee SET status = 'inactive'")
            except psycopg.errors.ReadOnlySqlTransaction:
                pass
            else:
                raise RuntimeError("database accepted a write in read-only transaction")
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM employee")
                database_unchanged = cursor.fetchone()[0] == before
    except (psycopg.Error, OSError) as exc:
        results.append({"database_probe_error": type(exc).__name__})

    print(
        json.dumps(
            {
                "application_validation": application_rejections,
                "database_level_read_only": database_unchanged,
                "database_unchanged": database_unchanged,
                "statements": results,
                "passed": application_rejections and database_unchanged,
            }
        )
    )


if __name__ == "__main__":
    main()
