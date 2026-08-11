"""Keep data labels visible without letting them control a terminal."""

from __future__ import annotations

__all__ = ["escape_untrusted"]


def escape_untrusted(value: object, *, ascii_only: bool = False) -> str:
    """Render an untrusted value as inert, single-line terminal text.

    Python's ``ascii`` representation gives control and non-ASCII characters
    stable visible spellings such as ``\\x1b`` and ``\\u202e``. Printable
    Unicode remains unchanged unless the caller promised ASCII-only output.
    The original value is not mutated; structured JSON output can retain it.
    """

    rendered: list[str] = []
    for character in str(value):
        if character.isprintable() and (not ascii_only or character.isascii()):
            rendered.append(character)
        else:
            rendered.append(ascii(character)[1:-1])
    return "".join(rendered)
