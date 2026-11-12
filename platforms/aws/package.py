"""Build the Lambda zip from an APPROVED registry release (signature + digest verified first)."""
import hashlib, os, shutil, subprocess, zipfile

from govpipeline.registry import Registry

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEPS = ["mcp>=1.2,<2", "pyjwt", "mangum", "httpx"]


def build(registry_dir: str, cap: str, ver: str, out_dir: str) -> tuple[str, str, dict]:
    reg = Registry(registry_dir)
    rec = reg.load(cap, ver)                      # raises if tampered or not approved
    wheel = reg.wheel_path(rec)
    tree = os.path.join(out_dir, "tree")
    shutil.rmtree(tree, ignore_errors=True); os.makedirs(tree)
    subprocess.run(["uv", "pip", "install", "--quiet", "--target", tree, "--python-platform",
                    "aarch64-manylinux2014", "--python-version", "3.12", wheel, *DEPS], check=True)
    # platform code (the gateway) ships with the platform, not with the capability wheel
    shutil.copytree(os.path.join(REPO, "src", "platform_gateway"), os.path.join(tree, "platform_gateway"),
                    ignore=shutil.ignore_patterns("__pycache__", "selfcheck.py"))
    for root, dirs, _ in os.walk(tree):
        for d in [d for d in dirs if d == "__pycache__"]:
            shutil.rmtree(os.path.join(root, d)); dirs.remove(d)
    zpath = os.path.join(out_dir, f"{cap}-{ver}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in sorted(os.walk(tree)):
            for f in sorted(files):
                full = os.path.join(root, f)
                info = zipfile.ZipInfo(os.path.relpath(full, tree), (1980, 1, 1, 0, 0, 0))
                info.external_attr = 0o755 << 16
                z.writestr(info, open(full, "rb").read(), zipfile.ZIP_DEFLATED)
    sha = hashlib.sha256(open(zpath, "rb").read()).hexdigest()
    return zpath, sha, rec
