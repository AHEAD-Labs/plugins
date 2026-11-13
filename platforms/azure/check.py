"""Live checks against the deployed agent gateway, using REAL Entra tokens and a real OBO exchange.
  uv run --with azure-identity --with azure-storage-blob python platforms/azure/check.py --cfg .gmo-demo/entra-agent.json
"""
import argparse, json, os, subprocess, sys, time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from platform_gateway import obo, revocations  # noqa

H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
CALL = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "tag.inspect", "arguments": {"request": "hello", "answer": ""}}}


def sh(*a): return subprocess.run(a, capture_output=True, text=True, check=True).stdout.strip()
def az_token(scope=None, resource=None):
    return sh("az", "account", "get-access-token", "--query", "accessToken", "-o", "tsv", *(["--scope", scope] if scope else ["--resource", resource]))


def main(cfg, endpoint, storage):
    out, post = [], lambda tok=None, body=CALL: httpx.post(endpoint, json=body, timeout=90,
                                                           headers={**H, **({"Authorization": f"Bearer {tok}"} if tok else {})})
    ok = lambda n, p, d="": out.append((n, bool(p), d))
    ok("health", httpx.get(endpoint.replace("/mcp", "/health"), timeout=30).status_code == 200)
    ok("no token -> 401", post().status_code == 401)
    ok("garbage token -> 401", post("not-a-jwt").status_code == 401)
    ok("Entra token for another API (Graph) -> 401", post(az_token(resource="https://graph.microsoft.com")).status_code == 401)
    # a valid token for the AGENT API, but minted by the Azure CLI app, which is not an allowed caller
    r = post(az_token(scope=cfg["agent_scope"]))
    ok("valid token from a caller that is NOT allowed -> 403", r.status_code == 403 and "caller_not_allowed" in r.text, r.text[:60])
    # the real path: user token for the MCP -> OBO -> agent token, calling as the MCP app
    secret = sh("aws", "ssm", "get-parameter", "--name", "/gmo/obo-client-secret", "--with-decryption", "--query", "Parameter.Value", "--output", "text", "--region", "us-east-1")
    user_tok = az_token(scope=f"api://{cfg['mcp_client_id']}/project-status:read")
    agent_tok = obo.exchange(user_tok, tenant=cfg["tenant_id"], client_id=cfg["mcp_client_id"], client_secret=secret, scope=cfg["agent_scope"])
    r = post(agent_tok)
    ok("OBO token -> agent answers through the gateway", r.status_code == 200 and "Which Azure subscription" in r.text, r.text[:70])
    ok("agent API key never reaches the caller", "x-api-key" not in r.text.lower())
    # suspension via the shared Azure Blob list (takes effect within the 5 s cache)
    os.environ["GMO_REVOCATIONS"] = f"azblob://{storage}/state/revocations.json"
    revocations.suspend("ahead.tag-compliance", reason="azure live check", by="check.py")
    time.sleep(8)
    r = post(agent_tok); ok("suspended -> 403 with a reason", r.status_code == 403 and "suspended" in r.text, r.text[:60])
    revocations.lift("ahead.tag-compliance"); time.sleep(8)
    ok("lifted -> 200 again", post(agent_tok).status_code == 200)
    for n, p, d in out: print(("PASS " if p else "FAIL ") + n, d if not p else "")
    return all(p for _, p, _ in out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--cfg", required=True); ap.add_argument("--storage", default="gmoagent6065c874")
    ap.add_argument("--endpoint", default="https://gmo-agent-gateway.gentlecoast-92cdab52.westus2.azurecontainerapps.io/mcp")
    a = ap.parse_args(); sys.exit(0 if main(json.load(open(a.cfg)), a.endpoint, a.storage) else 1)
