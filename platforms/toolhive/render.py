"""Render the ToolHive resources for one signed release (kind mcp-image). Nothing is applied here.

  uv run python platforms/toolhive/render.py --registry .gmo/registry --cap ahead.project-status --version latest \
      --entra .gmo/entra.json --namespace toolhive-system [--otel-endpoint host:4318] --out out.yaml

Resources (API toolhive.stacklok.dev/v1beta1, field names read from the CRDs of operator v0.53.0):
  MCPExternalAuthConfig  embeddedAuthServer: ChatGPT registers with it (CIMD/DCR), the user signs in at Entra
  MCPOIDCConfig          the proxy validates the tokens that auth server issues
  MCPAuthzConfig         Cedar, default-deny: one permit per tool and allowed Entra app role
  MCPTelemetryConfig     only when an OTLP endpoint is given
  MCPServer              the image pinned by digest, behind the proxy
Secrets are referenced, never written: see platforms/toolhive/README.md.

NOT YET VERIFIED ON A CLUSTER: whether MCPServer.spec.image accepts name@sha256:..., the callback path of the
embedded auth server, how roles reach Cedar when the embedded server is in front, and the obo type.
"""
import argparse, json, os, sys
from urllib.parse import urlparse

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
API = "toolhive.stacklok.dev/v1beta1"
LABELS = {"app.kubernetes.io/part-of": "governed-mcp-onboarding", "project": "governed-mcp-onboarding"}


def _name(cap: str) -> str:
    return "gmo-" + cap.split(".")[-1]


def cedar_policies(tools: list[str], roles: list[str]) -> list[str]:
    q = lambda v: json.dumps(v)  # Cedar string literals use the same double-quote escaping
    return [f'permit(principal, action in [Action::"call_tool", Action::"list_tools"], resource == Tool::{q(t)}) '
            f'when {{ principal.claim_roles.contains({q(r)}) }};' for t in sorted(tools) for r in sorted(roles)]


def render(rec: dict, entra: dict, namespace: str = "toolhive-system", otel_endpoint: str | None = None,
           callback_path: str = "/oauth/callback") -> list[dict]:
    d = rec["deployments"][0]
    if rec.get("kind") != "mcp-image" or d.get("platform") != "toolhive":
        raise ValueError(f"{rec['capability_id']} is not an mcp-image for toolhive")
    n, host = _name(rec["capability_id"]), urlparse(d["endpoint"])
    base = f"{host.scheme}://{host.netloc}"
    meta = lambda name, kind: {"name": name, "namespace": namespace, "labels": LABELS,
                               "annotations": {"gmo/capability": rec["capability_id"], "gmo/version": rec["version"],
                                               "gmo/release-signature": rec["signature"]}}
    docs = [
        {"apiVersion": API, "kind": "MCPExternalAuthConfig", "metadata": meta(f"{n}-auth", "auth"),
         "spec": {"type": "embeddedAuthServer", "embeddedAuthServer": {
             "issuer": base,
             "upstreamProviders": [{"name": "entra", "type": "oidc", "oidcConfig": {
                 "issuerUrl": entra["issuer"], "clientId": entra["toolhive_client_id"],
                 "clientSecretRef": {"name": f"{n}-auth", "key": "entra-client-secret"},
                 "redirectUri": base + callback_path, "scopes": ["openid", "profile", "email"]}}],
             "primaryUpstreamProvider": "entra",
             "hmacSecretRefs": [{"name": f"{n}-auth", "key": "hmac"}],
             "signingKeySecretRefs": [{"name": f"{n}-auth", "key": "signing-key"}],
             "cimd": {"enabled": True}}}},
        {"apiVersion": API, "kind": "MCPOIDCConfig", "metadata": meta(f"{n}-oidc", "oidc"),
         "spec": {"type": "inline", "inline": {"issuer": base}}},
        {"apiVersion": API, "kind": "MCPAuthzConfig", "metadata": meta(f"{n}-authz", "authz"),
         "spec": {"type": "cedarv1", "config": {"policies": cedar_policies(rec["tools"], d["allowed_roles"]),
                                                "entities_json": "[]"}}},
    ]
    server = {"image": d["image"], "transport": "streamable-http", "proxyPort": 8080, "mcpPort": d["mcp_port"],
              "authServerRef": {"kind": "MCPExternalAuthConfig", "name": f"{n}-auth"},
              "oidcConfigRef": {"name": f"{n}-oidc", "audience": d["auth"]["audience"], "resourceUrl": d["endpoint"],
                                "scopes": d["auth"]["scopes"]},
              "authzConfigRef": {"name": f"{n}-authz"},
              "resources": {"limits": {"cpu": "500m", "memory": "512Mi"}, "requests": {"cpu": "100m", "memory": "128Mi"}}}
    if d.get("obo_scope"):  # experimental: the CRD lists an obo type; not confirmed to work without Stacklok Enterprise
        docs.append({"apiVersion": API, "kind": "MCPExternalAuthConfig", "metadata": meta(f"{n}-obo", "obo"),
                     "spec": {"type": "obo", "obo": {"tenantId": entra["tenant_id"], "clientId": entra["toolhive_client_id"],
                              "clientSecretRef": {"name": f"{n}-auth", "key": "entra-client-secret"}, "scopes": [d["obo_scope"]]}}})
        server["externalAuthConfigRef"] = {"name": f"{n}-obo"}
    if otel_endpoint:
        docs.append({"apiVersion": API, "kind": "MCPTelemetryConfig", "metadata": meta(f"{n}-otel", "otel"),
                     "spec": {"openTelemetry": {"enabled": True, "endpoint": otel_endpoint, "tracing": {"enabled": True,
                              "samplingRate": "0.05"}, "metrics": {"enabled": True}}}})
        server["telemetryConfigRef"] = {"name": f"{n}-otel", "serviceName": n}
    docs.append({"apiVersion": API, "kind": "MCPServer", "metadata": meta(n, "server"), "spec": server})
    return docs


def dump(docs: list[dict]) -> str:
    return yaml.safe_dump_all(docs, sort_keys=False)


if __name__ == "__main__":
    from govpipeline.registry import Registry
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True); ap.add_argument("--cap", required=True); ap.add_argument("--version", default="latest")
    ap.add_argument("--entra", required=True, help="json with issuer, tenant_id, toolhive_client_id")
    ap.add_argument("--namespace", default="toolhive-system"); ap.add_argument("--otel-endpoint"); ap.add_argument("--out")
    a = ap.parse_args()
    reg = Registry(a.registry)
    ver = reg.versions(a.cap)[-1] if a.version == "latest" else a.version
    text = dump(render(reg.load(a.cap, ver), json.load(open(a.entra)), a.namespace, a.otel_endpoint))
    open(a.out, "w").write(text) if a.out else print(text)
