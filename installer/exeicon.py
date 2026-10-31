"""Give a Windows exe an icon and a name: the .ico's images replace the exe's icon resources,
so that Explorer, the taskbar and Task Manager show it, and a version resource names it, so
that Settings > Apps > Startup, Task Manager's Startup page and the file's Properties say the
helper and ForeverWowCraft, not Python and the Python Software Foundation. ctypes and the
resource API; Windows only, but for version_info(), which is plain bytes. The installer gives a
copy of python.org's pythonw.exe the helper's icon and name this way."""
from __future__ import annotations
import ctypes
import struct
import sys
from ctypes import wintypes as wt
from pathlib import Path

RT_ICON, RT_GROUP_ICON, RT_VERSION, LANG = 3, 14, 16, 1033    # the language python.exe's own resources carry
LOAD_LIBRARY_AS_DATAFILE = 0x2

k32 = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None
if k32 is not None:
    ENUMRESNAMEPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMODULE, ctypes.c_void_p, ctypes.c_void_p, wt.LPARAM)
    for fn, args, res in ((k32.BeginUpdateResourceW, [wt.LPCWSTR, wt.BOOL], wt.HANDLE),
                          (k32.UpdateResourceW, [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wt.WORD, wt.LPVOID, wt.DWORD], wt.BOOL),
                          (k32.EndUpdateResourceW, [wt.HANDLE, wt.BOOL], wt.BOOL),
                          (k32.LoadLibraryExW, [wt.LPCWSTR, wt.HANDLE, wt.DWORD], wt.HMODULE),
                          (k32.EnumResourceNamesW, [wt.HMODULE, ctypes.c_void_p, ENUMRESNAMEPROC, wt.LPARAM], wt.BOOL),
                          (k32.FreeLibrary, [wt.HMODULE], wt.BOOL)):
        fn.argtypes, fn.restype = args, res


def resources(exe: Path, kind: int) -> list:
    """The names of the exe's resources of `kind`: numbers, or strings."""
    module = k32.LoadLibraryExW(str(exe), None, LOAD_LIBRARY_AS_DATAFILE)
    if not module:
        raise OSError(ctypes.get_last_error(), f"{exe}: not loaded")
    found = []

    def each(_module, _kind, name, _param):
        found.append(name if name < 0x10000 else ctypes.wstring_at(name))
        return True

    k32.EnumResourceNamesW(module, kind, ENUMRESNAMEPROC(each), 0)
    k32.FreeLibrary(module)
    return found


def entries(ico: bytes) -> list[tuple]:
    """The images of an .ico: (width, height, colours, reserved, planes, bits, size, offset)."""
    reserved, kind, count = struct.unpack_from("<HHH", ico, 0)
    if (reserved, kind) != (0, 1):
        raise ValueError("not an .ico file")
    return [struct.unpack_from("<BBBBHHII", ico, 6 + 16 * i) for i in range(count)]


def set_icon(exe: Path, ico: Path) -> int:
    """Replace the exe's icons with the .ico's images, as its icon group 1 (the one Explorer
    shows). Returns how many images went in."""
    data = ico.read_bytes()
    images = entries(data)
    old_icons, old_groups = resources(exe, RT_ICON), resources(exe, RT_GROUP_ICON)
    handle = k32.BeginUpdateResourceW(str(exe), False)
    if not handle:
        raise OSError(ctypes.get_last_error(), f"{exe}: its resources could not be opened for writing")
    done = False
    try:
        for kind, names in ((RT_ICON, old_icons), (RT_GROUP_ICON, old_groups)):
            for name in names:
                if isinstance(name, int):
                    k32.UpdateResourceW(handle, kind, name, LANG, None, 0)
        group = struct.pack("<HHH", 0, 1, len(images))
        for n, (w, h, colours, reserved, planes, bits, size, offset) in enumerate(images, 1):
            image = data[offset:offset + size]
            if not k32.UpdateResourceW(handle, RT_ICON, n, LANG, image, len(image)):
                raise OSError(ctypes.get_last_error(), f"icon {n} not written")
            group += struct.pack("<BBBBHHIH", w, h, colours, reserved, planes, bits, size, n)
        if not k32.UpdateResourceW(handle, RT_GROUP_ICON, 1, LANG, group, len(group)):
            raise OSError(ctypes.get_last_error(), "icon group not written")
        done = True
    finally:
        if not k32.EndUpdateResourceW(handle, not done) and done:
            raise OSError(ctypes.get_last_error(), f"{exe}: the new icon was not saved")
    return len(images)


def _block(key: str, value: bytes, text: bool, children: bytes = b"") -> bytes:
    """One node of a version resource: its length, its value's length (in characters when the
    value is text), its kind, its key, the value, and its children, each on a 4-byte boundary."""
    head = struct.pack("<HHH", 0, len(value) // 2 if text else len(value), 1 if text else 0) + key.encode("utf-16-le") + b"\0\0"
    head += b"\0" * (-len(head) % 4)
    body = head + value
    if children:
        body += b"\0" * (-len(body) % 4) + children
    return struct.pack("<H", len(body)) + body[2:]


def version_info(ver: str, strings: dict[str, str]) -> bytes:
    """A VS_VERSIONINFO resource: the version as four numbers (`ver` is "1.5.0", so 1.5.0.0) and
    the given strings (FileDescription, CompanyName, ...), in English, Unicode."""
    numbers = ([int(p) for p in ver.split(".")] + [0, 0, 0, 0])[:4]
    fixed = struct.pack("<13I", 0xFEEF04BD, 0x00010000, numbers[0] << 16 | numbers[1], numbers[2] << 16 | numbers[3],
                        numbers[0] << 16 | numbers[1], numbers[2] << 16 | numbers[3], 0x3F, 0, 0x40004, 1, 0, 0, 0)
    table = b""
    for key, text in strings.items():
        table += b"\0" * (-len(table) % 4) + _block(key, text.encode("utf-16-le") + b"\0\0", True)
    string_info = _block("StringFileInfo", b"", True, _block("040904B0", b"", True, table))
    var_info = _block("VarFileInfo", b"", True, _block("Translation", struct.pack("<HH", 0x0409, 0x04B0), False))
    return _block("VS_VERSION_INFO", fixed, False, string_info + b"\0" * (-len(string_info) % 4) + var_info)


def set_version(exe: Path, ver: str, strings: dict[str, str]) -> None:
    """Replace the exe's version resource with one that carries `ver` and `strings`."""
    data = version_info(ver, strings)
    handle = k32.BeginUpdateResourceW(str(exe), False)
    if not handle:
        raise OSError(ctypes.get_last_error(), f"{exe}: its resources could not be opened for writing")
    done = False
    try:
        for name in resources(exe, RT_VERSION):
            if isinstance(name, int) and name != 1:
                k32.UpdateResourceW(handle, RT_VERSION, name, LANG, None, 0)
        if not k32.UpdateResourceW(handle, RT_VERSION, 1, LANG, data, len(data)):
            raise OSError(ctypes.get_last_error(), "version not written")
        done = True
    finally:
        if not k32.EndUpdateResourceW(handle, not done) and done:
            raise OSError(ctypes.get_last_error(), f"{exe}: the new version was not saved")


def file_version(exe: Path) -> dict[str, str]:
    """What Windows reads back from an exe's version resource: its strings (Windows only)."""
    v = ctypes.WinDLL("version", use_last_error=True)
    size = v.GetFileVersionInfoSizeW(str(exe), None)
    if not size:
        raise OSError(ctypes.get_last_error(), f"{exe}: no version resource")
    buf = ctypes.create_string_buffer(size)
    if not v.GetFileVersionInfoW(str(exe), 0, size, buf):
        raise OSError(ctypes.get_last_error(), f"{exe}: version not read")
    ptr, n = ctypes.c_void_p(), wt.UINT()
    if not v.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(n)) or n.value < 4:
        raise OSError(f"{exe}: no translation in its version resource")
    lang, codepage = struct.unpack("<HH", ctypes.string_at(ptr, 4))     # the strings are under the language and code page the exe names
    out = {}
    for key in ("FileDescription", "CompanyName", "ProductName", "ProductVersion", "FileVersion", "OriginalFilename", "LegalCopyright"):
        ptr, n = ctypes.c_void_p(), wt.UINT()
        if v.VerQueryValueW(buf, f"\\StringFileInfo\\{lang:04X}{codepage:04X}\\{key}", ctypes.byref(ptr), ctypes.byref(n)) and n.value:
            out[key] = ctypes.wstring_at(ptr, n.value).rstrip("\0")
    return out


if __name__ == "__main__":
    print(set_icon(Path(sys.argv[1]), Path(sys.argv[2])), "images")
    if len(sys.argv) > 3:
        set_version(Path(sys.argv[1]), sys.argv[3], {"FileDescription": "test"})
    print(file_version(Path(sys.argv[1])))
