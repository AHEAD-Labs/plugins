"""Entra objects for the Azure tag-compliance agent and the on-behalf-of (OBO) exchange. Idempotent.

  python platforms/entra/agent_setup.py            # create / reuse; prints identifiers only
  python platforms/entra/agent_setup.py --destroy  # delete the agent API app (the OBO secret is removed with --destroy too)

Creates API app `gmo-tag-agent` (scope tag-compliance:read, v2 tokens, tagged). Pre-authorises:
  - gmo-project-status (the MCP that exchanges a user's token for an agent token: OBO)
  - gmo-codex-client   (Codex calling the agent gateway directly)
  - Azure CLI          (testing only: lets `az account get-access-token` mint a token we must REJECT)
Gives gmo-project-status a client secret for the OBO call and stores it in AWS SSM (/gmo/obo-client-secret).
The secret value is never printed.
"""
import json, subprocess, sys, uuid

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import setup as base  # noqa  (reuses az/find/graph_patch helpers)

AGENT, SCOPE = "gmo-tag-agent", "tag-compliance:read"
SSM_PARAM = "/gmo/obo-client-secret"


def ensure():
    tenant = base.az("account", "show")["tenantId"]
    mcp, codex = base.find(base.API), base.find(base.CLIENT)
    if not mcp or not codex: sys.exit("run platforms/entra/setup.py first")
    agent = base.find(AGENT) or base.az("ad", "app", "create", "--display-name", AGENT, "--sign-in-audience", "AzureADMyOrg")
    ex = next((s for s in (agent.get("api") or {}).get("oauth2PermissionScopes", []) if s["value"] == SCOPE), None)
    sid = ex["id"] if ex else str(uuid.uuid4())
    base.graph_patch(agent["id"], {"identifierUris": [f"api://{agent['appId']}"], "tags": [base.TAG],
        "api": {"requestedAccessTokenVersion": 2, "oauth2PermissionScopes": [{"id": sid, "value": SCOPE, "type": "User",
            "isEnabled": True, "adminConsentDisplayName": "Inspect tag compliance", "userConsentDisplayName": "Inspect tag compliance",
            "adminConsentDescription": "Run the tag-compliance agent on the user's behalf",
            "userConsentDescription": "Run the tag-compliance agent on your behalf"}]}})
    base.graph_patch(agent["id"], {"api": {"preAuthorizedApplications": [
        {"appId": a, "delegatedPermissionIds": [sid]} for a in (mcp["appId"], codex["appId"], base.AZ_CLI_CLIENT)]}})
    if not base.az("ad", "sp", "list", "--filter", f"appId eq '{agent['appId']}'"):
        base.az("ad", "sp", "create", "--id", agent["appId"])
    # the MCP app declares it needs the agent scope (OBO target)
    cur = (base.az("ad", "app", "show", "--id", mcp["appId"]).get("requiredResourceAccess") or [])
    if not any(r["resourceAppId"] == agent["appId"] for r in cur):
        base.graph_patch(mcp["id"], {"requiredResourceAccess": cur + [
            {"resourceAppId": agent["appId"], "resourceAccess": [{"id": sid, "type": "Scope"}]}]})
    # OBO needs the MCP app to prove who it is to Entra: a client secret, kept only in SSM
    have = subprocess.run(["aws", "ssm", "get-parameter", "--name", SSM_PARAM, "--region", "us-east-1"], capture_output=True)
    if have.returncode:
        cred = base.az("ad", "app", "credential", "reset", "--id", mcp["appId"], "--append", "--display-name", "gmo-obo", "--years", "1")
        put = subprocess.run(["aws", "ssm", "put-parameter", "--name", SSM_PARAM, "--type", "SecureString", "--region", "us-east-1",
                              "--value", cred["password"], "--tags", "Key=project,Value=governed-mcp-onboarding"], capture_output=True, text=True)
        if put.returncode: sys.exit("could not store the OBO secret: " + put.stderr[:200])
        stored = "created and stored in SSM"
    else:
        stored = "already in SSM (unchanged)"
    out = {"tenant_id": tenant, "agent_client_id": agent["appId"], "agent_audience": f"api://{agent['appId']}",
           "agent_scope": f"api://{agent['appId']}/{SCOPE}", "mcp_client_id": mcp["appId"], "codex_client_id": codex["appId"],
           "obo_secret": stored}
    print(json.dumps(out, indent=2)); return out


if __name__ == "__main__":
    if "--destroy" in sys.argv:
        a = base.find(AGENT)
        if a: base.az("ad", "app", "delete", "--id", a["appId"], parse=False); print("deleted", AGENT)
        subprocess.run(["aws", "ssm", "delete-parameter", "--name", SSM_PARAM, "--region", "us-east-1"], capture_output=True)
        print("note: the gmo-obo secret on gmo-project-status expires on its own (1 year); remove it in the portal if wanted")
    else:
        ensure()
