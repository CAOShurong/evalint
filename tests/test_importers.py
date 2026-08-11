"""Reading the files people already have.

The rule these tests enforce: a file the tool does not understand must raise,
never produce an empty matrix. An empty matrix flows downstream into a report
with no problems in it, which reads as "your eval set is clean".
"""

from __future__ import annotations

import json
import pathlib

import pytest

from evalint.importers import (
    ImportError_,
    detect_format,
    load,
    load_many,
    load_text,
    parse_text,
)

# -- format detection is by shape, not by extension -----------------------


def test_detects_a_long_csv():
    text = "item_id,system,score\na,gpt,1\na,claude,0\n"
    assert detect_format(text) == "csv"


def test_utf8_bom_before_the_first_header_is_accepted(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text(
        "item_id,system,score\nq1,alpha,1\nq1,beta,0\n",
        encoding="utf-8-sig",
    )

    matrix, fmt = load(path)
    assert fmt == "csv"
    assert matrix.item_ids == ["q1"]
    assert matrix.systems == ["alpha", "beta"]


def test_invalid_utf8_is_refused_instead_of_replacing_identifiers(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_bytes(
        b"item_id,system,score\nquestion-\xff,alpha,1\nquestion-\xff,beta,0\n"
    )

    with pytest.raises(ImportError_) as caught:
        load(path)
    message = str(caught.value)
    assert "not valid UTF-8" in message
    assert "byte" in message
    assert "re-export" in message


def test_detects_a_wide_csv():
    text = "item_id,gpt,claude\na,1,0\nb,0,1\n"
    assert detect_format(text) == "csv"


def test_detects_jsonl():
    text = '{"item":"a","model":"gpt","score":1}\n{"item":"a","model":"c","score":0}\n'
    assert detect_format(text) == "jsonl"


def test_detects_a_json_array_as_records():
    assert detect_format('[{"item":"a","model":"m","score":1}]') == "jsonl"


def test_detects_promptfoo_by_its_results_key():
    assert detect_format('{"results": [], "version": 3}') == "promptfoo"


def test_detects_openai_evals_by_its_spec_line():
    """The file starts with `{`, so the whole-file JSON branch sees it first.

    That branch used to answer "jsonl" and stop, which made the openai-evals
    reader unreachable by detection -- the format was supported in name only.
    """
    text = '{"spec": {"eval_name": "x", "completion_fns": ["gpt"]}}\n{"event_id": 1}\n'
    assert detect_format(text) == "openai-evals"


def test_detects_our_own_matrix_format():
    assert detect_format('{"schema": "evalint/matrix-v1", "systems": []}') == "matrix"


def test_an_unrecognised_file_is_called_unknown():
    assert detect_format("hello world, this is prose") == "unknown"
    assert detect_format("") == "unknown"


def test_broken_json_that_looks_like_jsonl_is_read_as_jsonl():
    text = '{"item":"a","model":"m","score":1}\n{"item":"b","model":"m","score":0}\n'
    assert detect_format(text) == "jsonl"


# -- an unreadable file must raise, never return nothing ------------------


def test_an_unknown_format_raises_rather_than_reporting_a_clean_set():
    with pytest.raises(ImportError_) as caught:
        load_text("just some prose, no columns at all")
    assert "--format" in str(caught.value)


def test_a_file_with_one_system_is_refused_with_a_reason():
    """Every statistic compares systems, so one column is not a small
    version of the answer -- it is no answer."""
    with pytest.raises(ImportError_) as caught:
        load_text("item_id,system,score\na,only-me,1\nb,only-me,0\n")
    message = str(caught.value)
    assert "only 1 system" in message
    assert "two models" in message
    # And it points at the valid way out without suggesting that correlated
    # repeats of the same model create independent evidence.
    assert "distinctly named models or prompt versions" in message
    assert "not counted as new systems" in message


def test_one_system_is_allowed_when_the_file_is_going_to_be_merged():
    matrix, fmt = parse_text("item_id,system,score\na,only-me,1\nb,only-me,0\n")
    assert fmt == "csv"
    assert matrix.systems == ["only-me"]


def test_a_readable_file_with_no_items_raises():
    with pytest.raises(ImportError_):
        load_text('{"schema": "evalint/matrix-v1", "systems": ["a", "b"]}')


def test_a_missing_file_raises_with_the_path():
    with pytest.raises(ImportError_) as caught:
        load(pathlib.Path("nowhere-at-all.csv"))
    assert "nowhere-at-all.csv" in str(caught.value)


# -- score coercion -------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", 1.0),
        ("0", 0.0),
        ("true", 1.0),
        ("PASS", 1.0),
        ("Failed", 0.0),
        ("0.75", 0.75),
        ("yes", 1.0),
        ("no", 0.0),
    ],
)
def test_whatever_the_grader_wrote_becomes_a_score(raw, expected):
    matrix, _ = load_text(f"item_id,system,score\na,x,{raw}\na,y,1\n")
    assert matrix.score("a", "x") == expected


def test_a_rubric_score_keeps_its_resolution():
    """Graded-by-judge evals are not pass/fail, and rounding them at the door
    would make every statistic coarser than the data."""
    matrix, _ = load_text("item_id,system,score\na,x,0.62\na,y,0.41\n")
    assert matrix.score("a", "x") == pytest.approx(0.62)


def test_an_unparseable_score_is_skipped_not_guessed():
    matrix, _ = load_text("item_id,system,score\na,x,1\na,y,0\nb,x,n/a\nb,y,1\n")
    assert matrix.score("b", "x") is None
    assert matrix.score("b", "y") == 1.0


@pytest.mark.parametrize("raw", ["1.01", "-0.01", "nan", "inf", "-inf"])
def test_a_score_outside_the_declared_unit_range_is_refused(raw):
    text = f"item_id,system,score\na,x,{raw}\na,y,1\n"

    with pytest.raises(ImportError_) as caught:
        load_text(text)
    message = str(caught.value)
    assert "finite" in message
    assert "[0, 1]" in message
    assert "normalize" in message


# -- the shapes themselves ------------------------------------------------


def test_a_long_csv_becomes_the_expected_matrix():
    matrix, fmt = load_text(
        "item_id,text,system,score\n"
        "q1,What is 2+2?,gpt,1\n"
        "q1,What is 2+2?,claude,1\n"
        "q2,Capital of France?,gpt,0\n"
        "q2,Capital of France?,claude,1\n"
    )
    assert fmt == "csv"
    assert matrix.systems == ["gpt", "claude"]
    assert matrix.items["q1"].text == "What is 2+2?"
    assert matrix.score("q2", "gpt") == 0.0


def test_a_wide_csv_treats_every_scoring_column_as_a_system():
    matrix, _ = load_text(
        "item_id,text,gpt-4o,claude,llama\n"
        "q1,adding numbers,1,1,0\n"
        "q2,naming capitals,0,1,0\n"
    )
    assert matrix.systems == ["gpt-4o", "claude", "llama"]
    assert matrix.items["q1"].text == "adding numbers"
    assert matrix.score("q2", "claude") == 1.0


def test_a_tab_separated_file_is_read():
    matrix, _ = load_text("item_id\tsystem\tscore\na\tx\t1\na\ty\t0\n")
    assert matrix.score("a", "x") == 1.0


def test_alternative_column_names_are_recognised():
    matrix, _ = load_text("test_id,model,passed\nt1,gpt,true\nt1,claude,false\n")
    assert matrix.systems == ["gpt", "claude"]
    assert matrix.score("t1", "claude") == 0.0


def test_jsonl_records_are_read():
    text = "\n".join(
        json.dumps(record)
        for record in [
            {"item_id": "a", "model": "gpt", "score": 1, "input": "add 2 and 2"},
            {"item_id": "a", "model": "claude", "score": 0, "input": "add 2 and 2"},
            {"item_id": "b", "model": "gpt", "score": 1, "input": "name a capital"},
            {"item_id": "b", "model": "claude", "score": 1, "input": "name a capital"},
        ]
    )
    matrix, fmt = load_text(text)
    assert fmt == "jsonl"
    assert matrix.items["a"].text == "add 2 and 2"
    assert matrix.observations == 4


def test_nested_fields_are_found_without_a_schema_per_tool():
    """Result files bury the interesting keys under `data` or `testCase`."""
    text = "\n".join(
        json.dumps(r)
        for r in [
            {
                "meta": {"item_id": "a"},
                "run": {"model": "gpt"},
                "data": {"correct": True},
            },
            {
                "meta": {"item_id": "a"},
                "run": {"model": "cl"},
                "data": {"correct": False},
            },
        ]
    )
    matrix, _ = load_text(text)
    assert matrix.score("a", "gpt") == 1.0
    assert matrix.score("a", "cl") == 0.0


def test_promptfoo_output_is_read():
    payload = {
        "version": 3,
        "results": {
            "results": [
                {
                    "provider": {"id": "openai:gpt-4o"},
                    "testCase": {"vars": {"question": "What is 2+2?"}},
                    "score": 1,
                },
                {
                    "provider": {"id": "anthropic:claude"},
                    "testCase": {"vars": {"question": "What is 2+2?"}},
                    "success": False,
                },
            ]
        },
    }
    matrix, fmt = load_text(json.dumps(payload))
    assert fmt == "promptfoo"
    assert set(matrix.systems) == {"openai:gpt-4o", "anthropic:claude"}
    assert len(matrix.items) == 1
    scores = list(matrix.scores_for_item(next(iter(matrix.items))).values())
    assert sorted(scores) == [0.0, 1.0]


def _evals_log(model: str, grades: dict[str, bool]) -> str:
    lines = [{"spec": {"eval_name": "maths", "completion_fns": [model]}}]
    for index, (sample, correct) in enumerate(grades.items(), start=1):
        lines.append(
            {
                "event_id": index,
                "sample_id": sample,
                "type": "match",
                "data": {"correct": correct},
            }
        )
    return "\n".join(json.dumps(line) for line in lines)


def test_openai_evals_events_are_read_and_the_run_names_the_system():
    text = _evals_log("gpt-4o", {"s1": True, "s2": False})
    matrix, fmt = parse_text(text, "openai-evals")
    assert fmt == "openai-evals"
    assert matrix.systems == ["gpt-4o"]
    assert matrix.score("s1", "gpt-4o") == 1.0


# -- merging several runs -------------------------------------------------


def test_several_openai_evals_logs_merge_into_a_comparable_set(tmp_path):
    """One log is one completion function, so a single file can never hold
    two systems. Without merging, the format would be readable and useless."""
    first = tmp_path / "gpt-4o.jsonl"
    second = tmp_path / "claude.jsonl"
    first.write_text(_evals_log("gpt-4o", {"s1": True, "s2": True}), encoding="utf-8")
    second.write_text(_evals_log("claude", {"s1": True, "s2": False}), encoding="utf-8")

    matrix, fmt = load_many([first, second])
    assert fmt == "openai-evals"
    assert sorted(matrix.systems) == ["claude", "gpt-4o"]
    assert list(matrix.items) == ["s1", "s2"]
    assert matrix.score("s2", "claude") == 0.0
    assert matrix.score("s2", "gpt-4o") == 1.0


def test_merging_does_not_invent_systems_from_repeat_runs(tmp_path):
    """Repeated runs improve a model's estimate; they are not new models.

    Counting correlated runs as independent systems is pseudoreplication: it
    makes item significance look stronger without adding an independent
    system. One logical model is therefore still incomparable on its own.
    """
    for name, grades in (
        ("run-1", {"s1": True, "s2": True}),
        ("run-2", {"s1": True, "s2": False}),
    ):
        (tmp_path / f"{name}.jsonl").write_text(
            _evals_log("gpt-4o", grades), encoding="utf-8"
        )

    with pytest.raises(ImportError_) as caught:
        load_many(sorted(tmp_path.glob("*.jsonl")))
    assert "only 1 system" in str(caught.value)
    assert "repeat runs" in str(caught.value).lower()


def test_repeat_runs_are_averaged_within_each_logical_system(tmp_path):
    for run, grades in (
        ("run-1", {"gpt": (1, 0), "claude": (0, 1)}),
        ("run-2", {"gpt": (0, 0), "claude": (1, 1)}),
    ):
        for model, scores in grades.items():
            (tmp_path / f"{run}-{model}.csv").write_text(
                "item_id,system,score\n"
                f"q1,{model},{scores[0]}\n"
                f"q2,{model},{scores[1]}\n",
                encoding="utf-8",
            )

    matrix, _ = load_many(sorted(tmp_path.glob("*.csv")))
    assert sorted(matrix.systems) == ["claude", "gpt"]
    assert matrix.score("q1", "gpt") == 0.5
    assert matrix.score("q1", "claude") == 0.5
    assert matrix.observations == 4
    assert matrix.measurements == 8
    assert matrix.runs == 4


def test_repeated_rows_are_averaged_instead_of_last_write_winning():
    matrix, _ = load_text(
        "item_id,system,score\nq1,gpt,1\nq1,gpt,0\nq1,claude,0\nq1,claude,0\n"
    )
    assert matrix.score("q1", "gpt") == 0.5
    assert matrix.measurements == 4
    assert matrix.runs == 4


def test_merging_one_csv_per_model(tmp_path):
    for model, second in (("gpt", "1"), ("claude", "0")):
        (tmp_path / f"{model}.csv").write_text(
            f"item_id,system,score\na,{model},1\nb,{model},{second}\n",
            encoding="utf-8",
        )
    matrix, _ = load_many(sorted(tmp_path.glob("*.csv")))
    assert sorted(matrix.systems) == ["claude", "gpt"]
    assert matrix.score("b", "claude") == 0.0


def test_one_run_split_across_files_stays_one_system(tmp_path):
    """The other reading of a repeated system name.

    Here the two files hold different items, so nothing collides: this is one
    run written in two pieces. Splitting it into two columns would invent a
    system and give each half the coverage.
    """
    (tmp_path / "part-1.csv").write_text(
        "item_id,system,score\nq1,gpt,1\nq1,claude,0\n", encoding="utf-8"
    )
    (tmp_path / "part-2.csv").write_text(
        "item_id,system,score\nq2,gpt,0\nq2,claude,1\n", encoding="utf-8"
    )
    matrix, _ = load_many(sorted(tmp_path.glob("*.csv")))
    assert sorted(matrix.systems) == ["claude", "gpt"]
    assert matrix.density == 1.0


def test_merging_still_refuses_when_the_pieces_add_up_to_one_system(tmp_path):
    for name, item in (("a", "q1"), ("b", "q2")):
        (tmp_path / f"{name}.csv").write_text(
            f"item_id,system,score\n{item},solo,1\n{item}x,solo,0\n",
            encoding="utf-8",
        )
    with pytest.raises(ImportError_) as caught:
        load_many(sorted(tmp_path.glob("*.csv")))
    assert "these files" in str(caught.value)


def test_the_matrix_format_round_trips_through_the_importer():
    original, _ = load_text("item_id,system,score\na,x,1\na,y,0\nb,x,0\nb,y,1\n")
    back, fmt = load_text(json.dumps(original.as_dict()))
    assert fmt == "matrix"
    assert back.as_dict() == original.as_dict()


def test_an_explicit_format_overrides_detection():
    """Detection is a guess; the flag is the reader's answer."""
    text = "item_id,system,score\na,x,1\na,y,0\n"
    matrix, fmt = load_text(text, "csv")
    assert fmt == "csv"
    assert matrix.observations == 2


def test_blank_rows_are_ignored():
    matrix, _ = load_text("item_id,system,score\na,x,1\n\n\na,y,0\n")
    assert matrix.observations == 2
