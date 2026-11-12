"""AWS Lambda entrypoint: the same remote MCP + gateway checks, behind API Gateway (HTTP API)."""
from mangum import Mangum

from .remote_main import build_remote

_app = build_remote().streamable_http_app()
handler = Mangum(_app, lifespan="auto")
