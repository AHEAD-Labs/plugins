"""Append-only JSONL audit trail. Every record names user, capability and version."""
import json, os, sys, time, uuid
from . import CAPABILITY_ID, __version__


def record(*, source: str, user: str | None, tool: str | None, transport: str,
           decision: str, reason: str = "", project_id: str | None = None,
           version: str | None = None) -> dict:
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event_id": uuid.uuid4().hex,
        "source": source, "user": user, "capability_id": CAPABILITY_ID,
        "version": version or os.environ.get("CAPABILITY_VERSION") or __version__,
        "transport": transport, "tool": tool, "project_id": project_id,
        "decision": decision, "reason": reason,
    }
    line = json.dumps(rec, separators=(",", ":")) + "\n"
    path = os.environ.get("GMO_AUDIT_LOG")
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)
        try:
            os.write(fd, line.encode())
        finally:
            os.close(fd)
    else:
        sys.stderr.write(line)
    return rec
