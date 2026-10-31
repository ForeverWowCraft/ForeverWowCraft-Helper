"""The ForeverWowCraft Helper's command line: `python fwch.py <command>` (fwchelper/cli.py)."""
import sys

sys.dont_write_bytecode = True          # nothing written beside the helper's files: an installed copy is removed clean
from fwchelper.cli import main  # noqa: E402

main()
