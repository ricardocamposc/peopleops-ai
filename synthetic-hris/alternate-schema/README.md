# Schema B — MCP contract fixture

Schema B is deliberately smaller and structurally different from the
reference fixture. It uses `HR_PERSON`, `HR_CONTRACT`, `TIME_EVENT`, `PAY_RUN`
and `PAY_MOVEMENT`; the semantic IDs remain the MCP contract. Mapping belongs
to `reference_mcp_server.alternate_schema` and is never imported by PeopleOps.

Apply `migration.sql` and then `seed.sql` to an isolated PostgreSQL database.
