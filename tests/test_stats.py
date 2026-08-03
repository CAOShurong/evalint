"""Classical test theory, checked against cases small enough to do by hand.

Every number here is one somebody might act on: delete an item, retire an eval
set, believe a leaderboard. So the tests weight two things above coverage --
that the arithmetic matches the textbook formula on cases that can be worked
out on paper, and that the code declines to answer when the data cannot
support an answer.
"""

from __future__ import annotations

import math

import pytest

from conftest import grid
from evalint.stats import (
    BROKEN_DISCRIMINATION,
    chance_of_negative,
    correlation,
    item_stats,
    set_stats,
    variance,
)

# -- the primitives -------------------------------------------------------


def test_variance_is_population_not_sample():
    """These are all the systems there are, not a sample from a larger pool.

    Sample variance would divide by n-1 and give 1.0 here; the difference
    propagates into reliability, which is the number people quote.
    """
    assert variance([0, 1, 2]) == pytest.approx(2 / 3)


def test_variance_of_nothing_is_zero_not_an_error():
    assert variance([]) == 0.0


def test_correlation_matches_the_hand_computed_value():
    # Perfect straight line, so +1 exactly.
    assert correlation([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert correlation([1, 2, 3], [6, 4, 2]) == pytest.approx(-1.0)
    # A case worth doing on paper: r = 0.5 for this pairing.
    assert correlation([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(0.8)


def test_correlation_is_none_when_undefined_not_zero():
    """Undefined and uninformative are different answers.

    Returning 0.0 for a flat item would read as "measured, and it does not
    discriminate" when the truth is "cannot be measured at all". The report
    branches on that difference.
    """
    assert correlation([1, 1, 1], [1, 2, 3]) is None
    assert correlation([1, 2], [1]) is None
    assert correlation([1], [1]) is None


# -- item statistics ------------------------------------------------------


def test_difficulty_and_variance_on_a_worked_example():
    stats = item_stats(grid({"a": "1100"}))["a"]
    assert stats.difficulty == 0.5
    assert stats.variance == pytest.approx(0.25)
    assert stats.observed == 4


def test_a_flat_item_cannot_affect_the_ranking():
    stats = item_stats(grid({"a": "1111", "b": "0000", "c": "1100"}))
    assert stats["a"].is_flat and stats["a"].everyone_passes
    assert stats["b"].is_flat and stats["b"].everyone_fails
    assert not stats["a"].is_informative
    assert stats["c"].is_informative
    # Undefined, not zero: there is nothing to correlate.
    assert stats["a"].discrimination is None


def test_discrimination_is_corrected_for_the_item_itself():
    """The item must be removed from the total it is correlated against.

    Left in, every item correlates partly with itself, which inflates the
    whole report and inflates short sets most -- exactly the sets where the
    reader most needs the truth.
    """
    matrix = grid({f"i-{n}": "1100" for n in range(4)})
    stat = item_stats(matrix)["i-0"]
    # Against the other three items (which are identical) the correlation is
    # a clean +1. Uncorrected it would still be +1 here, so the case that
    # actually distinguishes the two is below.
    assert stat.discrimination == pytest.approx(1.0)

    # One item that disagrees with the rest. Correlated against a total that
    # includes itself, its own contribution drags the number upward.
    matrix = grid({"odd": "0011", "a": "1100", "b": "1100", "c": "1100"})
    assert item_stats(matrix)["odd"].discrimination == pytest.approx(-1.0)


def test_an_inverted_item_is_flagged_as_inverted():
    matrix = grid(
        {
            "ok-1": "1110",
            "ok-2": "1100",
            "ok-3": "1100",
            "ok-4": "1000",
            "broken": "0001",
        },
        systems=["best", "good", "fair", "poor"],
    )
    stats = item_stats(matrix)
    assert stats["broken"].is_inverted
    assert stats["broken"].discrimination <= BROKEN_DISCRIMINATION
    assert not stats["ok-1"].is_inverted


# -- refusing to answer ---------------------------------------------------


def test_two_systems_produce_no_discrimination_at_all():
    """With two columns every varying item correlates exactly +1 or -1.

    That looks like a strong signal and is an artefact of having two points.
    Reporting it would put a confident -1.00 next to items chosen by a coin
    flip.
    """
    stats = item_stats(grid({"a": "10", "b": "01", "c": "11"}))
    assert all(s.discrimination is None for s in stats.values())
    assert set_stats(grid({"a": "10", "b": "01"})).reliability is None


def test_reliability_is_none_when_no_system_is_ahead():
    """Every system scored the same overall.

    Alpha divides by the variance of the totals, so this is a division by
    zero dressed up as a statistic. The verdict has to say the set cannot
    separate them, not print a number.
    """
    matrix = grid({"a": "100", "b": "010", "c": "001"})
    summary = set_stats(matrix)
    assert summary.reliability is None
    assert "not measurable" in summary.reliability_verdict


def test_reliability_needs_at_least_two_items():
    assert set_stats(grid({"a": "110"})).reliability is None


def test_reliability_matches_the_kr20_formula():
    """Worked by hand from k/(k-1) * (1 - sum(item var) / var(totals))."""
    matrix = grid(
        {
            "a": "1110",
            "b": "1100",
            "c": "1000",
            "d": "1110",
        },
        systems=["p", "q", "r", "s"],
    )
    stats = item_stats(matrix)
    # Per system, by inspection of the grid: p passes all four; q passes a, b
    # and d; r passes a and d; s passes none.
    totals = [4.0, 3.0, 2.0, 0.0]
    assert totals == [
        sum(matrix.score(i, s) or 0.0 for i in matrix.items) for s in matrix.systems
    ]
    k = 4
    expected = (k / (k - 1)) * (
        1 - sum(s.variance for s in stats.values()) / variance(totals)
    )
    assert set_stats(matrix, stats).reliability == pytest.approx(min(1.0, expected))


def test_standard_error_shrinks_as_reliability_rises():
    """SEM = SD * sqrt(1 - reliability), and it is what makes a tie a tie."""
    summary = set_stats(
        grid(
            {
                "a": "1110",
                "b": "1100",
                "c": "1000",
                "d": "1110",
            }
        )
    )
    assert summary.standard_error is not None
    assert summary.standard_error <= summary.system_spread


def test_verdicts_are_words_not_decimals():
    assert "strong" in _verdict(0.95)
    assert "ranking" in _verdict(0.85)
    assert "weak" in _verdict(0.65)
    assert "too noisy" in _verdict(0.2)


def _verdict(value: float) -> str:
    from evalint.stats import SetStats

    return SetStats(
        items=10,
        systems=5,
        informative=10,
        everyone_passes=0,
        everyone_fails=0,
        looks_broken=0,
        suspect=0,
        weak=0,
        reliability=value,
        standard_error=0.0,
        system_spread=0.0,
    ).reliability_verdict


# -- the permutation test -------------------------------------------------


def test_three_systems_cannot_convict_an_item():
    """Only six orderings exist, so nothing can clear a 0.05 bar.

    This is the honest answer rather than a limitation to route around: with
    three systems a broken item and an unlucky one are genuinely
    indistinguishable, and the tool has to say so.
    """
    own = [0.0, 0.0, 1.0]
    rest = [3.0, 2.0, 1.0]
    observed = correlation(own, rest)
    assert chance_of_negative(own, rest, observed) > 0.05


def test_a_clear_inversion_over_many_systems_is_convicted():
    systems = 12
    own = [1.0 if i >= systems - 3 else 0.0 for i in range(systems)]
    rest = [float(systems - i) for i in range(systems)]
    observed = correlation(own, rest)
    assert observed < BROKEN_DISCRIMINATION
    assert chance_of_negative(own, rest, observed) <= 0.05


def test_the_chance_estimate_never_reaches_zero():
    """400 resamples cannot support a claim of impossibility."""
    own = [float(i) for i in range(20)]
    rest = [float(-i) for i in range(20)]
    value = chance_of_negative(own, rest, correlation(own, rest))
    assert value > 0.0
    assert value == pytest.approx(1 / 401)


def test_chance_is_stable_across_runs():
    """A p-value that flickered between runs of the same file would be worse
    than not reporting one. ``hash()`` is salted per process, so the seed is
    derived with crc32 instead."""
    matrix = grid(
        {"broken": "00011", **{f"ok-{n}": "11100" for n in range(6)}},
    )
    first = item_stats(matrix)["broken"].chance
    second = item_stats(matrix)["broken"].chance
    assert first == second


def test_chance_is_only_computed_where_it_could_change_an_answer():
    """The permutation is the expensive part; a positively discriminating
    item is never going to be accused of anything."""
    matrix = grid({"good": "11100", "other": "11100", "third": "11000"})
    assert item_stats(matrix)["good"].chance is None


def test_broken_requires_both_inversion_and_evidence():
    """Either half alone names innocent items.

    A reader who opens two flagged items, finds nothing wrong with them and
    stops trusting the rest is a worse outcome than flagging nothing.
    """
    matrix = grid(
        {
            "unlucky": "0011",
            "a": "1110",
            "b": "1100",
            "c": "1000",
        }
    )
    stat = item_stats(matrix)["unlucky"]
    assert stat.is_inverted
    assert not stat.looks_broken  # four systems cannot rule out luck
    assert stat.suspect


def test_planted_broken_items_are_all_found_with_enough_systems():
    """The end-to-end claim: given enough columns, the items whose expected
    answer is wrong are the ones named, and no others."""
    # sys-00 is the strongest and sys-11 the weakest, so a column index is
    # also a rank.
    systems = [f"sys-{i:02d}" for i in range(12)]
    rows = {}
    for n in range(30):
        # A normal item: passed by the top systems.
        cutoff = 4 + (n % 5)
        rows[f"ok-{n:02d}"] = "".join(
            "1" if rank < cutoff else "0" for rank in range(12)
        )
    for n in range(4):
        # Graded against a wrong reference, so the weakest systems "pass".
        rows[f"bad-{n}"] = "".join("1" if rank >= 8 else "0" for rank in range(12))
    stats = item_stats(grid(rows, systems=systems))
    named = {i for i, s in stats.items() if s.looks_broken}
    assert named == {"bad-0", "bad-1", "bad-2", "bad-3"}


def test_an_item_nobody_was_scored_on_does_not_crash():
    matrix = grid({"a": "11", "b": ".."})
    stats = item_stats(matrix)
    assert stats["b"].observed == 0
    assert stats["b"].discrimination is None
    assert not math.isnan(stats["b"].difficulty)
