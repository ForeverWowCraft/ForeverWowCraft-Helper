"""Minimal parser for WoW SavedVariables files.

The client writes globals as Lua table literals:

    FWCS_DB = {
        ["Realm Name"] = {
            [2840] = {
                ["name"] = "Copper Bar",
                ["l"] = {
                    {
                        12, -- [1]
                        20, -- [2]
                    }, -- [1]
                },
                ["complete"] = true,
            },
        },
    }

Tables whose keys are exactly 1..n come back as lists, everything else as dicts.
"""
from __future__ import annotations
import re

_TOKEN = re.compile(r"""
    \s+ | --[^\n]* |                      # whitespace, comments
    (?P<num>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?) |
    (?P<str>"(?:\\.|[^"\\])*") |
    (?P<name>[A-Za-z_][A-Za-z0-9_]*) |
    (?P<punct>[{}\[\]=,;])
""", re.X)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "\n": "\n"}


def _unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt.isdigit():
                j = i + 1
                while j < len(s) and j < i + 4 and s[j].isdigit():
                    j += 1
                out.append(chr(int(s[i + 1:j])))
                i = j
                continue
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def tokenize(text: str):
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            raise SyntaxError(f"unexpected character {text[pos]!r} at {pos}")
        pos = m.end()
        if m.lastgroup == "num":
            v = m.group("num")
            yield ("num", float(v) if any(c in v for c in ".eE") else int(v))
        elif m.lastgroup == "str":
            yield ("str", _unescape(m.group("str")[1:-1]))
        elif m.lastgroup == "name":
            yield ("name", m.group("name"))
        elif m.lastgroup == "punct":
            yield ("punct", m.group("punct"))
    yield ("eof", None)


class _Parser:
    """Recursive-descent parser over the token stream: `globals` handles `NAME = value` pairs,
    `value` a literal, `table` a `{...}` constructor with `[key] =`, `name =` or positional
    entries."""

    def __init__(self, text: str):
        self.toks = list(tokenize(text))
        self.i = 0

    def peek(self):
        return self.toks[self.i]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, kind, val=None):
        t = self.next()
        if t[0] != kind or (val is not None and t[1] != val):
            raise SyntaxError(f"expected {kind} {val!r}, got {t}")
        return t

    def value(self):
        kind, val = self.peek()
        if kind == "num" or kind == "str":
            self.next()
            return val
        if kind == "name":
            self.next()
            if val == "true":
                return True
            if val == "false":
                return False
            if val == "nil":
                return None
            raise SyntaxError(f"unexpected name {val!r}")
        if kind == "punct" and val == "{":
            return self.table()
        raise SyntaxError(f"unexpected token {self.peek()}")

    def table(self):
        self.expect("punct", "{")
        d: dict = {}
        idx = 1
        while True:
            kind, val = self.peek()
            if kind == "punct" and val == "}":
                self.next()
                break
            if kind == "punct" and val == "[":
                self.next()
                key = self.value()
                self.expect("punct", "]")
                self.expect("punct", "=")
                d[key] = self.value()
            elif kind == "name" and self.toks[self.i + 1] == ("punct", "="):
                self.next()
                self.next()
                d[val] = self.value()
            else:
                d[idx] = self.value()
                idx += 1
            kind, val = self.peek()
            if kind == "punct" and val in (",", ";"):
                self.next()
        if d and all(isinstance(k, int) for k in d) and sorted(d) == list(range(1, len(d) + 1)):
            return [d[k] for k in range(1, len(d) + 1)]
        return d

    def globals(self) -> dict:
        out = {}
        while self.peek()[0] != "eof":
            name = self.expect("name")[1]
            self.expect("punct", "=")
            out[name] = self.value()
        return out


def parse(text: str) -> dict:
    """Parse a SavedVariables file into {global name: value}."""
    return _Parser(text).globals()


def parse_value(text: str):
    """Parse a single Lua literal (useful for tests)."""
    return _Parser(text).value()
