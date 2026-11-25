"""Terraform plan and apply, bound to a policy approval.

plan() saves the plan file and returns a plan record whose digest covers the
saved file. apply() runs only that exact file, and only after the approval
matches the plan, target and user. Run it from a platform-owned runner, not
from the client.
"""
import os, subprocess

from . import readiness
from .util import sha256_file


def _tf(args: list[str], cwd: str, env: dict | None = None):
    r = subprocess.run(["terraform", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    if r.returncode != 0:
        raise RuntimeError(f"terraform {args[0]} failed: {r.stderr.strip()[-400:]}")
    return r.stdout


def plan(workdir: str, *, target: str, variables: dict | None = None, run=_tf) -> dict:
    """Return the plan record to put in front of the approval policy."""
    variables = variables or {}
    run(["init", "-input=false", "-no-color"], workdir)
    args = ["plan", "-input=false", "-no-color", "-out=plan.bin"] + [f"-var={k}={v}" for k, v in sorted(variables.items())]
    run(args, workdir)
    return {"target": target, "module": os.path.basename(os.path.abspath(workdir)),
            "vars": variables, "plan_sha256": sha256_file(os.path.join(workdir, "plan.bin"))}


def apply(workdir: str, decision: dict, record: dict, *, user: str, ledger: readiness.DeployLedger, run=_tf) -> dict:
    """Apply the approved plan file once. A retry returns the earlier outcome."""
    readiness.verify_approval(decision, plan=record, target=record["target"], user=user)
    path = os.path.join(workdir, "plan.bin")
    if not os.path.exists(path) or sha256_file(path) != record["plan_sha256"]:
        raise PermissionError("plan file changed since it was approved")

    def go():
        run(["apply", "-input=false", "-no-color", "plan.bin"], workdir)
        return {"status": "applied", "plan_sha256": record["plan_sha256"], "target": record["target"],
                "correlation_id": decision.get("correlation_id")}
    return ledger.apply(decision, go)
