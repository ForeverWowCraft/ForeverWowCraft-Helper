"""Build the helper's Windows installer, ForeverWowCraft-Helper-<version>.msi.

    python installer/build.py                   from the helper's folder (or anywhere: the paths are its own)
    python installer/build.py --out DIR         where the .msi goes (default: dist/ beside the helper, or the
                                                core's dist/ when the helper sits in the core's checkout)
    python installer/build.py --stage-only      lay the files out and write the WiX fragment, build nothing

What goes in: the helper's files (fwch.py, fwchelper/, addon/, README.md, LICENSE, send.cmd,
setup.cmd; not the tests, not this folder, nothing the helper writes), python.org's embeddable
Python in python/ (installer/embed.py), and python\\ForeverWowCraft Helper.exe: pythonw.exe
under the helper's name, with the helper's icon and a version resource that names the helper
and ForeverWowCraft (installer/exeicon.py: what Settings > Apps > Startup and Task Manager show),
which is what the Start Menu entry and the Run entry start. WiX 3.14's binaries are fetched once into the cache folder
and checked against their hash, like Python; nothing is installed on the PC that builds.
helper.wxs says what the installer does; the files fragment is written here, one component a
folder with a registry key path, as a per-user install wants. Windows only (the resource API,
and WiX itself).
"""
from __future__ import annotations
import argparse
import hashlib
import io
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).resolve().parent
HELPER = HERE.parent
sys.path.insert(0, str(HERE))
import embed  # noqa: E402

NAME = "ForeverWowCraft Helper"
EXE = f"{NAME}.exe"
WIX_URL = "https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip"
WIX_SHA256 = "6ac824e1642d6f7277d0ed7ea09411a508f6116ba6fae0aa5f2c7daa2ff43d31"
LEAVE_OUT = {"tests", "installer", "state", "dist", "__pycache__", ".pytest_cache", ".git", ".github"}
KEYPATHS = r"Software\ForeverWowCraft\Helper\Files"        # where each folder's component keeps its key path
NAMESPACE = uuid.UUID("5b0d1f3e-7a2c-4d6e-9f81-3c5a7e9b1d2f")   # the component GUIDs are made from the folder's path: stable across builds


def version() -> str:
    for line in (HELPER / "fwchelper" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split('"')[1]
    raise SystemExit("fwchelper/__init__.py: no __version__")


def helper_files() -> list[Path]:
    """The helper's own files, relative to its folder, in a stable order."""
    out = []
    for p in sorted(HELPER.rglob("*")):
        rel = p.relative_to(HELPER)
        if p.is_file() and not (set(rel.parts[:-1]) & LEAVE_OUT) and p.suffix != ".pyc":
            out.append(rel)
    return out


def stage(where: Path, cache: Path, ver: str = "0.0.0") -> list[Path]:
    """Lay the install out under `where`, as it will be on the PC; returns the files (relative)."""
    if where.exists():
        shutil.rmtree(where)
    files = []
    for rel in helper_files():
        dst = where / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HELPER / rel, dst)
        files.append(rel)
    python = where / "python"
    python.mkdir()
    for name, data in embed.python_files(cache):
        (python / name).write_bytes(data)
        files.append(Path("python") / name)
    shutil.copyfile(python / "pythonw.exe", python / EXE)
    if sys.platform == "win32":
        import exeicon
        exeicon.set_icon(python / EXE, HELPER / "fwchelper" / "helper.ico")
        exeicon.set_version(python / EXE, ver, exe_strings(ver))
    files.append(Path("python") / EXE)
    return files


def exe_strings(ver: str) -> dict[str, str]:
    """What the exe says of itself: Settings > Apps > Startup shows FileDescription and CompanyName."""
    return {"FileDescription": NAME, "CompanyName": "ForeverWowCraft", "ProductName": NAME, "ProductVersion": ver, "FileVersion": ver,
            "OriginalFilename": EXE, "InternalName": NAME,
            "LegalCopyright": f"{NAME}: MIT licence. Python: Copyright (c) Python Software Foundation, PSF licence (python/LICENSE.txt)."}


def _id(text: str) -> str:
    """A WiX identifier: letters, digits, underscores, at most 72 characters, unique by a hash."""
    safe = "".join(c if c.isalnum() else "_" for c in text)
    return f"{safe[:56]}_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


def fragment(files: list[Path], ver: str) -> str:
    """The WiX fragment that puts the staged files in: one component per folder, its files,
    a registry key path and the folder's removal, as a per-user install wants."""
    by_dir: dict[Path, list[Path]] = {Path("."): []}
    for f in files:
        by_dir.setdefault(f.parent, []).append(f)
        for above in f.parents:                          # a folder with nothing but folders in it is a component too: it is removed with them
            by_dir.setdefault(above, [])
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">', "  <Fragment>",
             '    <DirectoryRef Id="INSTALLDIR">']
    components = []

    def walk(folder: Path, depth: int) -> None:
        # names and GUIDs come from the POSIX form of the path, the same on any OS the fragment is
        # made on; the source paths are Windows', which is where WiX reads them
        pad = "  " * (depth + 3)
        name = folder.as_posix()
        comp = "RootFiles" if folder == Path(".") else _id(name)
        components.append(comp)
        lines.append(f'{pad}<Component Id={quoteattr(comp)} Guid={quoteattr(str(uuid.uuid5(NAMESPACE, name)).upper())}>')
        for f in by_dir.get(folder, []):
            source = quoteattr("$(var.Stage)\\" + "\\".join(f.parts))
            lines.append(f'{pad}  <File Id={quoteattr(_id(f.as_posix()))} Name={quoteattr(f.name)} Source={source} />')
        lines.append(f'{pad}  <RegistryValue Root="HKCU" Key={quoteattr(KEYPATHS)} Name={quoteattr(name)} Type="string" Value={quoteattr(ver)} KeyPath="yes" />')
        lines.append(f'{pad}  <RemoveFolder Id={quoteattr("rm_" + comp)} On="uninstall" />')
        lines.append(f"{pad}</Component>")
        for sub in sorted({d for d in by_dir if d.parent == folder and d != folder}):
            lines.append(f'{pad}<Directory Id={quoteattr("d_" + _id(sub.as_posix()))} Name={quoteattr(sub.name)}>')
            walk(sub, depth + 1)
            lines.append(f"{pad}</Directory>")

    walk(Path("."), 0)
    lines += ["    </DirectoryRef>", '    <ComponentGroup Id="Files">']
    lines += [f"      <ComponentRef Id={quoteattr(c)} />" for c in components]
    lines += ["    </ComponentGroup>", "  </Fragment>", "</Wix>", ""]
    return "\n".join(lines)


def license_rtf(text: str) -> str:
    """The licence as the installer's dialog shows it: plain text in an RTF wrapper."""
    body = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\par\n")
    body = "".join(c if ord(c) < 128 else f"\\u{ord(c)}?" for c in body)
    return "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0\\fswiss Segoe UI;}}\\f0\\fs18\n" + body + "\n}\n"


def wix(cache: Path) -> Path:
    """WiX's tools, unpacked beside the cache; the folder with candle.exe and light.exe."""
    tools = cache / "wix314"
    if not (tools / "candle.exe").exists():
        data = embed.fetch(WIX_URL, WIX_SHA256, cache)
        tools.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(tools)
    return tools


def build(out: Path, cache: Path, stage_only: bool = False) -> Path | None:
    ver = version()
    work = out / "msi"
    staged = work / NAME
    files = stage(staged, cache, ver)
    (work / "files.wxs").write_text(fragment(files, ver), encoding="utf-8")
    (work / "license.rtf").write_text(license_rtf((HELPER / "LICENSE").read_text(encoding="utf-8")), encoding="utf-8")
    print(f"staged {len(files)} files in {staged}")
    if stage_only:
        return None
    if sys.platform != "win32":
        raise SystemExit("the .msi is built on Windows (WiX, and the exe's icon)")
    tools = wix(cache)
    msi = out / f"ForeverWowCraft-Helper-{ver}.msi"
    obj = work / "obj"
    obj.mkdir(exist_ok=True)
    defines = [f"-dVersion={ver}", f"-dStage={staged}", f"-dIcon={HELPER / 'fwchelper' / 'helper.ico'}", f"-dLicense={work / 'license.rtf'}"]
    ext = ["-ext", str(tools / "WixUIExtension.dll"), "-ext", str(tools / "WixUtilExtension.dll")]
    # 1077: WixShellExecTarget names a folder property on purpose; WixShellExec resolves it when it runs
    run([str(tools / "candle.exe"), "-nologo", "-arch", "x64", "-sw1077", *defines, *ext, "-out", str(obj) + os.sep,
         str(HERE / "helper.wxs"), str(work / "files.wxs")])
    # per-user components under the profile folder with registry key paths: what ICE38/43/57/64/91 warn of is what is
    # wanted; ICE61 is the same-version upgrade, wanted too (a build of the same version replaces the one installed)
    run([str(tools / "light.exe"), "-nologo", "-spdb", *ext, "-sice:ICE38", "-sice:ICE43", "-sice:ICE57", "-sice:ICE61", "-sice:ICE64", "-sice:ICE91",
         "-sw1076", "-out", str(msi), *[str(p) for p in sorted(obj.glob("*.wixobj"))]])
    print(f"{msi}  {msi.stat().st_size / 1e6:.1f} MB")
    return msi


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    if r.returncode:
        raise SystemExit(f"{Path(cmd[0]).name} failed ({r.returncode})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    core = HELPER.parent if (HELPER.parent / "fwc.py").exists() else None
    ap.add_argument("--out", type=Path, default=(core or HELPER) / "dist", help="where the .msi goes")
    ap.add_argument("--cache", type=Path, help="where Python and WiX are kept between builds (default: <out>/cache)")
    ap.add_argument("--stage-only", action="store_true", help="lay the files out and write the fragment; build nothing")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    build(a.out, a.cache or a.out / "cache", a.stage_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
