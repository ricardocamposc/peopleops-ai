# Synthetic Reference HRIS

This directory owns the fictitious source database used by the Reference MCP
Server. It is a development/demo fixture, not the PeopleOps data contract.

Apply the schema with `alembic -c alembic.ini upgrade head` from this directory,
then load `seeds/seed.sql` with `psql`. The seed is deterministic and contains
the scenarios and expected facts in `seeds/ground_truth.json`.

The database is read-only from the product perspective. No PeopleOps module,
ORM model, credential, or migration imports this schema.
