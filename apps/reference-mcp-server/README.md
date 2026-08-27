# Reference MCP Server — Discovery

Slice 03 exposes the reference source catalog through the server's minimal
HTTP discovery transport. The transport is intentionally read-only and does
not accept conceptual queries yet.

Endpoints:

- `GET /health`
- `GET /discovery/catalog` — complete versioned catalog and SHA-256 fingerprint
- `GET /discovery/capabilities`
- `GET /discovery/entities`
- `GET /discovery/entities/{entity_id}`
- `GET /discovery/relationships`

The catalog uses provider-neutral entity identifiers and typed Pydantic
responses. Physical table/column mappings are source-adapter metadata and are
kept inside this deployable. Payroll entities and fields are classified as
`restricted`; no write operation is advertised.

Conceptual-query validation, execution, evidence, and the PeopleOps MCP
client/gateway are intentionally deferred to later slices.
