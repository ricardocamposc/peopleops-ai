# OpenAI Codex ↔ PeopleOps MCP validation

This document records the reproducible validation scenario used to verify that the PeopleOps Reference MCP Server can be consumed by an external MCP client without access to the PeopleOps codebase or to the physical HRIS schema.

## Test boundary

The validation was run with:

- `reference-mcp-server` running locally on `127.0.0.1:8001`;
- OpenAI Codex CLI started from a workspace outside the `peopleops-ai` repository;
- no imports from `peopleops_api`;
- no direct connection from Codex to the Synthetic HRIS PostgreSQL database.

The MCP endpoint is:

```text
http://127.0.0.1:8001/mcp
```

## Register the server in Codex

```bash
codex mcp add local_mcp_8001 --url http://127.0.0.1:8001/mcp
codex mcp list
```

Start a fresh Codex session after registration so the MCP server is loaded as a native external tool provider.

## Example natural-language test

Ask Codex:

```text
Using the PeopleOps MCP, tell me which employees have contracts close to expiration.
```

The observed native MCP interaction included:

```text
local_mcp_8001.discover_catalog
        ↓
local_mcp_8001.describe_conceptual_query_contract
        ↓
local_mcp_8001.execute_conceptual_query
```

Codex discovered the provider-neutral semantic model and used the catalog to build a conceptual query involving `employee`, `contract`, and their semantic relationship. The request was scoped with `hr:read`.

When the initial operational time window returned no rows, Codex issued follow-up conceptual queries rather than silently concluding that the data source contained no contract end dates.

## What this validates

This test demonstrates:

1. the Reference MCP Server can be registered by an external OpenAI Codex client;
2. MCP tool discovery works without importing PeopleOps application code;
3. the client can discover HR entities, fields, capabilities and relationships dynamically;
4. the client can construct and execute provider-neutral conceptual queries;
5. the MCP server validates and executes the query under a read-only scope;
6. the external client does not need the physical HRIS schema or HRIS database credentials.

This is an interoperability validation for the PeopleOps MCP boundary. It does not imply that every MCP client has been certified against this implementation.

## Security note

All public/demo data is synthetic. The Reference MCP Server owns physical mapping, validation, execution limits and source credentials. External MCP clients receive only the provider-neutral contract and returned evidence.
