"""Minimal MCP client helpers (stand-in for Codex) used by evaluation, deploy smoke tests and demo."""
import asyncio, json
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


def _parse(res):
    if res.structuredContent is not None:
        return res.structuredContent
    text = "".join(c.text for c in res.content if getattr(c, "text", None))
    try:
        return json.loads(text)
    except ValueError:
        return text


@asynccontextmanager
async def stdio_session(command: str, args: list[str], env: dict):
    import os
    params = StdioServerParameters(command=command, args=args, env={**os.environ, **env})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            yield s


@asynccontextmanager
async def http_session(url: str, token: str):
    async with streamablehttp_client(url, headers={"Authorization": f"Bearer {token}"}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            yield s


async def call(session, tool: str, **args) -> tuple[bool, object]:
    """Returns (ok, payload). ok=False means the tool returned an error."""
    res = await session.call_tool(tool, args)
    return (not res.isError), _parse(res)


async def http_status(url: str, token: str | None) -> int:
    """Raw HTTP status of an MCP initialize — shows gateway admission decisions."""
    h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "probe", "version": "0"}}}
    async with httpx.AsyncClient(timeout=10) as c:
        return (await c.post(url, json=body, headers=h)).status_code


def run(coro):
    return asyncio.run(coro)
