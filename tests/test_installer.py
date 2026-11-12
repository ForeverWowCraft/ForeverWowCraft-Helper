"""What the installer's build puts in (installer/build.py), checked without building: the
files, the WiX fragment, the licence as RTF, the version. The .msi itself is built on Windows."""
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HELPER / "installer"))
sys.path.insert(0, str(HELPER))

import build  # noqa: E402
import embed  # noqa: E402
from fwchelper import __version__  # noqa: E402

WIX = "{http://schemas.microsoft.com/wix/2006/wi}"


def test_the_helpers_files_go_in_and_nothing_of_the_tests_or_the_state():
    files = {str(f).replace("\\", "/") for f in build.helper_files()}
    for name in ("fwch.py", "fwchelper/__init__.py", "fwchelper/app.py", "fwchelper/win.py", "fwchelper/helper.ico",
                 "addon/ForeverWowCraftScanner/ForeverWowCraftScanner.toc", "addon/ForeverWowCraftPlans/ForeverWowCraftPlans.toc",
                 "README.md", "LICENSE"):
        assert name in files, name
    # the zip's own scripts stay out of the install (nothing installed starts them); the zip, which is the
    # repository's files, keeps them
    assert not files & {"send.cmd", "setup.cmd", ".gitignore"}, files & {"send.cmd", "setup.cmd"}
    assert (HELPER / "send.cmd").is_file() and (HELPER / "setup.cmd").is_file()
    assert ".cmd" not in (HELPER / "installer" / "helper.wxs").read_text(encoding="utf-8")
    assert not any(f.startswith(("tests/", "installer/", "state/", "dist/")) or "__pycache__" in f for f in files), sorted(files)[:5]


def test_the_fragment_names_every_file_once_with_a_key_path_a_folder():
    files = [Path("fwch.py"), Path("fwchelper") / "cli.py", Path("fwchelper") / "helper.ico", Path("python") / "python.exe",
             Path("python") / "ForeverWowCraft Helper.exe", Path("addon") / "ForeverWowCraftScanner" / "Seed.lua"]
    text = build.fragment(files, "1.5.0")
    root = ET.fromstring(text)                                          # well formed
    names = [f.get("Name") for f in root.iter(f"{WIX}File")]
    assert sorted(names) == sorted(f.name for f in files)
    sources = [f.get("Source") for f in root.iter(f"{WIX}File")]
    assert "$(var.Stage)\\python\\ForeverWowCraft Helper.exe" in sources
    components = list(root.iter(f"{WIX}Component"))
    assert len(components) == 5                                         # the root, fwchelper, python, addon, addon/ForeverWowCraftScanner
    assert [d.get("Name") for d in root.iter(f"{WIX}Directory")] == ["addon", "ForeverWowCraftScanner", "fwchelper", "python"]
    for c in components:
        keys = [r for r in c.findall(f"{WIX}RegistryValue") if r.get("KeyPath") == "yes"]
        assert len(keys) == 1 and keys[0].get("Root") == "HKCU" and keys[0].get("Value") == "1.5.0", c.get("Id")
        assert c.find(f"{WIX}RemoveFolder") is not None
        assert len(c.get("Guid")) == 36
    assert build.fragment(files, "1.5.0") == text                       # the same files, the same fragment: the GUIDs are stable
    refs = [r.get("Id") for r in root.iter(f"{WIX}ComponentRef")]
    assert sorted(refs) == sorted(c.get("Id") for c in components)
    ids = [e.get("Id") for e in root.iter() if e.get("Id") and not e.tag.endswith("ComponentRef")]
    assert len(ids) == len(set(ids)) and all(len(i) <= 72 and i.replace("_", "a").isalnum() for i in ids)


def test_the_licence_is_rtf_and_the_version_is_the_helpers():
    rtf = build.license_rtf("MIT License\n\nCopyright (c) 2026 ForeverWowCraft {and others}\nÜber\n")
    assert rtf.startswith("{\\rtf1") and "MIT License\\par" in rtf and "\\{and others\\}" in rtf and "\\u220?ber" in rtf
    assert build.version() == __version__ and __version__.count(".") == 2 and all(p.isdigit() for p in __version__.split("."))
    assert (HELPER / "installer" / "helper.wxs").read_text(encoding="utf-8").count("UpgradeCode=") == 1
    assert embed.PYTHON_PTH == "python312.zip\n.\n..\n"                 # the package one up from python\ is found


def test_the_version_resource_names_the_helper_and_carries_the_version():
    import struct
    sys.path.insert(0, str(HELPER / "installer"))
    import exeicon
    data = exeicon.version_info("1.5.0", build.exe_strings("1.5.0"))
    length, value_len, kind = struct.unpack_from("<HHH", data, 0)
    assert length == len(data) and value_len == 52 and kind == 0 and len(data) % 4 == 0
    key = "VS_VERSION_INFO".encode("utf-16-le") + b"\0\0"
    assert data[6:6 + len(key)] == key
    fixed = 6 + len(key) + (-(6 + len(key)) % 4)
    signature, _, file_ms, file_ls, product_ms, product_ls = struct.unpack_from("<6I", data, fixed)
    assert signature == 0xFEEF04BD and (file_ms, file_ls) == (1 << 16 | 5, 0) and (product_ms, product_ls) == (file_ms, file_ls)
    for text in ("StringFileInfo", "040904B0", "FileDescription", "ForeverWowCraft Helper", "CompanyName", "ForeverWowCraft",
                 "ProductVersion", "1.5.0", "VarFileInfo", "Translation"):
        assert text.encode("utf-16-le") + b"\0\0" in data, text
    assert data.endswith(struct.pack("<HH", 0x0409, 0x04B0))        # English, Unicode
    # every node's length is what it says, and each child starts on a 4-byte boundary
    def walk(at, end):
        while at < end:
            n, = struct.unpack_from("<H", data, at)
            assert n > 6 and at + n <= end, (at, n)
            at += n + (-n % 4)
    walk(0, len(data))
    assert "Python Software Foundation" not in build.exe_strings("1.5.0")["CompanyName"]


def _pe(signature: bytes = b"") -> bytes:
    """A small PE32+ file: one section of 512 bytes at 0x200, and `signature` after it, where
    Authenticode puts one, with the security directory pointing at it."""
    import struct
    data = bytearray(0x400)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x40)
    data[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HH", data, 0x44, 0x8664, 1)
    struct.pack_into("<H", data, 0x54, 240)                             # the optional header: 112 bytes, 16 directories
    struct.pack_into("<H", data, 0x58, 0x20B)
    data[0x58 + 240:0x58 + 248] = b".text\0\0\0"
    struct.pack_into("<IIII", data, 0x58 + 240 + 8, 0x200, 0x1000, 0x200, 0x200)
    data[0x200:0x400] = bytes(range(256)) * 2
    if signature:
        struct.pack_into("<II", data, 0x58 + 112 + 8 * 4, len(data), len(signature))
    return bytes(data) + signature


def test_a_changed_copy_of_a_signed_exe_says_plainly_it_is_unsigned():
    """Up to 1.7.6 the helper's exe, a copy of python.org's pythonw.exe with the helper's icon
    and name, kept the header's pointer to python.org's signature, which the resource API had
    left pointing at the new icons, and a stale checksum: a file that looks tampered with.
    exeicon.unsigned takes the signature off (its bytes and the pointer) and sets the checksum."""
    import struct
    import exeicon
    plain = _pe()
    signed = _pe(b"\x10\x00\x00\x00\x00\x02\x02\x00" + b"certificate!")
    assert exeicon.signature_entry(signed) == (0x400, 20) and exeicon.signature_entry(plain) == (0, 0)
    out = exeicon.unsigned(signed)
    assert len(out) == 0x400 and exeicon.signature_entry(out) == (0, 0)
    stored = struct.unpack_from("<I", out, 0x58 + 64)[0]
    assert stored == exeicon.checksum(out) != 0
    assert out == exeicon.unsigned(plain)                                # the same file as one that was never signed
    if sys.platform == "win32":                                          # the checksum is Windows' own
        import ctypes
        from ctypes import wintypes as wt
        imagehlp = ctypes.WinDLL("imagehlp")
        buf = ctypes.create_string_buffer(out, len(out))
        header, computed = wt.DWORD(), wt.DWORD()
        assert imagehlp.CheckSumMappedFile(buf, len(out), ctypes.byref(header), ctypes.byref(computed))
        assert header.value == stored and computed.value == stored
    try:
        exeicon.unsigned(b"not an exe" * 10)
    except ValueError:
        pass
    else:
        raise AssertionError("not an exe, and no error")


def test_staging_lays_the_install_out(tmp=None):
    out = Path(tempfile.mkdtemp())
    cache = HELPER.parent / "dist" / "cache" if (HELPER.parent / "dist" / "cache" / embed.PYTHON_URL.rsplit("/", 1)[1]).exists() else None
    if cache is None:
        print("  (no cached Python here: staging not tried)")
        return
    files = build.stage(out / "stage", cache, "1.5.0")
    assert (out / "stage" / "python" / "python312._pth").read_text() == embed.PYTHON_PTH
    exe = out / "stage" / "python" / "ForeverWowCraft Helper.exe"
    assert exe.exists() and (out / "stage" / "fwch.py").exists()
    assert Path("python") / "ForeverWowCraft Helper.exe" in files and Path("fwchelper") / "app.py" in files
    if sys.platform == "win32":                                           # what Windows reads back: the Startup page's name and publisher
        import exeicon
        read = exeicon.file_version(exe)
        assert read["FileDescription"] == "ForeverWowCraft Helper" and read["CompanyName"] == "ForeverWowCraft"
        assert read["ProductVersion"] == "1.5.0" and "Python Software Foundation" in read["LegalCopyright"]
        assert exeicon.file_version(out / "stage" / "python" / "pythonw.exe")["CompanyName"] == "Python Software Foundation"
    # the helper's exe is plainly unsigned, its checksum right; python.org's files are as python.org signed them
    data = exe.read_bytes()
    import exeicon
    import struct
    assert exeicon.signature_entry(data) == (0, 0)
    assert struct.unpack_from("<I", data, exeicon._layout(data)[0])[0] == exeicon.checksum(data)
    shipped = dict(embed.python_files(cache))
    for name in ("pythonw.exe", "python.exe", "python312.dll"):
        assert (out / "stage" / "python" / name).read_bytes() == shipped[name], name
        assert exeicon.signature_entry(shipped[name])[1] > 0, name


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
