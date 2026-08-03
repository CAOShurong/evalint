"""The example set in docs/, which is also what the README quotes.

Two jobs. First, the numbers in the README have to be reproducible, or the
documentation is a screenshot of a run nobody can repeat. Second, the example
has known defects planted in it at known positions, so it doubles as the
end-to-end accuracy check: everything planted should be found, and nothing
else should be accused.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from evalint.importers import load
from evalint.report import audit_matrix

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
EXAMPLE = DOCS / "example-results.csv"

#: Planted by docs/make_example.py, and asserted here so the two cannot drift.
TRIVIAL = range(0, 44)
IMPOSSIBLE = range(44, 56)
WRONG_ANSWER = range(56, 66)


@pytest.fixture(scope="module")
def audit():
    if not EXAMPLE.exists():
        pytest.skip("example not generated yet")
    matrix, _ = load(EXAMPLE)
    return audit_matrix(matrix, source=EXAMPLE.name)


def test_the_example_is_reproducible(tmp_path):
    """Regenerating must produce the file that is checked in, byte for byte.

    CI runs this. Without it the README's numbers slowly stop matching the
    code that produced them, and nobody notices because nothing fails.
    """
    if not EXAMPLE.exists():
        pytest.skip("example not generated yet")
    before = EXAMPLE.read_bytes()
    result = subprocess.run(
        [sys.executable, str(DOCS / "make_example.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert EXAMPLE.read_bytes() == before, (
        "docs/example-results.csv is stale; run docs/make_example.py and "
        "commit the result"
    )


def test_the_set_is_large_enough_to_support_its_own_claims(audit):
    assert audit.summary.items == 240
    assert audit.summary.systems == 8


def test_every_planted_wrong_answer_is_found(audit):
    named = {s.item_id for s in audit.broken()}
    planted = {f"item-{n:03d}" for n in WRONG_ANSWER}
    assert planted <= named


def test_no_healthy_item_is_accused(audit):
    """The expensive failure. A reader who opens a flagged item, finds
    nothing wrong and stops believing the rest has been actively harmed by
    the tool."""
    named = {s.item_id for s in audit.broken()}
    planted = {f"item-{n:03d}" for n in WRONG_ANSWER}
    assert named - planted == set()


def test_the_dead_weight_is_counted_exactly(audit):
    assert audit.summary.everyone_passes == len(TRIVIAL) + 2
    assert audit.summary.everyone_fails == len(IMPOSSIBLE)


def test_reliability_is_high_enough_for_the_readme_to_quote_it(audit):
    assert audit.summary.reliability is not None
    assert audit.summary.reliability > 0.85


def test_the_duplicates_are_found_without_swallowing_the_set(audit):
    """Templated eval items are textually near-identical to each other, so a
    surface-similarity check can cluster a whole set into one lump. The
    example is written to read like a real set, and this pins that: some
    duplicates, nowhere near all of it."""
    assert audit.duplicate_items > 20
    assert audit.duplicate_items < audit.summary.items // 2


def test_the_reduction_keeps_the_ranking(audit):
    reduction = audit.reduction
    assert reduction is not None
    assert reduction.ranking_preserved
    assert reduction.tau == 1.0
    assert reduction.saving > 0.2


def test_the_reduced_set_really_does_reproduce_the_ranking(audit):
    """Recomputed here rather than trusted, because the claim printed to the
    user is exactly this one."""
    full = [name for name, _ in audit.matrix.ranking()]
    kept = audit.matrix.subset(audit.reduction.kept)
    assert [name for name, _ in kept.ranking()] == full


def test_the_top_two_systems_are_reported_as_a_tie(audit):
    """They are 0.000 apart in the generated data, and the report has to say
    so rather than printing a first and a second place."""
    ranking = audit.matrix.ranking()
    gap = abs(ranking[0][1] - ranking[1][1])
    assert audit.summary.standard_error is not None
    assert gap < audit.summary.standard_error
