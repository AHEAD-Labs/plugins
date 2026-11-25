"""Deployment readiness: one result shape for every agent, a consolidated report,
and a policy approval bound to the exact plan, target and user.

Pure functions, no network. The agents run on their own platforms; this module
defines what they must return and how the answers are combined and approved.
"""
import time

from .util import sha256_json

STATUSES = ("ok", "denied", "missing", "failed")
# Agents the readiness workflow depends on. All are mandatory.
AGENTS = ("requirements", "feasibility", "governance")
APPROVAL_TTL_S = 900


class SchemaError(ValueError):
    pass


def validate_result(r: dict) -> dict:
    """An agent result: {agent, status, correlation_id, data, issues[]}. Strict."""
    if not isinstance(r, dict):
        raise SchemaError("result must be an object")
    missing = [k for k in ("agent", "status", "correlation_id", "data", "issues") if k not in r]
    if missing:
        raise SchemaError(f"missing fields: {missing}")
    if r["agent"] not in AGENTS:
        raise SchemaError(f"unknown agent {r['agent']!r}")
    if r["status"] not in STATUSES:
        raise SchemaError(f"status must be one of {STATUSES}")
    if not isinstance(r["issues"], list) or not isinstance(r["data"], dict):
        raise SchemaError("issues must be a list and data an object")
    if r["status"] != "ok" and not r["issues"]:
        raise SchemaError("a non-ok result must say why in issues")
    return r


def consolidate(results: list[dict], correlation_id: str) -> dict:
    """Combine agent results into one readiness report. A result that is absent,
    malformed or not ok blocks the deployment; nothing is silently dropped."""
    by_agent, problems = {}, []
    for r in results:
        try:
            validate_result(r)
            by_agent[r["agent"]] = r
        except SchemaError as e:
            problems.append({"agent": (r or {}).get("agent", "unknown") if isinstance(r, dict) else "unknown",
                             "status": "failed", "issues": [f"invalid result: {e}"]})
    blockers = list(problems)
    for a in AGENTS:
        r = by_agent.get(a)
        if r is None and not any(p["agent"] == a for p in problems):
            blockers.append({"agent": a, "status": "missing", "issues": ["no result returned"]})
        elif r is not None and r["status"] != "ok":
            blockers.append({"agent": a, "status": r["status"], "issues": r["issues"]})
    ok = not blockers
    return {
        "correlation_id": correlation_id,
        "ready": ok,
        "blockers": blockers,
        "sections": {a: by_agent[a]["data"] for a in AGENTS if a in by_agent and by_agent[a]["status"] == "ok"},
        "sources": {a: by_agent[a]["correlation_id"] for a in by_agent},
    }


def plan_hash(plan: dict) -> str:
    """Digest of the exact configuration that will be applied (target included)."""
    return sha256_json(plan)


def decide_approval(report: dict, *, plan: dict, target: str, user: str, roles: list[str],
                    policy: dict, now: float | None = None) -> dict:
    """Policy approval. Allowed only if the report is ready, the target is allowed,
    and the user holds the deploy role. The token binds plan, target and user."""
    now = time.time() if now is None else now
    reasons = []
    if not report.get("ready"):
        reasons.append("readiness report has blockers")
    if plan.get("target") != target:
        reasons.append("plan target does not match requested target")
    if target not in policy.get("allowed_targets", []):
        reasons.append(f"target {target!r} not allowed")
    if policy.get("deploy_role") not in roles:
        reasons.append("user lacks the deploy role")
    ph = plan_hash(plan)
    decision = {"allowed": not reasons, "reasons": reasons, "policy_version": policy.get("version"),
                "plan_hash": ph, "target": target, "user": user, "correlation_id": report.get("correlation_id")}
    if decision["allowed"]:
        decision["expires_at"] = now + APPROVAL_TTL_S
        decision["idempotency_key"] = sha256_json({"plan": ph, "target": target})
    return decision


def verify_approval(decision: dict, *, plan: dict, target: str, user: str, now: float | None = None) -> None:
    """Called by the deploy step. Raises unless the approval matches what is about to run."""
    now = time.time() if now is None else now
    if not decision.get("allowed"):
        raise PermissionError("not approved")
    if now > decision["expires_at"]:
        raise PermissionError("approval expired")
    if decision["plan_hash"] != plan_hash(plan) or decision["target"] != target or decision["user"] != user:
        raise PermissionError("approval does not match this plan, target or user")


class DeployLedger:
    """Idempotency: the first apply for a key runs; a retry returns the earlier outcome.
    In production this is a conditional write in a durable store (e.g. DynamoDB)."""

    def __init__(self):
        self._done: dict[str, dict] = {}

    def apply(self, decision: dict, run):
        key = decision["idempotency_key"]
        if key in self._done:
            return {**self._done[key], "replayed": True}
        out = run()
        self._done[key] = out
        return {**out, "replayed": False}
