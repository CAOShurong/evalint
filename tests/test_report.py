"""What the report says, and what it refuses to say."""

from __future__ import annotations

import json

from conftest import grid
from evalint.report import Palette, audit_matrix, render


def _text(matrix, **kwargs) -> str:
    audit = audit_matrix(matrix, **kwargs)
    return render(audit, Palette("never"))


def test_a_healthy_set_reports_its_reliability_in_words():
    matrix = grid({f"i-{n:02d}": "1110" if n % 3 else "1100" for n in range(20)})
    out = _text(matrix)
    assert "Measurement" in out
    assert "reliability" in out


def test_too_few_systems_says_so_instead_of_printing_a_number():
    out = _text(grid({"a": "10", "b": "01", "c": "11"}))
    assert "could not be computed" in out
    assert "not measurable" in out


def test_dead_weight_is_counted_where_somebody_will_see_it():
    matrix = grid(
        {
            "always": "1111",
            "never": "0000",
            "real-1": "1110",
            "real-2": "1100",
            "real-3": "1000",
        }
    )
    out = _text(matrix)
    assert "Paying for, not using" in out
    assert "every system passes" in out
    assert "no system passes" in out


def test_systems_within_the_measurement_error_are_marked_tied():
    """A leaderboard that prints 0.729 and 0.729 as first and second place is
    reporting a difference it cannot measure."""
    matrix = grid(
        {f"i-{n:02d}": "1100" if n % 2 else "1010" for n in range(12)},
        systems=["a", "b", "c", "d"],
    )
    out = _text(matrix)
    assert "Ranking" in out
    if "tied with the leader" in out:
        assert out.index("Ranking") < out.index("tied with the leader")


def test_broken_items_are_named_with_their_evidence():
    systems = [f"s{i:02d}" for i in range(12)]
    rows = {
        f"ok-{n:02d}": "".join("1" if r < 4 + n % 5 else "0" for r in range(12))
        for n in range(24)
    }
    rows["bad-0"] = "".join("1" if r >= 8 else "0" for r in range(12))
    out = _text(grid(rows, systems=systems))
    assert "Probably broken" in out
    assert "bad-0" in out
    assert "discrimination" in out
    assert "chance" in out


def test_an_inverted_but_unproven_item_is_separated_from_a_broken_one():
    """Four systems cannot tell a broken item from an unlucky one, and the
    report has to put those in different sections."""
    matrix = grid(
        {
            "unlucky": "0011",
            "a": "1110",
            "b": "1100",
            "c": "1000",
            "d": "1110",
        }
    )
    out = _text(matrix)
    assert "Inverted, but unproven" in out
    assert "cannot rule out luck" in out
    assert "Probably broken" not in out


def test_a_valid_high_pass_rate_is_not_called_a_units_mistake():
    """Binary scores can legitimately be all ones; their shape cannot reveal
    what scale the producer intended."""
    matrix = grid({f"i-{n}": "1111" for n in range(8)})
    out = _text(matrix)
    assert "units" not in out.lower()
    assert "rescale" not in out


def test_ascii_mode_emits_no_characters_a_dumb_terminal_cannot_show():
    matrix = grid({f"i-{n:02d}": "1110" if n % 3 else "1100" for n in range(12)})
    audit = audit_matrix(matrix)
    out = render(audit, Palette("never"), ascii_only=True)
    assert out.isascii()


def test_colour_is_off_when_asked_and_on_when_asked():
    matrix = grid({f"i-{n:02d}": "1110" if n % 3 else "1100" for n in range(12)})
    audit = audit_matrix(matrix)
    assert "\x1b[" not in render(audit, Palette("never"))
    assert "\x1b[" in render(audit, Palette("always"))


def test_no_color_environment_variable_is_honoured(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert Palette("auto").enabled is False


def test_the_json_payload_is_stable_and_serialisable():
    matrix = grid({f"i-{n:02d}": "1110" if n % 3 else "1100" for n in range(12)})
    payload = audit_matrix(matrix).as_dict()
    assert payload["schema"] == "evalint/audit-v1"
    # Must survive a round trip: this is what a CI job parses.
    assert json.loads(json.dumps(payload))["summary"]["items"] == 12
    assert {"summary", "ranking", "broken", "suspect", "reduction"} <= set(payload)


def test_duplicate_detection_can_be_turned_off():
    matrix = grid({"a": "1110", "b": "1110", "c": "1100", "d": "1000"})
    for item in matrix.items.values():
        item.text = "the very same question asked twice over"
    assert audit_matrix(matrix).clusters
    assert audit_matrix(matrix, detect_duplicates=False).clusters == []


def test_reduction_can_be_turned_off():
    matrix = grid({"a": "1111", "b": "1110", "c": "1100", "d": "1000"})
    assert audit_matrix(matrix, reduce=False).reduction is None
    assert audit_matrix(matrix).reduction is not None
