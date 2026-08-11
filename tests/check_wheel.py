"""Fail a build when the wheel contradicts the Typing :: Typed classifier."""

from __future__ import annotations

import pathlib
import sys
import zipfile


def main(argv: list[str] | None = None) -> int:
    paths = [pathlib.Path(value) for value in (argv or sys.argv[1:])]
    if len(paths) != 1:
        print("usage: python tests/check_wheel.py DIST.whl", file=sys.stderr)
        return 1

    with zipfile.ZipFile(paths[0]) as wheel:
        names = set(wheel.namelist())
    marker = "evalint/py.typed"
    if marker not in names:
        print(f"{paths[0]}: missing {marker}", file=sys.stderr)
        return 1
    print(f"{paths[0]}: contains {marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
