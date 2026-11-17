import hashlib, json, os, subprocess, sys


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def py(args: list[str], *, pythonpath: str | None = None, env: dict | None = None, timeout=120):
    e = {**os.environ, **(env or {})}
    if pythonpath:
        e["PYTHONPATH"] = pythonpath
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, env=e, timeout=timeout)


def git_ref(cwd: str) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else "unversioned"
    except OSError:
        return "unversioned"


def sha256_tree(root: str) -> str:
    """One digest for a folder: every file's relative path and content digest, sorted."""
    items = []
    for d, _, files in os.walk(root):
        for f in files:
            full = os.path.join(d, f)
            items.append([os.path.relpath(full, root).replace(os.sep, "/"), sha256_file(full)])
    return sha256_json(sorted(items))
