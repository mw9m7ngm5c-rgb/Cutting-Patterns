"""Sawing pattern text notation: parse and serialise.

All sizes are dry sizes in mm.

    primary     "25 38/114/38 25"   sideboards, /cant width/, sideboards
                "3*25 2*38 3*25"    no cant: live sawing
    secondary   "25 3*38 25"        board thicknesses across the cant
    n*t         n adjacent boards of thickness t
    ,           arris blade, written straight after the item it follows: "25 3*38,25"
    < >         riving knives around the boards that are only cross-cut: "25 <3*38> 25"
    TxW         chipper-profiler sideboard with a fixed width: "25x76"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class PatternError(ValueError):
    pass


@dataclass(frozen=True)
class Item:
    thickness: float
    width: float | None = None   # only for chipper-profiler sideboards


@dataclass(frozen=True)
class Stack:
    """An ordered run of boards with optional markers.

    arris_after:  index of the board the arris blade follows (None if no arris blade).
    knives:       (first, last) index of the boards inside the riving knives, inclusive.
    """
    items: tuple[Item, ...] = ()
    arris_after: int | None = None
    knives: tuple[int, int] | None = None

    @property
    def thicknesses(self) -> list[float]:
        return [i.thickness for i in self.items]

    def inside_knives(self, index: int) -> bool:
        return self.knives is not None and self.knives[0] <= index <= self.knives[1]


@dataclass(frozen=True)
class Primary:
    left: Stack = field(default_factory=Stack)     # as written: outermost board first
    cant: float | None = None                      # None = live sawing
    right: Stack = field(default_factory=Stack)    # as written: board next to the cant first


@dataclass(frozen=True)
class Pattern:
    primary: Primary
    secondary: Stack

    @property
    def is_live(self) -> bool:
        return self.primary.cant is None


_ITEM = re.compile(r"(?:(\d+)\*)?(\d+(?:\.\d+)?)(?:[xX](\d+(?:\.\d+)?))?")
_TOKEN = re.compile(r"\s*(?:(?P<item>(?:\d+\*)?\d+(?:\.\d+)?(?:[xX]\d+(?:\.\d+)?)?)|(?P<mark>[,<>]))")


def _num(s: str) -> float:
    return float(s)


def _fmt(v: float) -> str:
    return f"{v:g}"


def parse_stack(text: str) -> Stack:
    items: list[Item] = []
    arris: int | None = None
    k_open: int | None = None
    k_close: int | None = None
    pos = 0
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise PatternError(f"cannot read pattern text at {text[pos:]!r}")
        pos = m.end()
        if m.group("item"):
            n, t, w = _ITEM.fullmatch(m.group("item")).groups()
            count = int(n) if n else 1
            if count < 1:
                raise PatternError("a board count must be at least 1")
            items.extend([Item(_num(t), _num(w) if w else None)] * count)
        else:
            mark = m.group("mark")
            if mark == ",":
                if arris is not None:
                    raise PatternError("only one arris blade (comma) is allowed")
                if not items:
                    raise PatternError("the arris comma must follow a board")
                arris = len(items) - 1
            elif mark == "<":
                if k_open is not None:
                    raise PatternError("only one '<' is allowed")
                k_open = len(items)
            else:
                if k_close is not None:
                    raise PatternError("only one '>' is allowed")
                k_close = len(items) - 1
    knives = None
    if k_open is not None or k_close is not None:
        if k_open is None or k_close is None:
            raise PatternError("riving knives need both '<' and '>'")
        if k_close < k_open:
            raise PatternError("riving knives must enclose at least one board")
        knives = (k_open, k_close)
    return Stack(tuple(items), arris, knives)


def serialise_stack(stack: Stack) -> str:
    """Collapse runs of equal neighbours to n*t. A marker always ends a run."""
    out: list[str] = []
    i, n = 0, len(stack.items)
    while i < n:
        j = i
        while (j + 1 < n and stack.items[j + 1] == stack.items[i]
               and stack.arris_after != j
               and not (stack.knives and (stack.knives[1] == j or stack.knives[0] == j + 1))):
            j += 1
        it = stack.items[i]
        tok = _fmt(it.thickness) + (f"x{_fmt(it.width)}" if it.width is not None else "")
        if j > i:
            tok = f"{j - i + 1}*{tok}"
        if stack.knives and stack.knives[0] == i:
            tok = "<" + tok
        if stack.knives and stack.knives[1] == j:
            tok += ">"
        sep = " "
        if stack.arris_after == j:
            tok += ","
            sep = ""          # Simsaw writes "25 3*38,25": no space after the comma
        out.append(tok + (sep if j + 1 < n else ""))
        i = j + 1
    return "".join(out).rstrip()


def parse_primary(text: str) -> Primary:
    text = text.strip()
    if "/" not in text:
        return Primary(left=parse_stack(text), cant=None, right=Stack())
    parts = text.split("/")
    if len(parts) != 3:
        raise PatternError("a cant pattern needs exactly two slashes, e.g. 25/114/25")
    left, cant, right = parts
    try:
        width = _num(cant.strip())
    except ValueError as e:
        raise PatternError(f"cant width {cant!r} is not a number") from e
    ls, rs = parse_stack(left), parse_stack(right)
    for s in (ls, rs):
        if s.arris_after is not None or s.knives is not None:
            raise PatternError("arris and riving-knife markers belong in the secondary pattern")
    return Primary(ls, width, rs)


def serialise_primary(p: Primary) -> str:
    if p.cant is None:
        return serialise_stack(p.left)
    return f"{serialise_stack(p.left)}/{_fmt(p.cant)}/{serialise_stack(p.right)}"


def parse(primary: str, secondary: str = "") -> Pattern:
    return Pattern(parse_primary(primary), parse_stack(secondary))


def serialise(pattern: Pattern) -> tuple[str, str]:
    return serialise_primary(pattern.primary), serialise_stack(pattern.secondary)
