"""Distribution claims that must remain true after installation."""

from __future__ import annotations

import pathlib

import evalint


def test_inline_types_have_the_pep561_marker():
    marker = pathlib.Path(evalint.__file__).with_name("py.typed")
    assert marker.is_file(), "Typing :: Typed requires evalint/py.typed"
