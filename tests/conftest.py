"""Shared builders.

Tests state matrices as a grid of pass/fail characters, because the thing
being verified is nearly always a statistical property of a *shape* -- an
inverted item, a flat one, a set with no spread -- and that shape is legible
in a grid and invisible in a list of dicts.
"""

from __future__ import annotations

import pytest

from evalint.matrix import Item, Matrix


def grid(rows: dict[str, str], systems: list[str] | None = None) -> Matrix:
    """Build a matrix from ``{item_id: "1011"}``, one character per system.

    ``.`` means the cell was not measured, which is different from a zero and
    is exercised deliberately -- treating a missing score as a failure is the
    most damaging thing this tool could get wrong.
    """
    width = len(next(iter(rows.values())))
    names = systems or [f"sys-{i}" for i in range(width)]
    matrix = Matrix()
    matrix.systems = list(names)
    for item_id, pattern in rows.items():
        matrix.add_item(Item(id=item_id, text=item_id))
        for name, char in zip(names, pattern):
            if char == ".":
                continue
            matrix.record(item_id, name, float(char))
    return matrix


@pytest.fixture
def separating() -> Matrix:
    """A well behaved set: every item agrees with the overall ordering."""
    return grid(
        {
            "easy-1": "1111",
            "easy-2": "1110",
            "mid-1": "1100",
            "mid-2": "1100",
            "hard-1": "1000",
            "hard-2": "1000",
        },
        systems=["best", "good", "fair", "poor"],
    )
