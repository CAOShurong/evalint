"""Reduction, and the verification that keeps it honest.

The failure mode this module exists to prevent is a confident "96% fewer
calls" printed next to a leaderboard that has quietly reversed. Every test
below is about that: the saving is only real if the answer survives it.
"""

from __future__ import annotations

import pytest

from conftest import grid
from evalint.dedupe import Cluster
from evalint.reduce import kendall_tau, reduce_set
from evalint.stats import item_stats


def _reduce(matrix, clusters=None):
    return reduce_set(matrix, item_stats(matrix), clusters)


# -- rank agreement -------------------------------------------------------


def test_tau_is_one_for_identical_orderings():
    assert kendall_tau(["a", "b", "c"], ["a", "b", "c"]) == 1.0


def test_tau_is_minus_one_for_a_reversal():
    assert kendall_tau(["c", "b", "a"], ["a", "b", "c"]) == -1.0


def test_tau_counts_the_pairs_that_survived():
    # One of three pairs swapped: (3 - 1) / 3.
    assert kendall_tau(["b", "a", "c"], ["a", "b", "c"]) == pytest.approx(1 / 3)


def test_tau_refuses_orderings_over_different_systems():
    assert kendall_tau(["a", "b"], ["a", "z"]) == 0.0


# -- layer one: provably inert -------------------------------------------


def test_flat_items_are_dropped_and_cannot_change_anything():
    matrix = grid(
        {
            "all-pass": "1111",
            "all-fail": "0000",
            "real-1": "1110",
            "real-2": "1100",
            "real-3": "1000",
        }
    )
    reduction = _reduce(matrix)
    assert reduction.inert == ["all-fail", "all-pass"]
    assert reduction.ranking_preserved
    assert reduction.tau == 1.0


def test_the_saving_is_a_fraction_of_the_original_set():
    matrix = grid({"a": "1111", "b": "1110", "c": "1100", "d": "1000"})
    reduction = _reduce(matrix)
    assert reduction.original_items == 4
    assert reduction.saving == reduction.dropped / 4


# -- layer two: duplicates, verified -------------------------------------


def test_duplicates_of_a_kept_item_are_dropped_when_the_ranking_holds():
    matrix = grid(
        {
            "a": "1110",
            "a-copy": "1110",
            "b": "1100",
            "c": "1000",
            "d": "1100",
        }
    )
    clusters = [Cluster(keeper="a", duplicates=["a-copy"], similarity=0.95)]
    reduction = _reduce(matrix, clusters)
    assert "a-copy" in reduction.redundant
    assert reduction.ranking_preserved


def test_a_duplicate_that_would_move_the_ranking_is_kept_with_a_note():
    """The bug this check was written for.

    Duplicate detection works on surface text. Two items can read alike and
    still be scored differently -- a templated pair where only the number
    changed is textually near-identical and genuinely tests different things.
    Dropping those moves the ranking, so the whole redundancy step rolls back
    rather than reporting a saving that is not real.
    """
    matrix = grid(
        {
            "a": "1100",
            # Textually a copy of a, but scored the other way round: dropping
            # it hands the lead to a different system.
            "a-copy": "0011",
            "b": "1000",
            "c": "0010",
        },
        systems=["w", "x", "y", "z"],
    )
    before = [name for name, _ in matrix.ranking()]
    clusters = [Cluster(keeper="a", duplicates=["a-copy"], similarity=0.98)]
    reduction = _reduce(matrix, clusters)

    assert reduction.redundant == []
    assert reduction.notes
    assert "not interchangeable" in reduction.notes[0]
    assert [name for name, _ in matrix.subset(reduction.kept).ranking()] == before


def test_a_cluster_is_never_emptied_entirely():
    """Dropping every member loses the question, not just the duplication."""
    matrix = grid(
        {
            "dup-1": "1110",
            "dup-2": "1110",
            "other": "1100",
            "third": "1000",
        }
    )
    clusters = [Cluster(keeper="dup-1", duplicates=["dup-2"], similarity=0.99)]
    reduction = _reduce(matrix, clusters)
    assert "dup-1" not in reduction.redundant


def test_duplicates_that_are_also_inert_do_not_count_twice():
    matrix = grid(
        {
            "flat-1": "1111",
            "flat-2": "1111",
            "real-1": "1110",
            "real-2": "1100",
            "real-3": "1000",
        }
    )
    clusters = [Cluster(keeper="flat-1", duplicates=["flat-2"], similarity=0.99)]
    reduction = _reduce(matrix, clusters)
    assert set(reduction.inert) == {"flat-1", "flat-2"}
    # Already gone as inert, so the redundancy layer has nothing left to say
    # about them, and neither layer counts them a second time.
    assert reduction.redundant == []
    layers = [reduction.inert, reduction.redundant, reduction.low_information]
    assert sum(len(layer) for layer in layers) == reduction.dropped
    assert len({i for layer in layers for i in layer}) == reduction.dropped


# -- layer three: low information, verified ------------------------------


def test_dropping_stops_at_the_first_item_the_ranking_needs():
    matrix = grid(
        {
            "a": "1111",
            "b": "1110",
            "c": "1100",
            "d": "1000",
            "e": "1110",
            "f": "1100",
        }
    )
    reduction = _reduce(matrix)
    assert reduction.ranking_preserved
    assert reduction.tau == 1.0
    # Whatever survived must actually reproduce the ordering.
    kept = matrix.subset(reduction.kept)
    assert [n for n, _ in kept.ranking()] == [n for n, _ in matrix.ranking()]


def test_reliability_is_not_traded_away_for_a_saving():
    """A cheaper set that measures worse is a downgrade, not a saving."""
    matrix = grid({f"i-{n}": "1110" if n % 2 else "1100" for n in range(20)})
    reduction = reduce_set(matrix, item_stats(matrix), None, max_reliability_loss=0.0)
    if reduction.reliability_before is not None:
        assert reduction.reliability_after is not None
        assert reduction.reliability_after >= reduction.reliability_before - 1e-9


def test_at_least_two_items_always_survive():
    """A one-item eval set is not a smaller version of the answer."""
    matrix = grid({"a": "1100", "b": "1100", "c": "1100"})
    reduction = _reduce(matrix)
    assert len(reduction.kept) >= 2


def test_the_reduced_set_is_reported_alongside_its_own_evidence():
    matrix = grid({"a": "1111", "b": "1110", "c": "1100", "d": "1000"})
    payload = _reduce(matrix).as_dict()
    assert payload["kept"] + payload["dropped"] == payload["original_items"]
    assert 0.0 <= payload["saving"] <= 1.0
    assert payload["ranking_preserved"] is True


def test_nothing_is_dropped_from_a_set_that_cannot_spare_it():
    """Every item pulls its weight, so the honest answer is "no saving"."""
    matrix = grid({"a": "1000", "b": "0100", "c": "0010", "d": "0001"})
    reduction = _reduce(matrix)
    assert reduction.dropped == 0
    assert reduction.kept == ["a", "b", "c", "d"]
