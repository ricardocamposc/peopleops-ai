# Reference MCP Server

The reference source is a real MCP server using the official Python SDK and
Streamable HTTP. Its functional endpoint is `/mcp`; `/health` is an operational
endpoint only and is not part of the data contract.

The server exposes generic MCP tools:

- `discover_catalog`
- `discover_capabilities`
- `discover_entities`
- `describe_entity`
- `discover_relationships`
- `validate_conceptual_query`
- `execute_conceptual_query`

The catalog uses provider-neutral entity identifiers and typed Pydantic
responses. Physical table/column mappings are source-adapter metadata and are
kept inside this deployable. Payroll entities and fields are classified as
`restricted`; no write operation is advertised.

The deployed server composes provider semantic mappings with physical
PostgreSQL introspection. It owns physical translation, validation, EXPLAIN,
read-only execution, limits, timeouts and provider-neutral evidence. PeopleOps
receives only the MCP contract and never receives Synthetic HRIS credentials.

For local development, start it with `make mcp` after the synthetic HRIS is
available. The PeopleOps `HRDataGateway` connects to
`http://127.0.0.1:8001/mcp` using the official MCP client lifecycle.
# Temporal context and MCP audit

The provider exposes a typed `temporal_context` MCP tool. Relative calendar
expressions are resolved from the Synthetic HRIS PostgreSQL source date, not
from the application clock or an LLM-generated date.

MCP calls are persisted by the server in the separate `mcp_audit` PostgreSQL
schema (configurable with `MCP_AUDIT_SCHEMA`). Records retain request/tool
correlation, conceptual query, validation, physical SQL template and separate
parameters, execution timing, row count and safe error status. Credentials and
authorization headers are never persisted.
### Temporal periods

The server exposes provider temporal context and translates provider-neutral `PeriodValue(year, month)` scopes using catalog temporal metadata. Calendar periods are not assumed to be a physical field; date ranges require a catalog-compatible date/datetime field, and invalid temporal field combinations are rejected before SQL execution.
