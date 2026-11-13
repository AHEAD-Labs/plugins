"""Deploy the agent gateway to Azure Container Apps (same environment as the agent). Idempotent.

  python platforms/azure/deploy.py --cfg .gmo-demo/entra-agent.json --version 0.1.0
  python platforms/azure/deploy.py --destroy      # removes only gmo-* resources it created

Creates (all tagged project=governed-mcp-onboarding): storage account + container for the suspension
list, image gmo-agent-gateway in the EXISTING registry, Container App gmo-agent-gateway with a system
identity (pulls the image with AcrPull, reads the suspension list with Storage Blob Data Reader).
The existing agent is not modified. The agent's API key is copied into the gateway's own secret.
"""
import argparse, json, os, subprocess, sys, time

RG, ENV, AGENT, ACR = "arm-tag-compliance", "tag-compliance-elna-env", "tag-compliance-elna", "ca165df5fe9cacr"
APP, CONTAINER, BLOB, LOC = "gmo-agent-gateway", "state", "revocations.json", "westus2"
TAGS = "project=governed-mcp-onboarding"
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def az(*a, parse=True, check=True):
    r = subprocess.run(["az", *a, "-o", "json"], capture_output=True, text=True)
    if r.returncode and check: sys.exit(f"az {' '.join(a[:4])} failed: {r.stderr.strip()[:400]}")
    if r.returncode: return None
    return json.loads(r.stdout) if parse and r.stdout.strip() else r.stdout.strip()


def role(principal, role_name, scope):
    az("role", "assignment", "create", "--assignee-object-id", principal, "--assignee-principal-type", "ServicePrincipal",
       "--role", role_name, "--scope", scope, parse=False, check=False)  # re-running is fine: already assigned


def deploy(cfg, ver):
    sub = az("account", "show")
    sa = "gmoagent" + sub["id"].replace("-", "")[:8]
    sa_id = f"/subscriptions/{sub['id']}/resourceGroups/{RG}/providers/Microsoft.Storage/storageAccounts/{sa}"
    if not az("storage", "account", "show", "-g", RG, "-n", sa, check=False):
        print("creating storage account", sa)
        az("storage", "account", "create", "-g", RG, "-n", sa, "-l", LOC, "--sku", "Standard_LRS", "--min-tls-version", "TLS1_2",
           "--allow-blob-public-access", "false", "--tags", TAGS)
    me = az("ad", "signed-in-user", "show")["id"]
    az("role", "assignment", "create", "--assignee-object-id", me, "--assignee-principal-type", "User",
       "--role", "Storage Blob Data Contributor", "--scope", sa_id, parse=False, check=False)
    acr_id = az("acr", "show", "-n", ACR, "--query", "id")
    for _ in range(12):  # new role assignments take a little while
        ok = az("storage", "container", "create", "--account-name", sa, "-n", CONTAINER, "--auth-mode", "login", check=False)
        if ok is not None: break
        time.sleep(10)
    if not az("storage", "blob", "exists", "--account-name", sa, "-c", CONTAINER, "-n", BLOB, "--auth-mode", "login")["exists"]:
        open("/tmp/gmo-empty.json", "w").write("[]")
        az("storage", "blob", "upload", "--account-name", sa, "-c", CONTAINER, "-n", BLOB, "--file", "/tmp/gmo-empty.json",
           "--auth-mode", "login", parse=False)
    print("building image in", ACR)
    subprocess.run(["az", "acr", "build", "-r", ACR, "-t", f"{APP}:{ver}", "-f", "platforms/azure/gateway/Dockerfile", "--no-logs", "."],
                   cwd=REPO, check=True, capture_output=True)
    envid = az("containerapp", "env", "show", "-g", RG, "-n", ENV, "--query", "id")
    app = az("containerapp", "show", "-g", RG, "-n", APP, check=False)
    if not app:
        print("creating container app", APP)
        az("containerapp", "create", "-g", RG, "-n", APP, "--environment", envid, "--image", "mcr.microsoft.com/k8se/quickstart:latest",
           "--target-port", "80", "--ingress", "external", "--system-assigned", "--min-replicas", "1", "--max-replicas", "2",
           "--cpu", "0.25", "--memory", "0.5Gi", "--tags", TAGS)
        app = az("containerapp", "show", "-g", RG, "-n", APP)
    pid = app["identity"]["principalId"]
    role(pid, "AcrPull", acr_id)
    role(pid, "Storage Blob Data Reader", sa_id)
    time.sleep(40)
    az("containerapp", "registry", "set", "-g", RG, "-n", APP, "--server", f"{ACR}.azurecr.io", "--identity", "system", parse=False)
    key = az("containerapp", "secret", "show", "-g", RG, "-n", AGENT, "--secret-name", "tag-agent-api-key", "--query", "value", parse=True)
    agent_fqdn = az("containerapp", "show", "-g", RG, "-n", AGENT, "--query", "properties.configuration.ingress.fqdn")
    az("containerapp", "secret", "set", "-g", RG, "-n", APP, "--secrets", f"agent-key={key}", parse=False)
    env = [f"GMO_ENTRA_TENANT={cfg['tenant_id']}", f"GMO_ENTRA_AUDIENCE={cfg['agent_client_id']}",
           f"GMO_ALLOWED_CALLERS={cfg['mcp_client_id']},{cfg['codex_client_id']}", f"GMO_AGENT_URL=https://{agent_fqdn}/mcp",
           "GMO_AGENT_KEY=secretref:agent-key", f"GMO_REVOCATIONS=azblob://{sa}/{CONTAINER}/{BLOB}", "GMO_REVOCATION_TTL=5",
           "GMO_CAPABILITY_ID=ahead.tag-compliance", f"CAPABILITY_VERSION={ver}"]
    az("containerapp", "update", "-g", RG, "-n", APP, "--image", f"{ACR}.azurecr.io/{APP}:{ver}", "--set-env-vars", *env, parse=False)
    az("containerapp", "ingress", "update", "-g", RG, "-n", APP, "--target-port", "8080", parse=False)
    fqdn = az("containerapp", "show", "-g", RG, "-n", APP, "--query", "properties.configuration.ingress.fqdn")
    return {"platform": "azure", "gateway": APP, "endpoint": f"https://{fqdn}/mcp", "health": f"https://{fqdn}/health",
            "storage": sa, "version": ver, "agent_untouched": True}


def destroy():
    sub = az("account", "show"); sa = "gmoagent" + sub["id"].replace("-", "")[:8]
    az("containerapp", "delete", "-g", RG, "-n", APP, "--yes", parse=False, check=False)
    az("storage", "account", "delete", "-g", RG, "-n", sa, "--yes", parse=False, check=False)
    az("acr", "repository", "delete", "-n", ACR, "--repository", APP, "--yes", parse=False, check=False)
    print("removed gateway app, storage account and image; the agent was never changed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--cfg"); ap.add_argument("--version", default="0.1.0"); ap.add_argument("--destroy", action="store_true")
    a = ap.parse_args()
    if a.destroy: destroy(); sys.exit()
    out = deploy(json.load(open(a.cfg)), a.version); print(json.dumps(out, indent=2))
