"""Entra on-behalf-of (OBO) exchange: the calling MCP swaps the USER's token for a token aimed at a
downstream API, keeping the user's identity. The user's original token is never forwarded."""
import httpx


def exchange(user_token: str, *, tenant: str, client_id: str, client_secret: str, scope: str, timeout: float = 15) -> str:
    r = httpx.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", timeout=timeout, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "requested_token_use": "on_behalf_of",
        "client_id": client_id, "client_secret": client_secret, "assertion": user_token, "scope": scope})
    if r.status_code != 200:
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        raise PermissionError(f"OBO refused: {err.get('error')} - {str(err.get('error_description'))[:160]}")
    return r.json()["access_token"]
