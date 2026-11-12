"""Pipeline: PR -> common checks -> platform checks -> approved artifact (registry)."""
import getpass, os, time, uuid

from . import build, checks, evaluate
from .manifest import Manifest, load
from .registry import Registry
from .util import git_ref, sha256_file, sha256_json
from .workspace import Workspace


class ReleaseRejected(Exception):
    def __init__(self, failed):
        super().__init__("release rejected: " + ", ".join(f"{c.stage}/{c.name} ({c.detail})" for c in failed))
        self.failed = failed


def release(manifest_path: str, ws: Workspace, *, run_tests: bool = True, dry_run: bool = False) -> dict:
    m: Manifest = load(manifest_path)
    reg = Registry(ws.registry)
    run_id = uuid.uuid4().hex[:12]
    log: list[checks.Check] = []

    # --- common checks (pre-build)
    log += checks.common_pre(m, reg, run_tests)
    _gate(log)

    # --- build the artifact, then derive everything else from the artifact itself
    wheel, wheel_sha = build.build_wheel(m, os.path.join(ws.work, run_id))
    unpacked = build.unpack(wheel, os.path.join(ws.work, run_id, "unpacked"))
    schema = build.schema_info(unpacked, m.python_package)
    log += checks.common_post(m, schema, schema["version"])
    _gate(log)

    # --- evaluation evidence
    base = os.path.dirname(os.path.abspath(manifest_path))
    entry = m.deployment("stdio").package.entrypoint
    evidence = evaluate.evaluate(unpacked, wheel_sha, os.path.join(ws.work, run_id), entry,
                                 os.path.join(base, "eval_cases.json"))
    log.append(checks.Check("common", "evaluation-passed", evidence["passed"],
                            f"{sum(c['passed'] for c in evidence['cases'])}/{len(evidence['cases'])} cases"))
    _gate(log)

    # --- platform checks
    log += checks.platform_checks(m, unpacked)
    _gate(log)

    # --- approve: immutable, signed release record
    rec = {
        "capability_id": m.capability_id, "name": m.name, "description": m.description,
        "owner": m.owner.model_dump(), "version": m.version, "audience": m.audience,
        "classification": m.classification, "tools": m.tools,
        "deployments": [d.model_dump(exclude_none=True) for d in m.deployments],
        "distribution": m.distribution,
        "artifact": {"filename": os.path.basename(wheel), "sha256": wheel_sha,
                     "size": os.path.getsize(wheel)},
        "schema_digest": schema["digest"],
        "evaluation": {"file": "evaluation.json", "sha256": sha256_json(evidence),
                       "suite": evidence["suite"], "passed": evidence["passed"]},
        "approval": {
            "approved_by": os.environ.get("GITHUB_ACTOR") or f"local-ci:{getpass.getuser()}",
            "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pipeline_run": os.environ.get("GITHUB_RUN_ID") or run_id,
            "source_ref": git_ref(os.path.dirname(os.path.abspath(manifest_path))),
            "pull_request": os.environ.get("GMO_PR", "n/a (local run)"),
            "manifest_sha256": sha256_file(manifest_path),
            "skill_sha256": sha256_file(os.path.join(base, "SKILL.md")),
            "checks": checks.as_dicts(log),
        },
        "status": "approved",
    }
    if dry_run:  # PR mode: every check ran, nothing is written to the registry
        return rec
    reg.publish(rec, wheel, {"evaluation.json": evidence, "checks.json": checks.as_dicts(log)},
                files=[os.path.join(base, "SKILL.md"), manifest_path])
    return reg.load(m.capability_id, m.version)


def _gate(log):
    failed = [c for c in log if not c.passed]
    if failed:
        raise ReleaseRejected(failed)
