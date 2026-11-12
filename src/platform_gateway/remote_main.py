"""Remote transport: the capability hosted behind the platform gateway (Streamable HTTP)."""
import os
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from project_status.backend import HttpBackend
from project_status.server import build_server
from . import idp
from .gateway import GatewayTokenVerifier

ENDPOINT = lambda: os.environ.get("GMO_REMOTE_ENDPOINT", "http://127.0.0.1:8802/mcp")


def build_remote():
    endpoint = ENDPOINT()
    u = urlparse(endpoint)
    backend = HttpBackend(os.environ.get("GMO_BACKEND_URL", "http://127.0.0.1:8801"),
                          lambda: idp.mint("svc:project-status-mcp", idp.BACKEND_AUDIENCE,
                                           scope="backend:read", ttl=120))
    return build_server(
        backend, lambda: get_access_token().subject, transport="streamable-http",
        host=u.hostname, port=u.port, streamable_http_path=u.path,
        stateless_http=True, json_response=True,
        token_verifier=GatewayTokenVerifier(audience=endpoint),
        auth=AuthSettings(issuer_url=AnyHttpUrl(idp.ISSUER), resource_server_url=AnyHttpUrl(endpoint),
                          required_scopes=["project-status:read"]),
    )


def main() -> None:
    build_remote().run(transport="streamable-http")


if __name__ == "__main__":
    main()
