"""Targeted suspension. Checked by the gateway on EVERY request, so it takes effect
immediately and independently of catalogue state."""
import json, os, time

# Storage is a local file (default) or an S3 object ("s3://bucket/key") so every gateway
# instance sees the same list. GMO_REVOCATION_TTL (seconds, default 0 = always fresh) bounds how
# stale a cached copy may be: that is the maximum delay before a suspension takes effect.
_cache: dict = {"at": 0.0, "entries": []}


def _path() -> str:
    return os.environ.get("GMO_REVOCATIONS", "revocations.json")


def _s3():
    import boto3  # present in the Lambda runtime; only needed for s3:// storage
    return boto3.client("s3")


def _load() -> list[dict]:
    path, ttl = _path(), float(os.environ.get("GMO_REVOCATION_TTL", "0"))
    if path.startswith("s3://"):
        if ttl and time.time() - _cache["at"] < ttl:
            return _cache["entries"]
        bucket, key = path[5:].split("/", 1)
        try:
            entries = json.loads(_s3().get_object(Bucket=bucket, Key=key)["Body"].read())
        except Exception:  # fail closed: if the list cannot be read, treat everything as suspended
            raise RuntimeError("revocation list unavailable")
        _cache.update(at=time.time(), entries=entries)
        return entries
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def _save(entries: list[dict]) -> None:
    if _path().startswith("s3://"):
        bucket, key = _path()[5:].split("/", 1)
        _s3().put_object(Bucket=bucket, Key=key, Body=json.dumps(entries, indent=2).encode(),
                         ContentType="application/json")
        _cache["at"] = 0.0
        return
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
