"""AWS Lambda entrypoint: the same remote MCP + gateway checks, behind API Gateway (HTTP API).

The MCP session manager can only be started once per app instance, while the Lambda adapter
starts the ASGI lifespan on every invocation. The server is stateless (stateless_http=True), so
we build a fresh app per invocation: cheap, and nothing is shared between requests."""
from mangum import Mangum

from .remote_main import build_remote


def handler(event, context):
    return Mangum(build_remote().streamable_http_app(), lifespan="auto")(event, context)
