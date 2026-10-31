"""Windows, through ctypes: the icon in the notification area with its menu and balloons, the
mutex that keeps the app to one instance, the Run key and Windows' own startup switch, a
folder dialog, opening a file or an address, a user setting. Nothing here decides anything:
fwchelper/tray.py does, and fwchelper/app.py drives. Imported on Windows only."""
from __future__ import annotations
import ctypes
import os
import queue
import subprocess
import winreg
from ctypes import wintypes as wt
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

WM_NULL, WM_DESTROY, WM_CLOSE, WM_QUERYENDSESSION, WM_ENDSESSION = 0x0, 0x2, 0x10, 0x11, 0x16
WM_SETTINGCHANGE, WM_CONTEXTMENU, WM_LBUTTONUP, WM_RBUTTONUP, WM_APP = 0x1A, 0x7B, 0x202, 0x205, 0x8000
WM_TRAY, WM_CALL = WM_APP + 1, WM_APP + 2
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIIF_USER, NIIF_LARGE_ICON, NIIF_RESPECT_QUIET_TIME = 0x4, 0x20, 0x80
MF_STRING, MF_GRAYED, MF_CHECKED, MF_SEPARATOR = 0x0, 0x1, 0x8, 0x800
TPM_RIGHTBUTTON, TPM_BOTTOMALIGN, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x20, 0x100, 0x80
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE, SM_CXSMICON = 1, 0x10, 0x40, 49
HWND_MESSAGE, HWND_BROADCAST, SMTO_ABORTIFHUNG, SW_SHOWNORMAL = -3, 0xFFFF, 0x2, 1
BIF_RETURNONLYFSDIRS, BIF_NEWDIALOGSTYLE, COINIT_APARTMENTTHREADED = 0x1, 0x40, 0x2
ERROR_ALREADY_EXISTS, ERROR_CLASS_ALREADY_EXISTS = 183, 1410
MB_ICONINFORMATION = 0x40
CLASS = "ForeverWowCraftHelperTray"

for fn, args, res in (
        (user32.DefWindowProcW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], LRESULT),
        (user32.CreateWindowExW, [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID], wt.HWND),
        (user32.DestroyWindow, [wt.HWND], wt.BOOL),
        (user32.GetMessageW, [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT], ctypes.c_int),
        (user32.TranslateMessage, [ctypes.POINTER(wt.MSG)], wt.BOOL),
        (user32.DispatchMessageW, [ctypes.POINTER(wt.MSG)], LRESULT),
        (user32.PostMessageW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], wt.BOOL),
        (user32.PostQuitMessage, [ctypes.c_int], None),
        (user32.SetForegroundWindow, [wt.HWND], wt.BOOL),
        (user32.GetCursorPos, [ctypes.POINTER(wt.POINT)], wt.BOOL),
        (user32.CreatePopupMenu, [], wt.HMENU),
        (user32.AppendMenuW, [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR], wt.BOOL),
        (user32.TrackPopupMenu, [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.LPVOID], ctypes.c_int),
        (user32.DestroyMenu, [wt.HMENU], wt.BOOL),
        (user32.LoadImageW, [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT], wt.HANDLE),
        (user32.RegisterWindowMessageW, [wt.LPCWSTR], wt.UINT),
        (user32.GetSystemMetrics, [ctypes.c_int], ctypes.c_int),
        (user32.SendMessageTimeoutW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPCWSTR, wt.UINT, wt.UINT, ctypes.POINTER(wt.DWORD)], LRESULT),
        (user32.MessageBoxW, [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT], ctypes.c_int),
        (kernel32.CreateMutexW, [wt.LPVOID, wt.BOOL, wt.LPCWSTR], wt.HANDLE),
        (kernel32.GetModuleHandleW, [wt.LPCWSTR], wt.HMODULE),
        (shell32.SHBrowseForFolderW, [wt.LPVOID], wt.LPVOID),
        (shell32.SHGetPathFromIDListW, [wt.LPVOID, wt.LPWSTR], wt.BOOL),
        (shell32.ShellExecuteW, [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_int], wt.HINSTANCE),
        (ole32.CoInitializeEx, [wt.LPVOID, wt.DWORD], ctypes.c_long),
        (ole32.CoTaskMemFree, [wt.LPVOID], None)):
    fn.argtypes, fn.restype = args, res


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


user32.RegisterClassW.argtypes, user32.RegisterClassW.restype = [ctypes.POINTER(WNDCLASSW)], wt.ATOM


class GUID(ctypes.Structure):
    _fields_ = [("a", wt.DWORD), ("b", wt.WORD), ("c", wt.WORD), ("d", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT), ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT),
                ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128), ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
                ("szInfo", wt.WCHAR * 256), ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wt.HICON)]


shell32.Shell_NotifyIconW.argtypes, shell32.Shell_NotifyIconW.restype = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)], wt.BOOL


class BROWSEINFOW(ctypes.Structure):
    _fields_ = [("hwndOwner", wt.HWND), ("pidlRoot", wt.LPVOID), ("pszDisplayName", wt.LPWSTR), ("lpszTitle", wt.LPCWSTR),
                ("ulFlags", wt.UINT), ("lpfn", wt.LPVOID), ("lParam", wt.LPARAM), ("iImage", ctypes.c_int)]


# ---- one instance -------------------------------------------------------------------------------
_held: list = []        # the mutex handles, for the life of the process


def one_instance(name: str) -> bool:
    """Take the named mutex; False when another process of this user holds it already."""
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return True                                      # cannot tell: better to run than not
    _held.append(handle)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def message(title: str, text: str) -> None:
    user32.MessageBoxW(None, text, title, MB_ICONINFORMATION)


# ---- the icon -----------------------------------------------------------------------------------
class Tray:
    """The icon in the notification area, with its menu and balloons. Made and run on one thread
    (run() is that thread's message loop until quit()); other threads reach it through call().

    items()       the menu's rows, (id, label, enabled, checked) or None (fwchelper/tray.py's)
    chosen(id)    what to do with the row picked; called on the icon's thread
    closing()     Windows, or the uninstaller, is closing the window: the app should stop
    """

    def __init__(self, title: str, icon: Path, items, chosen, closing):
        self.items, self.chosen, self.closing = items, chosen, closing
        self.todo: queue.Queue = queue.Queue()
        self.tip, self.hwnd = title, None
        small = user32.GetSystemMetrics(SM_CXSMICON)
        self.hicon = user32.LoadImageW(None, str(icon), IMAGE_ICON, small, small, LR_LOADFROMFILE)
        self.hbig = user32.LoadImageW(None, str(icon), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")      # Explorer restarted: the icon is to be added again
        self.proc = WNDPROC(self._wndproc)                                # kept: the window calls it for as long as it lives
        cls = WNDCLASSW(lpfnWndProc=self.proc, hInstance=kernel32.GetModuleHandleW(None), lpszClassName=CLASS)
        if not user32.RegisterClassW(ctypes.byref(cls)) and ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
            raise OSError(ctypes.get_last_error(), "the tray's window class could not be registered")
        # a top-level window that is never shown, not a message-only one: the uninstaller's
        # "close the application" and Explorer's TaskbarCreated reach top-level windows only
        self.hwnd = user32.CreateWindowExW(0, CLASS, title, 0, 0, 0, 0, 0, None, None, cls.hInstance, None)
        if not self.hwnd:
            raise OSError(ctypes.get_last_error(), "the tray's window could not be made")
        self._add()

    def _data(self, flags: int) -> NOTIFYICONDATAW:
        d = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), hWnd=self.hwnd, uID=1, uFlags=flags, uCallbackMessage=WM_TRAY,
                            hIcon=self.hicon)
        d.szTip = self.tip[:127]
        return d

    def _add(self) -> None:
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP)))

    def tooltip(self, text: str) -> None:
        self.tip = text
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._data(NIF_TIP)))

    def balloon(self, title: str, text: str) -> None:
        d = self._data(NIF_INFO)
        d.szInfo, d.szInfoTitle = text[:255], title[:63]
        d.dwInfoFlags, d.hBalloonIcon = NIIF_USER | NIIF_LARGE_ICON | NIIF_RESPECT_QUIET_TIME, self.hbig
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(d))

    def call(self, fn) -> None:
        """Have `fn` run on the icon's thread."""
        self.todo.put(fn)
        user32.PostMessageW(self.hwnd, WM_CALL, 0, 0)

    def quit(self) -> None:
        self.call(lambda: user32.PostQuitMessage(0))

    def run(self) -> None:
        """The message loop, until quit() or Windows closes the window."""
        msg = wt.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data(0)))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            if lparam in (WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU):
                self._menu()
            return 0
        if msg == WM_CALL:
            while True:
                try:
                    fn = self.todo.get_nowait()
                except queue.Empty:
                    return 0
                fn()
        if msg == WM_QUERYENDSESSION:
            return 1
        if msg == WM_CLOSE or (msg == WM_ENDSESSION and wparam):
            self.closing()
            user32.PostQuitMessage(0)
            return 0
        if msg == self.taskbar_created:
            self._add()
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _menu(self) -> None:
        menu = user32.CreatePopupMenu()
        for row in self.items():
            if row is None:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            else:
                ident, label, enabled, checked = row
                user32.AppendMenuW(menu, MF_STRING | (0 if enabled else MF_GRAYED) | (MF_CHECKED if checked else 0), ident, label)
        at = wt.POINT()
        user32.GetCursorPos(ctypes.byref(at))
        user32.SetForegroundWindow(self.hwnd)                 # or the menu stays when the user clicks elsewhere
        picked = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_RETURNCMD | TPM_NONOTIFY, at.x, at.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if picked:
            self.chosen(picked)


# ---- dialogs and the shell ----------------------------------------------------------------------
def browse_folder(title: str) -> Path | None:
    """A folder the user picks, or None. On the thread that runs the message loop."""
    ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    shown = ctypes.create_unicode_buffer(1024)
    info = BROWSEINFOW(hwndOwner=None, pidlRoot=None, pszDisplayName=ctypes.cast(shown, wt.LPWSTR), lpszTitle=title,
                       ulFlags=BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE)
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(info))
    if not pidl:
        return None
    path = ctypes.create_unicode_buffer(1024)
    ok = shell32.SHGetPathFromIDListW(pidl, path)
    ole32.CoTaskMemFree(pidl)
    return Path(path.value) if ok and path.value else None


def open_path(what: str | Path) -> None:
    """Open a file with what Windows opens it with, or an address in the browser."""
    shell32.ShellExecuteW(None, "open", str(what), None, None, SW_SHOWNORMAL)


def game_running() -> bool:
    """Whether a World of Warcraft client runs (its process is Wow..., whatever the flavour)."""
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line.lower().startswith('"wow') for line in out.splitlines())


# ---- the registry -------------------------------------------------------------------------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"


def _read(key: str, name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def run_value(name: str) -> str | None:
    """The command under the user's Run key, or None."""
    value = _read(RUN_KEY, name)
    return str(value) if value is not None else None


def set_run_value(name: str, command: str | None) -> None:
    """Put a command under the user's Run key, or with None take it out."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if command is None:
            try:
                winreg.DeleteValue(k, name)
            except OSError:
                pass
        else:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, command)


def approved(name: str) -> bytes | None:
    """Windows' own switch for a Run entry (Settings > Apps > Startup): its record, or None."""
    value = _read(APPROVED_KEY, name)
    return bytes(value) if isinstance(value, (bytes, bytearray)) else None


def approve(name: str) -> None:
    """Turn Windows' own switch for a Run entry on."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_BINARY, bytes([2]) + bytes(11))


def set_user_setting(name: str, value: str) -> None:
    """Keep a setting for the user (HKCU\\Environment, what setx does), tell the programs that
    listen, and this process."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
    os.environ[name] = value
    user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, ctypes.byref(wt.DWORD()))
