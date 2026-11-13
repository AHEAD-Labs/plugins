"""Golden evaluation of the built artifact over the stdio transport (incl. negative authz cases).
Cases live next to each capability's manifest (eval_cases.json)."""
import json, os, sys, time

from . import mcpclient as mc


async def _run(unpacked: str, audit_log: str, entry: str, cases: list[dict]) -> list[dict]:
    results = []
    for c in cases:
        env = {"PYTHONPATH": unpacked, "GMO_USER": c["user"], "GMO_AUDIT_LOG": audit_log}
        async with mc.stdio_session(sys.executable, ["-m", entry], env) as s:
            ok, payload = await mc.call(s, c["tool"], **c["args"])
        passed = ok == c["expect_ok"]
        if passed and ok and "expect_count" in c:
            passed = len(payload[c["list_key"]]) == c["expect_count"]
        if passed and ok and "expect_field" in c:
            k, v = c["expect_field"]
            passed = payload.get(k) == v
        results.append({"id": c["id"], "passed": passed})
    return results


def evaluate(unpacked: str, wheel_sha256: str, workdir: str, entry: str, cases_path: str) -> dict:
    cases = json.load(open(cases_path))
    results = mc.run(_run(unpacked, os.path.join(workdir, "eval-audit.jsonl"), entry, cases))
    return {"suite": "golden/v1", "transport": "stdio", "artifact_sha256": wheel_sha256,
            "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cases": results, "passed": all(r["passed"] for r in results)}


def contract(tools: list[str], artifact_ref: str, cases_path: str) -> dict:
    """Agent evidence before it is deployed: the eval cases only name declared tools and every tool has one.
    Behaviour against the live agent is checked after deployment (platforms/azure/check.py)."""
    cases = json.load(open(cases_path))
    results = [{"id": c["id"], "passed": c["tool"] in tools} for c in cases]
    results += [{"id": f"covers:{t}", "passed": any(c["tool"] == t for c in cases)} for t in tools]
    return {"suite": "agent-contract/v1", "transport": "none (checked before deployment)", "artifact_sha256": artifact_ref,
            "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cases": results, "passed": all(r["passed"] for r in results)}
