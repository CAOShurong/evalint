"""Terminal-output encoding is separate from the data model."""

from evalint.terminal import escape_untrusted


def test_every_non_printable_character_gets_a_visible_spelling():
    raw = "line\r\n\ttab\bnull\x00esc\x1bdel\x7fc1\x85bidi\u202ezwj\u200d"

    escaped = escape_untrusted(raw)

    assert escaped == (
        r"line\r\n\ttab\x08null\x00esc\x1bdel\x7fc1\x85bidi\u202ezwj\u200d"
    )
    assert escaped.isprintable()


def test_printable_unicode_is_preserved_unless_ascii_was_promised():
    assert (
        escape_untrusted("mod\N{LATIN SMALL LETTER E WITH ACUTE}le")
        == "mod\N{LATIN SMALL LETTER E WITH ACUTE}le"
    )
    assert (
        escape_untrusted("mod\N{LATIN SMALL LETTER E WITH ACUTE}le", ascii_only=True)
        == r"mod\xe9le"
    )
