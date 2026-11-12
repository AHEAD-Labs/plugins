"""Create (idempotently) the Entra app registrations for the governed MCP, via the Azure CLI.

  python platforms/entra/setup.py            # create / reuse, print ids
  python platforms/entra/setup.py --destroy  # delete both apps

API app  `gmo-project-status`  exposes scope  project-status:read  (token version 2, single tenant)
Client   `gmo-codex-client`    public client for Codex sign-in (redirect http://127.0.0.1:3334/callback)
Both are tagged `governed-mcp-onboarding`. Azure CLI is pre-authorised on the API so
`az account get-access-token --scope api://<api-id>/project-status:read` works for testing.
"""
import json, subprocess, sys, uuid

AZ_CLI_CLIENT = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"   # Microsoft Azure CLI (well-known first-party id)
API, CLIENT = "gmo-project-status", "gmo-codex-client"
SCOPE = "project-status:read"
TAG = "governed-mcp-onboarding"


def az(*a, parse=True):
    r = subprocess.run(["az", *a, "-o", "json"], capture_output=True, text=True)
    if r.returncode: sys.exit(f"az {' '.join(a[:3])} failed: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout) if parse and r.stdout.strip() else None


def find(name):
    apps = az("ad", "app", "list", "--display-name", name)
    return next((a for a in apps if a["displayName"] == name), None)


def graph_patch(obj_id, body):
    az("rest", "--method", "PATCH", "--url", f"https://graph.microsoft.com/v1.0/applications/{obj_id}",
       "--headers", "Content-Type=application/json", "--body", json.dumps(body), parse=False)


def ensure():
    tenant = az("account", "show")["tenantId"]
    api = find(API) or az("ad", "app", "create", "--display-name", API, "--sign-in-audience", "AzureADMyOrg")
    existing = next((s for s in (api.get("api") or {}).get("oauth2PermissionScopes", []) if s["value"] == SCOPE), None)
    scope_id = existing["id"] if existing else str(uuid.uuid4())
    graph_patch(api["id"], {
        "identifierUris": [f"api://{api['appId']}"], "tags": [TAG],
        "api": {"requestedAccessTokenVersion": 2,
                "oauth2PermissionScopes": [{"id": scope_id, "value": SCOPE, "type": "User", "isEnabled": True,
                    "adminConsentDisplayName": "Read project status", "userConsentDisplayName": "Read project status",
                    "adminConsentDescription": "Read project status through the governed MCP",
                    "userConsentDescription": "Read project status through the governed MCP"}]}})
    # a scope must exist before a client can be pre-authorised for it, so this is a second call
    graph_patch(api["id"], {"api": {"preAuthorizedApplications": [
        {"appId": AZ_CLI_CLIENT, "delegatedPermissionIds": [scope_id]}]}})
    sp = az("ad", "sp", "list", "--filter", f"appId eq '{api['appId']}'")
    if not sp: az("ad", "sp", "create", "--id", api["appId"])
    cl = find(CLIENT) or az("ad", "app", "create", "--display-name", CLIENT, "--sign-in-audience", "AzureADMyOrg")
    graph_patch(cl["id"], {"tags": [TAG], "isFallbackPublicClient": True,
        "publicClient": {"redirectUris": ["http://127.0.0.1:3334/callback", "http://localhost:3334/callback"]},
        "requiredResourceAccess": [{"resourceAppId": api["appId"], "resourceAccess": [{"id": scope_id, "type": "Scope"}]}]})
    sp = az("ad", "sp", "list", "--filter", f"appId eq '{cl['appId']}'")
    if not sp: az("ad", "sp", "create", "--id", cl["appId"])
    out = {"tenant_id": tenant, "api_client_id": api["appId"], "api_audience": f"api://{api['appId']}",
           "scope": f"api://{api['appId']}/{SCOPE}", "codex_client_id": cl["appId"],
           "issuer": f"https://login.microsoftonline.com/{tenant}/v2.0",
           "jwks": f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"}
    print(json.dumps(out, indent=2)); return out


if __name__ == "__main__":
    if "--destroy" in sys.argv:
        for n in (API, CLIENT):
            a = find(n)
            if a: az("ad", "app", "delete", "--id", a["appId"], parse=False); print("deleted", n)
    else:
        ensure()
