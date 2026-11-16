"""One correlation id per request, carried across hops so a single user action can be followed from the
laptop through the MCP to the agent. Accepts a caller-supplied `x-correlation-id` (checked), else makes one."""
import re, uuid

from project_status.audit import CORRELATION

HEADER = "x-correlation-id"
_OK = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def clean(value: str | None) -> str:
    return value if value and _OK.match(value) else uuid.uuid4().hex


class Correlation:
    """ASGI middleware: set the id for the request, echo it on the response."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        hdr = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        cid = clean(hdr.get(HEADER))
        token = CORRELATION.set(cid)

        async def send_with_id(msg):
            if msg["type"] == "http.response.start":
                msg = {**msg, "headers": [*msg.get("headers", []), (HEADER.encode(), cid.encode())]}
            await send(msg)
        try:
            await self.app(scope, receive, send_with_id)
        finally:
            CORRELATION.reset(token)
