"""Targeted suspension. Checked by the gateway on EVERY request, so it takes effect
immediately and independently of catalogue state."""
import json, os, time


def _path() -> str:
    return os.environ.get("GMO_REVOCATIONS", "revocations.json")


def _load() -> list[dict]:
    try:
        with open(_path()) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def _save(entries: list[dict]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(_path())), exist_ok=True)
    tmp = _path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(entries, f, indent=2)
    os.replace(tmp, _path())


def suspend(capability_id: str, *, version: str | None = None, user: str | None = None,
            reason: str, by: str) -> dict:
    """Scope: capability (all versions), capability+version, and/or a single user."""
    entry = {"capability_id": capability_id, "version": version, "user": user, "reason": reason,
             "by": by, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _save(_load() + [entry])
    return entry


def lift(capability_id: str, *, version: str | None = None, user: str | None = None) -> int:
    entries = _load()
    keep = [e for e in entries if not (e["capability_id"] == capability_id
            and e["version"] == version and e["user"] == user)]
    _save(keep)
    return len(entries) - len(keep)


def check(capability_id: str, version: str, user: str | None) -> str | None:
    """Return the reason if blocked, else None."""
    for e in _load():
        if e["capability_id"] != capability_id: continue
        if e["version"] not in (None, version): continue
        if e["user"] not in (None, user): continue
        return e["reason"]
    return None


def active() -> list[dict]:
    return _load()
