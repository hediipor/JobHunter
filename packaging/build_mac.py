"""Assemble the Mac bundle: backend sources + the static frontend export + a
double-clickable run.command, zipped with the exec bit intact.

No compiled binary — PyInstaller can't cross-compile, so the Mac build ships
source and run.command builds a venv on first launch. Run from the repo root
(build_exe.ps1 does, after `npm run build`), or:  python packaging/build_mac.py
"""
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "mac_bundle"
APP = OUT / "JobHunterAI"


def stage() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    # backend: every module except the test suite
    py = shutil.ignore_patterns("__pycache__", "test_*.py", "conftest.py", "*.pyc")
    for sub in ("routes", "sources"):
        shutil.copytree(ROOT / "backend" / sub, APP / "backend" / sub, ignore=py)
    (APP / "backend").mkdir(parents=True, exist_ok=True)
    for f in sorted((ROOT / "backend").glob("*.py")):
        if not f.name.startswith("test_") and f.name != "conftest.py":
            shutil.copy2(f, APP / "backend" / f.name)
    shutil.copy2(ROOT / "backend" / "requirements.txt", APP / "backend" / "requirements.txt")

    export = ROOT / "frontend" / "out"
    if not (export / "index.html").exists():
        sys.exit("frontend/out is missing — run `npm run build` in frontend/ first")
    shutil.copytree(export, APP / "frontend" / "out")

    (APP / "profile").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "profile" / "profile.example.json", APP / "profile" / "profile.example.json")
    for name in ("run.command", "MAC_SETUP.md"):
        shutil.copy2(ROOT / "packaging" / "mac" / name, APP / name)


def zip_bundle() -> Path:
    path = OUT / "JobHunterAI-mac.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(p for p in APP.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(f.relative_to(OUT).as_posix())
            # 0o755 on run.command so macOS can launch it straight from the zip;
            # a plain write would strip the exec bit and force a chmod first.
            info.external_attr = (0o755 if f.name.endswith(".command") else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            data = f.read_bytes()
            if f.name.endswith(".command"):
                data = data.replace(b"\r\n", b"\n")  # CRLF = bad interpreter on macOS
            z.writestr(info, data)
    return path


if __name__ == "__main__":
    stage()
    z = zip_bundle()
    print(f"Built: {z.relative_to(ROOT)}  ({z.stat().st_size / 1024:.0f} KB, "
          f"{len(list(APP.rglob('*')))} entries)")
