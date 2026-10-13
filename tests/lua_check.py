"""Cheap structural check for the addon's Lua (no Lua interpreter on this machine).

Verifies that block openers (function/if/for/while/do/repeat) balance with end/until, that
parentheses and braces balance, and that file-scope locals are not referenced before they are
defined. It is not a parser; it catches the mistakes that are easy to make when editing by hand.

    python tests/lua_check.py addon/ForeverWowCraftScanner/ForeverWowCraftScanner.lua
"""
import re
import sys

KEYWORDS_OPEN = {"function", "if", "while", "for", "repeat"}
TOKEN = re.compile(
    r"--\[\[.*?\]\]|--[^\n]*|\[\[.*?\]\]|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[A-Za-z_][A-Za-z0-9_]*|[(){}\[\]]|\S",
    re.S,
)


def check(path: str) -> int:
    src = open(path, encoding="utf-8").read()
    problems = 0
    depth, parens, braces = 0, 0, 0
    line = 1
    pending_do = False  # 'for'/'while' consume the following 'do'
    first_use: dict[str, int] = {}
    local_def: dict[str, int] = {}
    prev = None
    for m in TOKEN.finditer(src):
        tok = m.group(0)
        line = src.count("\n", 0, m.start()) + 1
        if tok.startswith("--") or tok[0] in "\"'" or tok.startswith("[["):
            prev = tok
            continue
        if tok in ("(",):
            parens += 1
        elif tok == ")":
            parens -= 1
        elif tok == "{":
            braces += 1
        elif tok == "}":
            braces -= 1
        elif tok in ("function", "if", "repeat"):
            depth += 1
        elif tok in ("for", "while"):
            depth += 1
            pending_do = True
        elif tok == "do":
            if pending_do:
                pending_do = False
            else:
                depth += 1
        elif tok in ("end", "until"):
            depth -= 1
            if depth < 0:
                print(f"{path}:{line}: extra 'end'")
                problems += 1
                depth = 0
        if re.match(r"[A-Za-z_]", tok) and tok not in ("local", "function", "end", "if", "then", "else", "elseif",
                                                     "for", "while", "do", "repeat", "until", "return", "and", "or",
                                                     "not", "nil", "true", "false", "in", "break"):
            # Only file-scope locals are tracked (depth 0, or the name right after 'local function'
            # whose own 'function' token has already bumped depth to 1). Field accesses (a.b) do
            # not count as uses.
            is_local_fn = prev == "function" and depth == 1 and \
                src[max(0, m.start() - 15):m.start()].rstrip().endswith("local function")
            if (prev == "local" and depth == 0) or is_local_fn:
                local_def.setdefault(tok, line)
            elif prev not in (".", ":"):
                first_use.setdefault(tok, line)
        prev = tok
    for name, dline in local_def.items():
        uline = first_use.get(name, dline)
        if uline < dline:
            print(f"{path}:{uline}: '{name}' referenced before its local definition at line {dline}")
            problems += 1
    if depth != 0:
        print(f"{path}: block imbalance: {depth} unclosed block(s) at end of file")
        problems += 1
    if parens or braces:
        print(f"{path}: unbalanced parentheses ({parens}) or braces ({braces})")
        problems += 1
    print(f"{path}: {'OK' if problems == 0 else str(problems) + ' problem(s)'}")
    return problems


if __name__ == "__main__":
    sys.exit(1 if any(check(p) for p in sys.argv[1:]) else 0)
