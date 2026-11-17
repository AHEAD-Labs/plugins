"""Pipeline: PR -> common checks -> platform checks -> approved artifact (registry)."""
import getpass, json, os, time, uuid

from . import build, checks, evaluate
from .manifest import Manifest, load
from .registry import Registry
from .util import git_ref, sha256_file, sha256_json, sha256_tree
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

    base = os.path.dirname(os.path.abspath(manifest_path))
    wheel, extra_files, skill_file = None, [], os.path.join(base, "SKILL.md")
    if m.kind == "external":
        d = m.deployments[0]
        snapshot = json.load(open(os.path.join(base, "tools.json")))
        pf = checks.plugin_files(base)
        skill_file = pf["skills"][0] if pf["skills"] else skill_file
        artifact = {"type": "external-endpoint", "endpoint": d.endpoint, "built_by_us": False,
                    "sha256": sha256_json(snapshot), "plugin_sha256": sha256_tree(pf["root"]) if os.path.isdir(pf["root"]) else ""}
        schema = {"digest": sha256_json(sorted(snapshot, key=lambda t: t.get("name", "")))}
        log += checks.common_agent(m)
        _gate(log)
        evidence = evaluate.contract(m.tools, d.endpoint, os.path.join(base, "eval_cases.json"), suite="external-contract/v1")
        log.append(checks.Check("common", "evaluation-passed", evidence["passed"],
                                f"{sum(c['passed'] for c in evidence['cases'])}/{len(evidence['cases'])} contract cases"))
        _gate(log)
        log += checks.external_checks(m, base, snapshot)
        _gate(log)
        extra_files = [pf["root"], os.path.join(base, "tools.json")]
    elif m.kind == "agent":
        # no wheel: the artifact is the container image, pinned by digest in the signed record
        d = m.deployments[0]
        artifact = {"type": "container-image", "image": d.image, "gateway_image": d.gateway_image,
                    "sha256": d.image.split("@sha256:")[-1]}
        schema = {"digest": sha_tools(m.tools)}
        log += checks.common_agent(m)
        _gate(log)
        evidence = evaluate.contract(m.tools, d.image, os.path.join(base, "eval_cases.json"))
        log.append(checks.Check("common", "evaluation-passed", evidence["passed"],
                                f"{sum(c['passed'] for c in evidence['cases'])}/{len(evidence['cases'])} contract cases"))
        _gate(log)
        log += checks.agent_checks(m)
        _gate(log)
    else:
        # --- build the artifact, then derive everything else from the artifact itself
        wheel, wheel_sha = build.build_wheel(m, os.path.join(ws.work, run_id))
        unpacked = build.unpack(wheel, os.path.join(ws.work, run_id, "unpacked"))
        schema = build.schema_info(unpacked, m.python_package)
        log += checks.common_post(m, schema, schema["version"])
        _gate(log)

        # --- evaluation evidence
        entry = m.deployment("stdio").package.entrypoint
        spec_errs = evaluate.validate_spec(json.load(open(os.path.join(base, "eval_cases.json"))), m.tools)
        log.append(checks.Check("common", "eval-spec-valid", not spec_errs, "; ".join(spec_errs) or "fields well formed"))
        _gate(log)
        evidence = evaluate.evaluate(unpacked, wheel_sha, os.path.join(ws.work, run_id), entry,
                                     os.path.join(base, "eval_cases.json"))
        log.append(checks.Check("common", "evaluation-passed", evidence["passed"],
                                f"{sum(c['passed'] for c in evidence['cases'])}/{len(evidence['cases'])} cases"))
        _gate(log)

        # --- platform checks
        log += checks.platform_checks(m, unpacked)
        _gate(log)
        artifact = {"filename": os.path.basename(wheel), "sha256": wheel_sha, "size": os.path.getsize(wheel)}

    # --- approve: immutable, signed release record
    rec = {
        "capability_id": m.capability_id, "kind": m.kind, "name": m.name, "description": m.description,
        "owner": m.owner.model_dump(), "version": m.version, "audience": m.audience,
        "classification": m.classification, "tools": m.tools,
        "deployments": [d.model_dump(exclude_none=True) for d in m.deployments],
        "distribution": m.distribution,
        "artifact": artifact,
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
            "skill_sha256": sha256_file(skill_file),
            "checks": checks.as_dicts(log),
        },
        "status": "approved",
    }
    if dry_run:  # PR mode: every check ran, nothing is written to the registry
        return rec
    reg.publish(rec, wheel, {"evaluation.json": evidence, "checks.json": checks.as_dicts(log)},
                files=[skill_file, manifest_path, *extra_files])
    return reg.load(m.capability_id, m.version)


def _gate(log):
    failed = [c for c in log if not c.passed]
    if failed:
        raise ReleaseRejected(failed)


def sha_tools(tools: list[str]) -> str:
    return sha256_json(sorted(tools))
