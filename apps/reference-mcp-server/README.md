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
