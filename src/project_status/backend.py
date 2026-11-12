"""Backend abstraction: the same tool code runs over an in-process or HTTP backend."""
from typing import Awaitable, Callable, Protocol

import httpx

from . import CAPABILITY_ID, __version__, data
from .data import AccessDenied, NotFound


class Backend(Protocol):
    async def list_projects(self, user: str) -> list[dict]: ...
    async def get_status(self, user: str, project_id: str) -> dict: ...


class InProcessBackend:
    """Local mode: reads permitted local (synthetic) data directly."""
    async def list_projects(self, user): return data.list_for(user)
    async def get_status(self, user, project_id): return data.status_for(user, project_id)


class HttpBackend:
    """Remote mode: calls the backend API with a service credential + on-behalf-of user.
    The caller's own token is never forwarded (no token passthrough)."""
    def __init__(self, base_url: str, token_provider: Callable[[], str]):
        self.base, self.token = base_url.rstrip("/"), token_provider

    async def _get(self, path: str, user: str):
        headers = {"Authorization": f"Bearer {self.token()}", "X-On-Behalf-Of": user,
                   "X-Capability-Id": CAPABILITY_ID, "X-Capability-Version": __version__}
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(self.base + path, headers=headers)
        if r.status_code == 403: raise AccessDenied(path)
        if r.status_code == 404: raise NotFound(path)
        r.raise_for_status()
        return r.json()

    async def list_projects(self, user): return (await self._get("/projects", user))["projects"]
    async def get_status(self, user, project_id): return await self._get(f"/projects/{project_id}", user)
