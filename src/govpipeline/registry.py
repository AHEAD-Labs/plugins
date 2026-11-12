"""Approved artifact registry: immutable, signed release records + the artifact itself."""
import hashlib, hmac, json, os, shutil

from .util import sha256_file

KEY = lambda: os.environ.get("GMO_SIGNING_KEY", "dev-only-signing-key").encode()


def _canon(rec: dict) -> bytes:
    return json.dumps({k: v for k, v in rec.items() if k != "signature"}, sort_keys=True,
                      separators=(",", ":")).encode()


def sign(rec: dict) -> str:
    return hmac.new(KEY(), _canon(rec), hashlib.sha256).hexdigest()


class Registry:
    def __init__(self, root: str):
        self.root = root

    def dir(self, cap: str, ver: str) -> str:
        return os.path.join(self.root, cap, ver)

    def exists(self, cap, ver) -> bool:
        return os.path.exists(os.path.join(self.dir(cap, ver), "release.json"))

    def publish(self, rec: dict, wheel: str, evidence: dict[str, dict], files: list[str] = ()) -> str:
        cap, ver = rec["capability_id"], rec["version"]
        if self.exists(cap, ver):
            raise FileExistsError(f"{cap}@{ver} already released (releases are immutable)")
        d = self.dir(cap, ver)
        os.makedirs(d)
        shutil.copy(wheel, d)
        for f in files:
            shutil.copy(f, d)
        for name, body in evidence.items():
            json.dump(body, open(os.path.join(d, name), "w"), indent=2, sort_keys=True)
        rec = {**rec, "signature": sign(rec)}
        json.dump(rec, open(os.path.join(d, "release.json"), "w"), indent=2, sort_keys=True)
        return d

    def load(self, cap: str, ver: str) -> dict:
        """Load + verify signature and artifact digest. Raises if tampered."""
        d = self.dir(cap, ver)
        rec = json.load(open(os.path.join(d, "release.json")))
        if not hmac.compare_digest(rec["signature"], sign(rec)):
            raise ValueError(f"release record signature invalid for {cap}@{ver}")
        wheel = os.path.join(d, rec["artifact"]["filename"])
        if sha256_file(wheel) != rec["artifact"]["sha256"]:
            raise ValueError(f"artifact digest mismatch for {cap}@{ver}")
        if rec["status"] != "approved":
            raise ValueError(f"{cap}@{ver} is not approved")
        return rec

    def wheel_path(self, rec: dict) -> str:
        return os.path.join(self.dir(rec["capability_id"], rec["version"]), rec["artifact"]["filename"])

    def versions(self, cap: str) -> list[str]:
        p = os.path.join(self.root, cap)
        vs = [v for v in os.listdir(p) if self.exists(cap, v)] if os.path.isdir(p) else []
        return sorted(vs, key=lambda v: tuple(map(int, v.split("."))))

    def capabilities(self) -> list[str]:
        return sorted(c for c in os.listdir(self.root)) if os.path.isdir(self.root) else []
