"""Call a governed agent on behalf of the signed-in user.

The MCP never forwards the user's token. It swaps it (Entra on-behalf-of) for a token aimed only at
the agent's API, then calls the agent's gateway, which checks the token, the scope, the calling app and
the suspension list. Configuration comes from the deployment (the signed agent release), not from code:

  GMO_AGENT_ENDPOINT    the agent gateway's MCP URL
  GMO_AGENT_SCOPE       api://<agent app>/<scope>
  GMO_ENTRA_TENANT, GMO_OBO_CLIENT_ID    this MCP's own Entra app
  GMO_OBO_SECRET or GMO_OBO_SECRET_SSM   its client secret (an SSM parameter name on AWS, never in the code)
"""
import asyncio, json, os

import httpx

from . import obo

_secret_cache: dict[str, str] = {}


def configured() -> bool:
    need = ("GMO_AGENT_ENDPOINT", "GMO_AGENT_SCOPE", "GMO_ENTRA_TENANT", "GMO_OBO_CLIENT_ID")
    return all(os.environ.get(k) for k in need) and bool(os.environ.get("GMO_OBO_SECRET") or os.environ.get("GMO_OBO_SECRET_SSM"))


def _secret() -> str:
    if os.environ.get("GMO_OBO_SECRET"):
        return os.environ["GMO_OBO_SECRET"]
    name = os.environ["GMO_OBO_SECRET_SSM"]
    if name not in _secret_cache:
        import boto3
        _secret_cache[name] = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    return _secret_cache[name]


def _body(resp: httpx.Response) -> dict:
    text = resp.text.strip()
    if text.startswith("event:") or text.startswith("data:"):  # Streamable HTTP may answer as one SSE event
        text = next(l[5:].strip() for l in text.splitlines() if l.startswith("data:"))
    return json.loads(text)


async def call_tool(user_token: str, tool: str, arguments: dict, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Returns the agent's text answer. Raises PermissionError when the agent's gateway refuses (with its reason)."""
    agent_token = await asyncio.to_thread(
        obo.exchange, user_token, tenant=os.environ["GMO_ENTRA_TENANT"], client_id=os.environ["GMO_OBO_CLIENT_ID"],
        client_secret=_secret(), scope=os.environ["GMO_AGENT_SCOPE"])
    async with httpx.AsyncClient(transport=transport, timeout=90) as c:
        r = await c.post(os.environ["GMO_AGENT_ENDPOINT"], headers={
            "Authorization": f"Bearer {agent_token}", "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}})
    if r.status_code in (401, 403):
        reason = r.json().get("error", "refused") if r.headers.get("content-type", "").startswith("application/json") else "refused"
        raise PermissionError(f"agent gateway refused: {reason}")
    r.raise_for_status()
    result = _body(r).get("result", {})
    text = "".join(p.get("text", "") for p in result.get("content", []) if p.get("type") == "text")
    if result.get("isError"):
        raise RuntimeError(f"agent reported an error: {text[:200]}")
    return text
