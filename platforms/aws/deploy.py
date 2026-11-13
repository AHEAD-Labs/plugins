"""Deploy an approved capability release to AWS: Lambda + API Gateway (HTTP API).

  uv run --extra aws python platforms/aws/deploy.py --registry <dir> --cap ahead.project-status --version 0.1.0

Idempotent. Creates/updates only gmo-* resources. Runs the platform selfcheck against the LIVE
endpoint and exits non-zero if it fails.
"""
import argparse, asyncio, base64, hashlib, json, os, secrets, sys, time

sys.path.insert(0, os.path.dirname(__file__))
from botocore.exceptions import ClientError

from common import *  # noqa
import package

SSM_SECRET = "/gmo/idp-secret"


def idp_secret(s) -> str:
    ssm = s.client("ssm")
    try:
        return ssm.get_parameter(Name=SSM_SECRET, WithDecryption=True)["Parameter"]["Value"]
    except ClientError:
        v = secrets.token_urlsafe(48)
        ssm.put_parameter(Name=SSM_SECRET, Value=v, Type="SecureString", Tags=TAGS)
        return v


def wait_ready(lam, name):
    for _ in range(60):
        c = lam.get_function_configuration(FunctionName=name)
        if c.get("State") == "Active" and c.get("LastUpdateStatus") in ("Successful", None):
            return
        time.sleep(2)
    raise TimeoutError("lambda not ready")


def deploy(s, registry_dir, cap, ver, workdir, entra=None):
    acct = account(s); lam, apigw, s3 = s.client("lambda"), s.client("apigatewayv2"), s.client("s3")
    zpath, sha, rec = package.build(registry_dir, cap, ver, workdir)
    key = f"artifacts/{cap}-{ver}-{sha[:16]}.zip"
    s3.upload_file(zpath, bucket(acct), key, ExtraArgs={"Tagging": "project=governed-mcp-onboarding"})
    role = f"arn:aws:iam::{acct}:role/{LAMBDA_ROLE}"
    env = {"GMO_BACKEND_URL": "inprocess", "CAPABILITY_VERSION": ver, "GMO_REVOCATION_TTL": "5",
           "GMO_REVOCATIONS": f"s3://{bucket(acct)}/revocations.json", "GMO_IDP_SECRET": idp_secret(s),
           "GMO_REMOTE_ENDPOINT": "https://pending.invalid/mcp"}
    if entra:  # real identity: the function validates Entra tokens too (defence in depth)
        env.update(GMO_ENTRA_TENANT=entra["tenant_id"], GMO_ENTRA_AUDIENCE=entra["api_client_id"])
    code = {"S3Bucket": bucket(acct), "S3Key": key}
    try:
        old = lam.get_function_configuration(FunctionName=FUNCTION)
        prev = old.get("Environment", {}).get("Variables", {})
        env["GMO_REMOTE_ENDPOINT"] = prev.get("GMO_REMOTE_ENDPOINT", env["GMO_REMOTE_ENDPOINT"])
        lam.update_function_code(FunctionName=FUNCTION, Architectures=["arm64"], **code); wait_ready(lam, FUNCTION)
        lam.update_function_configuration(FunctionName=FUNCTION, Environment={"Variables": env}); wait_ready(lam, FUNCTION)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException": raise
        for _ in range(10):  # a new IAM role can take a few seconds to become assumable
            try:
                lam.create_function(FunctionName=FUNCTION, Runtime="python3.12", Role=role, Code=code,
                    Handler="platform_gateway.aws_handler.handler", Architectures=["arm64"], Timeout=15,
                    MemorySize=512, Environment={"Variables": env}, Tags=PROJECT_TAG); break
            except ClientError as ce:
                if "cannot be assumed" not in str(ce): raise
                time.sleep(4)
        wait_ready(lam, FUNCTION)
    fn_arn = lam.get_function_configuration(FunctionName=FUNCTION)["FunctionArn"]

    api = next((a for a in apigw.get_apis()["Items"] if a["Name"] == API_NAME), None)
    if not api:
        api = apigw.create_api(Name=API_NAME, ProtocolType="HTTP", Target=fn_arn, Tags=PROJECT_TAG)
        try:
            lam.add_permission(FunctionName=FUNCTION, StatementId="apigw-invoke", Action="lambda:InvokeFunction",
                               Principal="apigateway.amazonaws.com",
                               SourceArn=f"arn:aws:execute-api:{REGION}:{acct}:{api['ApiId']}/*/*")
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceConflictException": raise
    # traffic limits at the native gateway (R1)
    apigw.update_stage(ApiId=api["ApiId"], StageName="$default",
                       DefaultRouteSettings={"ThrottlingRateLimit": 10.0, "ThrottlingBurstLimit": 20})
    if entra:  # native gateway check: API Gateway validates issuer/audience/scope BEFORE the function runs
        auth = next((a for a in apigw.get_authorizers(ApiId=api["ApiId"])["Items"] if a["Name"] == "gmo-entra"), None)
        cfg = {"Audience": [entra["api_client_id"]], "Issuer": entra["issuer"]}
        if auth:
            apigw.update_authorizer(ApiId=api["ApiId"], AuthorizerId=auth["AuthorizerId"], JwtConfiguration=cfg)
        else:
            auth = apigw.create_authorizer(ApiId=api["ApiId"], AuthorizerType="JWT", Name="gmo-entra",
                IdentitySource=["$request.header.Authorization"], JwtConfiguration=cfg)
        integ = apigw.get_integrations(ApiId=api["ApiId"])["Items"][0]["IntegrationId"]
        route = next((r for r in apigw.get_routes(ApiId=api["ApiId"])["Items"] if r["RouteKey"] == "ANY /mcp"), None)
        kw = dict(ApiId=api["ApiId"], Target=f"integrations/{integ}", AuthorizationType="JWT",
                  AuthorizerId=auth["AuthorizerId"], AuthorizationScopes=["project-status:read"])
        if route: apigw.update_route(RouteId=route["RouteId"], **kw)
        else: apigw.create_route(RouteKey="ANY /mcp", **kw)
    endpoint = api["ApiEndpoint"].rstrip("/") + "/mcp"
    if env["GMO_REMOTE_ENDPOINT"] != endpoint:
        env["GMO_REMOTE_ENDPOINT"] = endpoint
        lam.update_function_configuration(FunctionName=FUNCTION, Environment={"Variables": env}); wait_ready(lam, FUNCTION)
    want = base64.b64encode(hashlib.sha256(open(zpath, "rb").read()).digest()).decode()
    live = lam.get_function_configuration(FunctionName=FUNCTION)["CodeSha256"]
    if want != live:
        raise RuntimeError(f"deployed code hash {live} != approved artifact {want}")
    return {"platform": "aws", "capability_id": cap, "code_sha256_verified": True,
            **({"entra": {"issuer": entra["issuer"], "audience": entra["api_audience"], "scope": entra["scope"],
                          "codex_client_id": entra["codex_client_id"]}} if entra else {}), "version": ver, "endpoint": endpoint,
            "function": FUNCTION, "api_id": api["ApiId"], "artifact_sha256": sha, "account": acct,
            "region": REGION, "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


async def selfcheck(endpoint, secret):
    """Live platform check: gateway must reject bad tokens, accept a good one, enforce per-user access."""
    os.environ["GMO_IDP_SECRET"] = secret
    from govpipeline import mcpclient as mc
    from platform_gateway import idp
    out = []
    ok = lambda n, p, d="": out.append({"check": n, "passed": bool(p), "detail": d})
    ok("no token -> 401", await mc.http_status(endpoint, None) == 401)
    ok("wrong audience -> 401", await mc.http_status(endpoint, idp.mint("alice", "https://other.example/mcp")) == 401)
    ok("wrong scope -> 401", await mc.http_status(endpoint, idp.mint("alice", endpoint, scope="x:y")) == 401)
    ok("garbage token -> 401", await mc.http_status(endpoint, "not-a-jwt") == 401)
    async with mc.http_session(endpoint, idp.mint("alice", endpoint)) as sess:
        good, data = await mc.call(sess, "list_projects")
        ok("alice lists projects", good and len(data.get("projects", data)) == 4, str(data)[:80])
    async with mc.http_session(endpoint, idp.mint("bob", endpoint)) as sess:
        good, data = await mc.call(sess, "get_project_status", project_id="PRJ-002")
        ok("bob denied PRJ-002", not good)
    return out


async def selfcheck_ci(endpoint):
    """CI has no signed-in user, so only prove what a caller WITHOUT a valid Entra token sees."""
    from govpipeline import mcpclient as mc
    from platform_gateway import idp
    os.environ["GMO_IDP_SECRET"] = "x" * 32
    out = []
    ok = lambda n, p, d="": out.append({"check": n, "passed": bool(p), "detail": d})
    ok("no token -> 401", await mc.http_status(endpoint, None) == 401)
    ok("garbage token -> 401", await mc.http_status(endpoint, "not-a-jwt") == 401)
    ok("demo (HS256) token -> 401", await mc.http_status(endpoint, idp.mint("alice", endpoint)) == 401)
    return out


def az_token(scope=None, resource=None):
    import subprocess
    a = ["az", "account", "get-access-token", "--query", "accessToken", "-o", "tsv"]
    a += ["--scope", scope] if scope else ["--resource", resource]
    return subprocess.run(a, capture_output=True, text=True, check=True).stdout.strip()


async def selfcheck_entra(endpoint, entra):
    """Live check with REAL Entra tokens, including tokens that must be rejected."""
    from govpipeline import mcpclient as mc
    from platform_gateway import idp
    os.environ["GMO_IDP_SECRET"] = "x" * 32
    good = az_token(scope=entra["scope"])
    out = []
    ok = lambda n, p, d="": out.append({"check": n, "passed": bool(p), "detail": d})
    ok("no token -> 401", await mc.http_status(endpoint, None) == 401)
    ok("garbage token -> 401", await mc.http_status(endpoint, "not-a-jwt") == 401)
    ok("demo (HS256) token no longer accepted -> 401", await mc.http_status(endpoint, idp.mint("alice", endpoint)) == 401)
    ok("Entra token for another API (Graph) -> 401", await mc.http_status(endpoint, az_token(resource="https://graph.microsoft.com")) == 401)
    ok("valid Entra token (you) -> 200", await mc.http_status(endpoint, good) == 200)
    async with mc.http_session(endpoint, good) as sess:
        okc, data = await mc.call(sess, "list_projects")
        ok("tool call runs as your Entra identity", okc, str(data)[:90])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--profile"); ap.add_argument("--registry", required=True)
    ap.add_argument("--cap", default="ahead.project-status"); ap.add_argument("--version", required=True)
    ap.add_argument("--work", default=".gmo/aws-work"); ap.add_argument("--state-out"); ap.add_argument("--ci", action="store_true", help="no signed-in user: negative checks only"); ap.add_argument("--entra", help="json from platforms/entra/setup.py")
    a = ap.parse_args(); s = session(a.profile)
    if a.version == "latest":
        from govpipeline.registry import Registry
        a.version = Registry(a.registry).versions(a.cap)[-1]
    ent = json.load(open(a.entra)) if a.entra else None
    st = deploy(s, a.registry, a.cap, a.version, a.work, ent); print(json.dumps(st, indent=2))
    time.sleep(8)
    res = asyncio.run(selfcheck_ci(st["endpoint"]) if a.ci else selfcheck_entra(st["endpoint"], ent) if ent else selfcheck(st["endpoint"], idp_secret(s)))
    for r in res: print(("PASS " if r["passed"] else "FAIL ") + r["check"], r["detail"])
    if a.state_out:
        os.makedirs(os.path.dirname(a.state_out), exist_ok=True); json.dump({**st, "selfcheck": res}, open(a.state_out, "w"), indent=2)
    sys.exit(0 if all(r["passed"] for r in res) else 1)
