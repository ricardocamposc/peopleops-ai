from fastapi import FastAPI

from reference_mcp_server.config import get_settings

settings = get_settings()
app = FastAPI(title="Reference MCP Server", version="0.1.0")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
