"""The control contract: the minimum every platform signs up to in place of a central gateway (D1, R1).

Each platform has platforms/<name>/contract.yaml. Every control needs a named place where it is enforced and
an owner; a blank owner is where an audit finding lands. Gaps are allowed, but they must be written down.
"""
import glob, os

import yaml

CONTROLS = ["token_validation", "authorization", "audit_event", "suspension", "rate_limit", "cost_limit", "telemetry"]
STATUS = {"enforced", "planned", "gap"}
MAX_SUSPENSION_SECONDS = 60   # policy: a suspension must take effect within a minute
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def validate(path: str) -> list[str]:
    c = yaml.safe_load(open(path)) or {}
    name, errs = c.get("platform") or os.path.basename(os.path.dirname(path)), []
    if not c.get("platform_owner"):
        errs.append(f"{name}: platform_owner is blank")
    for ctl in CONTROLS:
        e = (c.get("controls") or {}).get(ctl)
        if not e:
            errs.append(f"{name}: control '{ctl}' is not declared"); continue
        if e.get("status") not in STATUS:
            errs.append(f"{name}.{ctl}: status must be one of {sorted(STATUS)}")
        if not e.get("owner"):
            errs.append(f"{name}.{ctl}: owner is blank")
        if e.get("status") == "enforced" and not (e.get("enforced_by") and e.get("evidence")):
            errs.append(f"{name}.{ctl}: 'enforced' needs enforced_by and evidence")
        if e.get("status") == "gap" and not e.get("note"):
            errs.append(f"{name}.{ctl}: a gap must say what is missing (note)")
    s = (c.get("controls") or {}).get("suspension") or {}
    if s.get("status") == "enforced" and not (isinstance(s.get("max_seconds"), int) and s["max_seconds"] <= MAX_SUSPENSION_SECONDS):
        errs.append(f"{name}.suspension: max_seconds must be an integer <= {MAX_SUSPENSION_SECONDS}")
    for ev in [e.get("evidence") for e in (c.get("controls") or {}).values() if e.get("evidence")]:
        if not os.path.exists(os.path.join(REPO, ev.split("::")[0])):
            errs.append(f"{name}: evidence file not found: {ev}")
    return errs


def check_all() -> tuple[list[dict], list[str]]:
    rows, errs = [], []
    for p in sorted(glob.glob(os.path.join(REPO, "platforms", "*", "contract.yaml"))):
        errs += validate(p)
        c = yaml.safe_load(open(p))
        rows.append({"platform": c.get("platform"), **{k: (c["controls"].get(k) or {}).get("status", "missing") for k in CONTROLS}})
    return rows, errs
