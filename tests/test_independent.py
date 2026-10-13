"""The helper is a project of its own: it runs with nothing but itself on the path, and nothing in
it names the core."""
import re
import subprocess
import sys
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent
CORE = "foreverwowcraft"


def _files():
    return [p for p in HELPER.rglob("*") if p.is_file() and p.suffix in (".py", ".lua", ".toc", ".md", ".cmd", ".ps1")
            and "__pycache__" not in p.parts and p.name != "test_independent.py"]


def test_nothing_imports_the_core():
    for p in _files():
        if p.suffix == ".py":
            text = p.read_text(encoding="utf-8")
            assert not re.search(rf"^\s*(from|import)\s+{CORE}\b", text, re.M), p
            assert not re.search(r"^\s*from\s+\.\.", text, re.M), p          # nor reaches above its own package


def test_it_runs_alone():
    # a Python that is given the helper's folder and nothing else of the project
    code = ("import sys; sys.path.insert(0, r'%s');"
            "import fwchelper, fwchelper.scan, fwchelper.pipe, fwchelper.plans, fwchelper.cli, fwchelper.auctionator, fwchelper.luatable;"
            "assert '%s' not in sys.modules; print(fwchelper.__version__)") % (HELPER, CORE)
    r = subprocess.run([sys.executable, "-I", "-c", code], cwd=HELPER.anchor, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip(), r.stderr[-400:]
    r = subprocess.run([sys.executable, "-E", "-s", str(HELPER / "fwch.py"), "--help"], cwd=HELPER.anchor, capture_output=True, text=True)
    assert r.returncode == 0 and "install-addon" in r.stdout and "send" in r.stdout, r.stderr[-400:]


def test_it_has_what_a_project_needs():
    for name in ("LICENSE", "README.md", "fwch.py", "fwchelper/__init__.py", "addon"):
        assert (HELPER / name).exists(), name
    assert "MIT License" in (HELPER / "LICENSE").read_text(encoding="utf-8")


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
