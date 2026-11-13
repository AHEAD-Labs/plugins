"""Remote transport: the capability hosted behind the platform gateway (Streamable HTTP)."""
import os
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from project_status.backend import HttpBackend, InProcessBackend
from project_status.server import build_server
from . import agent_client, entra, idp
from .gateway import GatewayTokenVerifier

ENDPOINT = lambda: os.environ.get("GMO_REMOTE_ENDPOINT", "http://127.0.0.1:8802/mcp")


def build_remote():
    endpoint = ENDPOINT()
    u = urlparse(endpoint)
    url = os.environ.get("GMO_BACKEND_URL", "http://127.0.0.1:8801")
    # "inprocess": AWS first pass runs the synthetic backend inside the function (no separate
    # backend service yet). Any other value is the backend API base URL.
    backend = InProcessBackend() if url == "inprocess" else HttpBackend(
        url, lambda: idp.mint("svc:project-status-mcp", idp.BACKEND_AUDIENCE,
                              scope="backend:read", ttl=120))
    agent = None
    if agent_client.configured():  # set by the deployment from the signed agent release
        async def agent(request, answer):  # noqa: F811
            return await agent_client.call_tool(get_access_token().token, "tag.inspect",
                                                {"request": request, "answer": answer})
    return build_server(
        backend, lambda: get_access_token().subject, transport="streamable-http", agent=agent,
        host=u.hostname, port=u.port or (443 if u.scheme == "https" else 80),
        streamable_http_path=u.path,
        stateless_http=True, json_response=True,
        token_verifier=GatewayTokenVerifier(audience=endpoint),
        auth=AuthSettings(issuer_url=AnyHttpUrl(entra.issuer() if entra.enabled() else idp.ISSUER), resource_server_url=AnyHttpUrl(endpoint),
                          required_scopes=["project-status:read"]),
    )


def main() -> None:
    build_remote().run(transport="streamable-http")


if __name__ == "__main__":
    main()
