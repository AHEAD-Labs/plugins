import subprocess, sys


def test_end_to_end_demo(tmp_path):
    """Runs the full acceptance demonstration (starts backend + remote on 8801/8802)."""
    r = subprocess.run([sys.executable, "-m", "govpipeline.cli", "--ws", str(tmp_path / "ws"), "demo"],
                       capture_output=True, text=True, timeout=600)
    print(r.stdout)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert "ACCEPTANCE: all checks passed" in r.stdout
