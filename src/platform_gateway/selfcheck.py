"""Platform check run by the pipeline against the *built artifact* (via PYTHONPATH):
the remote deployment must reject missing / wrong-audience / wrong-scope tokens."""
import asyncio, json

import httpx

from . import idp
from .remote_main import ENDPOINT, build_remote

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "selfcheck", "version": "0"}}}
HDRS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


async def run() -> list[dict]:
    app = build_remote().streamable_http_app()
    path = "/mcp"
    cases = {
        "no_token": {},
        "wrong_audience": {"Authorization": "Bearer " + idp.mint("alice", "https://other.example/mcp")},
        "wrong_scope": {"Authorization": "Bearer " + idp.mint("alice", ENDPOINT(), scope="other:scope")},
        "garbage_token": {"Authorization": "Bearer not-a-jwt"},
    }
    out = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        for name, extra in cases.items():
            r = await c.post(path, json=INIT, headers={**HDRS, **extra})
            out.append({"case": name, "status": r.status_code, "passed": r.status_code in (401, 403)})
    return out


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run())))
