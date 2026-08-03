"""Near-duplicate detection, and the limits it admits to."""

from __future__ import annotations

import pytest

from evalint.dedupe import (
    EXACT_BELOW,
    find_duplicates,
    normalise,
    shingles,
    similarity,
)


def test_normalise_strips_what_is_not_a_difference():
    assert normalise("  Hello,   World!  ") == "hello world"
    assert normalise("Café") == normalise("Café")


def test_accents_are_kept_because_they_may_be_the_point():
    """In an eval set "resume" and "résumé" may be two different test cases."""
    assert normalise("résumé") != normalise("resume")


def test_shingles_of_a_short_string_still_produce_something():
    assert len(shingles("hi")) == 1
    assert shingles("") == set()


def test_similarity_is_one_for_identical_text_and_zero_for_disjoint():
    assert similarity("the same thing", "the same thing") == 1.0
    assert similarity("aaaaaaaaaa", "zzzzzzzzzz") == 0.0


def test_similarity_is_high_for_a_reworded_copy():
    left = (
        "Given an invoice about unit conversion: return the total as a number "
        "with no currency symbol attached to it."
    )
    right = left + " Answer concisely."
    assert similarity(left, right) > 0.8


def test_a_short_item_needs_more_overlap_to_clear_the_threshold():
    """Jaccard is a ratio, so a fixed edit costs more on a short item.

    Worth pinning rather than tuning around: an eval set of one-line prompts
    will have fewer duplicates found than one of paragraphs, and that is the
    honest behaviour of a surface-similarity check.
    """
    short = "Convert this total to a plain number."
    assert similarity(short, short + " Answer concisely.") < 0.8


def test_similarity_is_low_for_different_questions_on_one_topic():
    """The threshold has to separate these two cases, or the tool either
    misses real duplicates or accuses a whole topic of being one item."""
    left = "Given a support ticket about SQL generation: list the table names this touches."
    right = "Given a git diff about code review: name the file most likely to contain the bug."
    assert similarity(left, right) < 0.5


def test_a_chain_of_rephrasings_becomes_one_cluster():
    """A drifted into B and B into C. Three overlapping pairs is the wrong
    answer; one cluster of three is the right one."""
    texts = {
        "a": "Summarise what changed in this changelog, in under twenty words.",
        "b": "Summarise what changed in this changelog, in under twenty words please.",
        "c": "Summarise what changed in this changelog, in under twenty words.  ",
    }
    clusters = find_duplicates(texts)
    assert len(clusters) == 1
    assert clusters[0].size == 3
    assert clusters[0].keeper == "a"
    assert clusters[0].duplicates == ["b", "c"]


def test_the_keeper_is_stable_between_runs():
    """Dict order must not decide which item somebody deletes."""
    texts = {
        "z": "Extract every date and normalise it to ISO 8601 format now.",
        "a": "Extract every date and normalise it to ISO 8601 format now!",
    }
    assert find_duplicates(texts)[0].keeper == "a"
    assert find_duplicates(dict(reversed(list(texts.items()))))[0].keeper == "a"


def test_cluster_similarity_reports_the_weakest_link():
    texts = {
        "a": "Rewrite this for a customer who is already annoyed with us.",
        "b": "Rewrite this for a customer who is already annoyed with us!",
        "c": "Rewrite this for a customer who is already quite annoyed with us.",
    }
    cluster = find_duplicates(texts, threshold=0.7)[0]
    assert cluster.similarity < 1.0
    assert cluster.similarity == pytest.approx(
        min(
            similarity(texts["a"], texts["b"]),
            similarity(texts["a"], texts["c"]),
            similarity(texts["b"], texts["c"]),
        ),
        abs=0.2,
    )


def test_distinct_items_are_left_alone():
    texts = {
        "a": "Write a regex that matches an ISO 8601 timestamp.",
        "b": "Summarise this support ticket in one sentence.",
        "c": "Convert 14 stone 3 pounds to kilograms.",
    }
    assert find_duplicates(texts) == []


def test_a_semantic_duplicate_in_different_words_is_not_claimed():
    """The documented limit, pinned so it cannot be quietly overstated.

    These two ask the same thing and share almost no surface form. Detecting
    it needs semantics; the README says so, and this test is what keeps that
    sentence true.
    """
    texts = {
        "a": "What is the capital city of France?",
        "b": "Name the seat of government for the French republic.",
    }
    assert find_duplicates(texts) == []


def test_empty_and_missing_text_is_skipped_not_clustered():
    """Items with no text are not all duplicates of each other."""
    texts = {"a": "", "b": "   ", "c": "a real question about arithmetic"}
    assert find_duplicates(texts) == []


def test_the_minhash_path_agrees_with_the_exact_path():
    """Above the cutoff the tool switches to banded LSH. The two paths must
    find the same clusters, or the answer would depend on set size."""
    base = [
        f"Given a log line about topic {n}: name the file most likely at fault."
        for n in range(EXACT_BELOW + 40)
    ]
    texts = {f"i-{n:04d}": text for n, text in enumerate(base)}
    # Plant an unmistakable duplicate pair.
    texts["i-0000"] = "Extract every date from this receipt and normalise to ISO 8601."
    texts["i-0001"] = "Extract every date from this receipt and normalise to ISO 8601!"

    big = find_duplicates(texts)
    small = find_duplicates(dict(list(texts.items())[:100]))

    assert len(texts) >= EXACT_BELOW
    planted = [c for c in big if c.keeper == "i-0000"]
    assert planted and "i-0001" in planted[0].duplicates
    assert [c for c in small if c.keeper == "i-0000"]


def test_a_higher_threshold_finds_fewer_duplicates():
    texts = {
        "a": "Rewrite this paragraph so it is shorter and clearer.",
        "b": "Rewrite this paragraph so that it is shorter and much clearer.",
    }
    assert find_duplicates(texts, threshold=0.6)
    assert find_duplicates(texts, threshold=0.99) == []


def test_one_item_is_never_a_duplicate():
    assert find_duplicates({"a": "anything at all"}) == []
    assert find_duplicates({}) == []
