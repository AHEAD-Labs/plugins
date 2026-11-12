"""Build the capability artifact: only project_status ships, stamped with the manifest version."""
import glob, os, re, shutil, subprocess, tempfile, zipfile

from .manifest import Manifest
from .util import py, sha256_file

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def build_wheel(m: Manifest, out_dir: str) -> tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        pkg, dist = m.python_package, m.capability_id.split(".")[-1] + "-mcp"
        shutil.copytree(os.path.join(REPO, "src", pkg), os.path.join(tmp, "src", pkg),
                        ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(REPO, "capabilities", "pyproject.artifact.toml")) as f:
            body = f.read().replace("@VERSION@", m.version).replace("@DIST@", dist).replace("@PKG@", pkg)
        open(os.path.join(tmp, "pyproject.toml"), "w").write(body)
        init = os.path.join(tmp, "src", pkg, "__init__.py")
        txt = open(init).read()
        txt = re.sub(r'__version__ = "[^"]*"', f'__version__ = "{m.version}"', txt)
        open(init, "w").write(txt)
        open(os.path.join(tmp, "README.md"), "w").write(m.description)
        r = subprocess.run(["uv", "build", "--wheel", "--out-dir", os.path.join(tmp, "dist")],
                           cwd=tmp, capture_output=True, text=True,
                           env={**os.environ, "SOURCE_DATE_EPOCH": "1700000000"})
        if r.returncode:
            raise RuntimeError("build failed: " + r.stderr[-500:])
        wheel = glob.glob(os.path.join(tmp, "dist", "*.whl"))[0]
        dest = os.path.join(out_dir, os.path.basename(wheel))
        shutil.copy(wheel, dest)
    return dest, sha256_file(dest)


def unpack(wheel: str, dest: str) -> str:
    shutil.rmtree(dest, ignore_errors=True)
    with zipfile.ZipFile(wheel) as z:
        z.extractall(dest)
    return dest


_SCHEMA_SNIPPET = r'''
import asyncio, json, hashlib, @PKG@
from @PKG@.server import schema_server
tools = asyncio.run(schema_server().list_tools())
canon = sorted(({"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in tools), key=lambda t: t["name"])
d = hashlib.sha256(json.dumps(canon, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
print(json.dumps({"digest": d, "tools": [t["name"] for t in canon], "version": @PKG@.__version__, "file": @PKG@.__file__}))
'''


def schema_info(unpacked: str, pkg: str) -> dict:
    """Derive tool schemas from the *built artifact* (not the working tree)."""
    import json
    r = py(["-c", _SCHEMA_SNIPPET.replace("@PKG@", pkg)], pythonpath=unpacked, env={"GMO_AUDIT_LOG": os.devnull})
    if r.returncode:
        raise RuntimeError(r.stderr[-500:])
    info = json.loads(r.stdout.strip().splitlines()[-1])
    assert info["file"].startswith(os.path.realpath(unpacked)) or info["file"].startswith(unpacked), \
        "schema was not read from the built artifact"
    return info
