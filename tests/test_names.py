"""Every name a module uses is defined: imported, assigned, a parameter, or a builtin.

A static look, by symtable, at every Python file of the helper (fwchelper/, the helper's own scripts, installer/): it runs on every platform, where
the platform modules (win.py, winreg) cannot be imported. win.quiet_update used `settings`
without importing it from 1.6.0 to 1.6.9 (the Mac commit of 5 Nov 2026 dropped the import):
no test ran it, the quiet install raised NameError, and the helper's watch thread ended with
it (6 Nov 2026). This would have said so.
"""
import builtins
import symtable
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWN = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__", "__package__", "__loader__", "__builtins__", "__annotations__"}


def undefined_names(path: Path) -> list[str]:
    """The names referenced in the file that nothing defines: at the top, in a function, or by
    a `global` in one (`free` names are a closure's, and locals of a function its own)."""
    top = symtable.symtable(path.read_text(encoding="utf-8"), str(path), "exec")
    defined = {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported()}

    def globals_assigned(table):
        for child in table.get_children():
            for s in child.get_symbols():
                if s.is_assigned() and s.is_global():
                    defined.add(s.get_name())
            globals_assigned(child)
    globals_assigned(top)
    out = set()

    def check(table):
        for s in table.get_symbols():
            own = s.is_assigned() or s.is_parameter() or s.is_imported() or s.is_free() or (s.is_local() and table is not top)
            if s.is_referenced() and not own and s.get_name() not in defined and s.get_name() not in KNOWN:
                out.add(s.get_name())
        for child in table.get_children():
            check(child)
    check(top)
    return sorted(out)


def test_every_name_the_modules_use_is_defined():
    files = [p for folder in ("fwchelper", ".", "installer") for p in sorted((ROOT / folder).glob("*.py"))]
    assert len(files) > 10, files
    bad = {str(p.relative_to(ROOT)): undefined_names(p) for p in files}
    bad = {k: v for k, v in bad.items() if v}
    assert bad == {}, bad


if __name__ == "__main__":
    test_every_name_the_modules_use_is_defined()
    print("ok", sys.argv[0])
