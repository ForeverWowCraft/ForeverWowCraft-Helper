"""Auctionator shopping-list import strings and results-CSV export parsing.

Import format (Auctionator.Shopping.Lists.BatchImportFromString, Auctionator 339):
    list name^term 1^term 2        (one list per line)
Each term is an "advanced search" string joined by ';' (Auctionator.Search.ReconstituteAdvancedSearch):
    "Exact Name";category;minIlvl;maxIlvl;minLvl;maxLvl;minCraft;maxCraft;minPrice;maxPrice;quality;tier;expansion;quantity
Quoting the name makes the search exact.

Export format ("Export Results" button on the Shopping tab). Seen on the Forever beta client:
    "Price","Name","Item Level","Owned?","Available"
    8400,"Big Bronze Knife (20)",20,"",11
Older/legacy layout: "Price","Name","Owned","Top?","Available". Columns are found by header
name, WoW colour/link markup is stripped, and a trailing " (item level)" is removed from names.
Price is the lowest unit buyout seen, in copper.
"""
from __future__ import annotations
import csv
import io
import re

SEARCH_FIELDS = 14


def search_term(name: str, exact: bool = True, quantity: int | None = None) -> str:
    """One Auctionator advanced-search term for an item name (quoted = exact match). `quantity`
    fills the last field, so the shopping list shows the price of buying that many."""
    q = f'"{name}"' if exact else name
    return q + ";" * (SEARCH_FIELDS - 1) + (str(quantity) if quantity else "")


def import_string(lists: dict[str, list], exact: bool = True) -> str:
    """lists: {list name: [item name | (item name, quantity)]} -> multi-line import string."""
    lines = []
    for list_name, entries in lists.items():
        terms = [search_term(e, exact) if isinstance(e, str) else search_term(e[0], exact, e[1]) for e in entries]
        lines.append("^".join([list_name] + terms))
    return "\n".join(lines)


_WOW_MARKUP = re.compile(r"\|c[0-9a-fA-F]{8}|\|r|\|H[^|]*\|h|\|h|\|T[^|]*\|t")
# Auctionator's Forever/Classic shopping export appends the item level: 'Big Bronze Knife (20)'
_ILVL_SUFFIX = re.compile(r"\s*\(\d+\)\s*$")


def strip_markup(s: str) -> str:
    """Remove WoW colour codes, hyperlink wrappers and texture tags from a string."""
    s = _WOW_MARKUP.sub("", s)
    return s.strip().strip("[]").strip()


def clean_item_name(s: str) -> str:
    """An item name from an Auctionator export as the item is called: markup and a trailing " (item level)" removed."""
    return _ILVL_SUFFIX.sub("", strip_markup(s)).strip()


_MONEY = re.compile(r"(?:(\d+)g)?(?:(\d+)s)?(?:(\d+)c)?", re.I)


def parse_money(s: str) -> int | None:
    """'1g 5s 20c' | '10500' (copper) | '1.05' (gold, decimal) -> copper."""
    s = str(s).strip().replace(",", "")
    if not s:
        return None
    if re.fullmatch(r"\d+", s):
        return int(s)
    if re.fullmatch(r"\d+\.\d+", s):
        return int(round(float(s) * 10000))
    m = _MONEY.fullmatch(s.replace(" ", ""))
    if m and any(m.groups()):
        g, sv, c = (int(x) if x else 0 for x in m.groups())
        return g * 10000 + sv * 100 + c
    return None


def parse_export(text: str) -> dict[str, dict]:  # noqa: C901 - baseline 9 Nov 2026, to be split
    """Parse Auctionator 'Export Results' CSV (or a simple name,price CSV).

    Returns {item name: {"price": copper, "available": int|None}} keeping the lowest
    price when a name appears more than once.
    """
    text = text.strip().lstrip("﻿")
    if not text:
        return {}
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = [strip_markup(h).lower() for h in rows[0]]
    if "name" in header and "price" in header:
        i_name, i_price = header.index("name"), header.index("price")
        i_avail = header.index("available") if "available" in header else None
        body = rows[1:]
    else:
        # bare "name,price" or "price,name"
        i_name, i_price, i_avail = 0, 1, None
        if rows[0] and parse_money(rows[0][0]) is not None:
            i_name, i_price = 1, 0
        body = rows
    out: dict[str, dict] = {}
    for r in body:
        if len(r) <= max(i_name, i_price):
            continue
        name = clean_item_name(r[i_name])
        price = parse_money(strip_markup(r[i_price]))
        if not name or price is None or price <= 0:
            continue
        avail = None
        if i_avail is not None and len(r) > i_avail:
            try:
                avail = int(strip_markup(r[i_avail]))
            except ValueError:
                avail = None
        prev = out.get(name)
        if prev is None or price < prev["price"]:
            out[name] = {"price": price, "available": avail}
    return out


def fmt_money(copper: float, signed: bool = False) -> str:
    """Copper -> '1g 05s 20c' style; signed=True prefixes '+' on non-negative values."""
    neg = copper < 0
    c = int(round(abs(copper)))
    g, rem = divmod(c, 10000)
    s, c = divmod(rem, 100)
    if g:
        txt = f"{g}g {s:02d}s {c:02d}c"
    elif s:
        txt = f"{s}s {c:02d}c"
    else:
        txt = f"{c}c"
    if neg:
        return "-" + txt
    return ("+" + txt) if signed else txt
