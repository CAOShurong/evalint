"""The table everything else is computed from."""

from __future__ import annotations

import math

from conftest import grid
from evalint.matrix import Item, Matrix


def test_missing_cells_are_absent_not_zero():
    """The distinction the whole tool rests on.

    A system that was not run on an item has no score. If that read as 0.0 the
    system would look like it failed, and every mean, variance and correlation
    below it would be wrong in the direction that most flatters whoever ran
    the eval on fewer items.
    """
    matrix = grid({"a": "1.0"}, systems=["x", "y", "z"])
    assert matrix.score("a", "y") is None
    assert matrix.scores_for_item("a") == {"x": 1.0, "z": 0.0}
    assert matrix.observations == 2


def test_system_mean_divides_by_what_was_measured():
    matrix = grid({"a": "11", "b": "1.", "c": "0."}, systems=["x", "y"])
    # x answered three items, scoring 1, 1, 0.
    assert matrix.system_mean("x") == 2 / 3
    # y answered one, and scored it. Its mean is over one item, not three.
    assert matrix.system_mean("y") == 1.0


def test_density_reports_how_much_of_the_grid_exists():
    matrix = grid({"a": "11", "b": "1."}, systems=["x", "y"])
    assert matrix.density == 0.75


def test_ranking_is_best_first_and_ties_break_by_name():
    matrix = grid({"a": "110", "b": "110"}, systems=["zeta", "alpha", "mid"])
    assert [name for name, _ in matrix.ranking()] == ["alpha", "zeta", "mid"]


def test_scores_outside_the_unit_range_are_clamped():
    """A grader emitting 0-100 must not silently corrupt every statistic."""
    matrix = Matrix()
    matrix.add_item(Item(id="a"))
    matrix.record("a", "x", 87.0)
    matrix.record("a", "y", -3.0)
    assert matrix.score("a", "x") == 1.0
    assert matrix.score("a", "y") == 0.0


def test_nan_scores_do_not_propagate():
    matrix = Matrix()
    matrix.add_item(Item(id="a"))
    matrix.record("a", "x", float("nan"))
    assert matrix.score("a", "x") == 0.0
    assert not math.isnan(matrix.system_mean("x"))


def test_adding_an_item_twice_keeps_the_richer_record():
    """Long-form files repeat the item on every row, and only some rows carry
    the prompt text. Keeping the first-seen record would lose it."""
    matrix = Matrix()
    matrix.add_item(Item(id="a"))
    matrix.add_item(Item(id="a", text="the question", expected="42"))
    assert matrix.items["a"].text == "the question"
    assert matrix.items["a"].expected == "42"


def test_subset_carries_scores_and_leaves_the_original_alone():
    matrix = grid({"a": "11", "b": "10", "c": "00"})
    smaller = matrix.subset(["a", "c"])
    assert list(smaller.items) == ["a", "c"]
    assert smaller.systems == matrix.systems
    assert smaller.score("a", "sys-0") == 1.0
    assert len(matrix.items) == 3


def test_subset_ignores_ids_that_are_not_there():
    matrix = grid({"a": "11"})
    assert list(matrix.subset(["a", "nope"]).items) == ["a"]


def test_round_trips_through_a_dict():
    matrix = grid({"a": "1.0", "b": "011"}, systems=["x", "y", "z"])
    matrix.items["a"].text = "hello"
    matrix.items["a"].tags = ("maths",)
    back = Matrix.from_dict(matrix.as_dict())
    assert back.as_dict() == matrix.as_dict()
    assert back.score("a", "y") is None
    assert back.items["a"].tags == ("maths",)
