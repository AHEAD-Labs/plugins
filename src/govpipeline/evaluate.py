"""Golden evaluation of the built artifact over the stdio transport (incl. negative authz cases).
Cases live next to each capability's manifest (eval_cases.json)."""
import json, os, sys, time

from . import mcpclient as mc


async def _run(unpacked: str, audit_log: str, entry: str, cases: list[dict]) -> list[dict]:
    results = []
    for c in cases:
        env = {"PYTHONPATH": unpacked, "GMO_USER": c["user"], "GMO_AUDIT_LOG": audit_log}
        k, wins = int(c.get("runs", 1)), 0           # pass^k: the case counts only if ALL k runs pass
        for _ in range(k):
            async with mc.stdio_session(sys.executable, ["-m", entry], env) as s:
                ok, payload = await mc.call(s, c["tool"], **c["args"])
            passed = ok == c["expect_ok"]
            if passed and ok and "expect_count" in c:
                passed = len(payload[c["list_key"]]) == c["expect_count"]
            if passed and ok and "expect_field" in c:
                f, v = c["expect_field"]
                passed = payload.get(f) == v
            if passed and ok and c.get("required_facts"):
                passed = all(str(x) in json.dumps(payload) for x in c["required_facts"])
            wins += passed
        results.append({"id": c["id"], "passed": wins == k, "runs": k, "passes": wins})
    return results


SPEC_FIELDS = {"prompt": str, "expected_tool_path": list, "required_facts": list, "safety": str, "platform": str, "runs": int}
PLATFORMS = {"local", "aws", "azure", "mulesoft"}


def validate_spec(cases: list[dict], tools: list[str]) -> list[str]:
    """Optional eval-spec fields from the evaluation guide: prompt, expected tool path, required facts,
    safety behaviour, platform, and k for pass^k. If given, they must be well formed and name real tools."""
    errs = []
    for c in cases:
        for f, t in SPEC_FIELDS.items():
            if f in c and not isinstance(c[f], t):
                errs.append(f"{c.get('id')}: {f} must be {t.__name__}")
        if any(t not in tools for t in c.get("expected_tool_path", []) if isinstance(t, str)):
            errs.append(f"{c.get('id')}: expected_tool_path names a tool the manifest does not declare")
        if c.get("platform") and c["platform"] not in PLATFORMS:
            errs.append(f"{c.get('id')}: platform must be one of {sorted(PLATFORMS)}")
        if isinstance(c.get("runs"), int) and c["runs"] < 1:
            errs.append(f"{c.get('id')}: runs must be >= 1")
    return errs


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
