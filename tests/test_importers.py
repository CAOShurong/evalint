"""Reading the files people already have.

The rule these tests enforce: a file the tool does not understand must raise,
never produce an empty matrix. An empty matrix flows downstream into a report
with no problems in it, which reads as "your eval set is clean".
"""

from __future__ import annotations

import csv
import io
import json
import os
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


def _deep_json(depth: int = 12_000) -> str:
    nested = '{"child":' * depth + "0" + "}" * depth
    return (
        '[{"item_id":"q1","system":"alpha","score":1,"metadata":'
        + nested
        + '},{"item_id":"q1","system":"beta","score":0}]'
    )


# -- format detection is by shape, not by extension -----------------------


def test_detects_a_long_csv():
    text = "item_id,system,score\na,gpt,1\na,claude,0\n"
    assert detect_format(text) == "csv"


@pytest.mark.parametrize(
    "fmt",
    ("auto", "jsonl", "matrix", "promptfoo", "openai-evals"),
)
def test_deeply_nested_json_is_a_bounded_import_error(fmt):
    with pytest.raises(ImportError_) as caught:
        parse_text(_deep_json(), fmt)

    message = str(caught.value)
    assert "JSON nesting is too deep" in message
    assert len(message) < 200
    assert "child" not in message


def test_deeply_nested_json_detection_is_a_bounded_import_error():
    with pytest.raises(ImportError_) as caught:
        detect_format(_deep_json())

    assert str(caught.value).startswith("JSON nesting is too deep")


@pytest.mark.parametrize(
    "prompt",
    (
        "What is 2, plus 2?",
        "What is 2,\nplus 2?",
        'Say "hello", please',
    ),
)
def test_detects_quoted_delimiters_and_newlines_as_csv(prompt):
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("item_id", "text", "system", "score"))
    writer.writerow(("q1", prompt, "alpha", 1))
    writer.writerow(("q1", prompt, "beta", 0))

    text = stream.getvalue()
    assert detect_format(text) == "csv"
    matrix, fmt = load_text(text)
    assert fmt == "csv"
    assert matrix.items["q1"].text == prompt


def test_an_unterminated_csv_quote_fails_even_when_csv_is_forced():
    text = (
        "item_id,text,system,score\n"
        "q1,ordinary,alpha,1\n"
        "q1,ordinary,beta,0\n"
        'q2,"unterminated prompt,alpha,1\n'
    )

    assert detect_format(text) == "unknown"
    with pytest.raises(ImportError_) as caught:
        parse_text(text, "csv")

    message = str(caught.value)
    assert "CSV" in message
    assert "line" in message


def test_extra_csv_fields_fail_instead_of_leaking_an_internal_error():
    text = (
        "item_id,text,system,score\n"
        "q1,ordinary,alpha,1\n"
        "q1,ordinary,beta,0,unexpected\n"
    )

    with pytest.raises(ImportError_) as caught:
        parse_text(text, "csv")

    message = str(caught.value)
    assert "CSV" in message
    assert "extra field" in message
    assert "line" in message


@pytest.mark.parametrize(
    "text,duplicate",
    (
        (
            "item_id,system,score,score\nq1,alpha,1,0\nq1,beta,0,1\n",
            "score",
        ),
        (
            "item_id,alpha,alpha,beta\nq1,1,0,1\nq2,0,1,0\n",
            "alpha",
        ),
    ),
)
def test_duplicate_csv_headers_fail_before_values_are_overwritten(text, duplicate):
    with pytest.raises(ImportError_) as caught:
        parse_text(text, "csv")

    message = str(caught.value)
    assert "duplicate" in message
    assert duplicate in message
    assert "header" in message


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


def _current_promptfoo_jsonl() -> str:
    records = []
    for test_idx, case in enumerate(("q1", "q2")):
        for prompt_idx, (provider, score) in enumerate(
            (("openai:gpt-4o", 1), ("anthropic:claude", 0))
        ):
            records.append(
                {
                    "id": f"result-{test_idx}-{prompt_idx}",
                    "testIdx": test_idx,
                    "promptIdx": prompt_idx,
                    "testCase": {"vars": {"case": case}},
                    "provider": {"id": provider, "label": provider},
                    "prompt": {"raw": "Answer {{case}}"},
                    "success": bool(score),
                    "score": score,
                    "latencyMs": 10,
                    "namedScores": {},
                    "failureReason": 0 if score else 1,
                }
            )
    return "\n".join(json.dumps(record) for record in records) + "\n"


def test_detects_current_promptfoo_jsonl_results():
    assert detect_format(_current_promptfoo_jsonl()) == "promptfoo"


def test_promptfoo_jsonl_does_not_capture_generic_records_with_index_metadata():
    text = (
        '{"item":"q1","system":"alpha","score":1,"testIdx":0,"promptIdx":0}\n'
        '{"item":"q1","system":"beta","score":0,"testIdx":0,"promptIdx":1}\n'
    )

    assert detect_format(text) == "jsonl"


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


def test_a_late_malformed_jsonl_record_reports_its_line_and_column():
    lines = [
        '{"item_id":"q1","model":"alpha","score":1}',
        '{"item_id":"q1","model":"beta","score":0}',
        '{"item_id":"q2","model":"alpha","score":0}',
        '{"item_id":"q2","model":"beta","score":1}',
        '{"item_id":"q3","model":"alpha","score":1}',
        '{"item_id":"q3","model":"beta","score":',
    ]

    with pytest.raises(ImportError_) as caught:
        parse_text("\n".join(lines))
    message = str(caught.value)
    assert "JSONL" in message
    assert "line 6" in message
    assert "column" in message


@pytest.mark.parametrize(
    ("record", "problem"),
    (
        ({"system": "alpha", "score": 1}, "missing item identifier"),
        ({"item_id": "   ", "system": "alpha", "score": 1}, "blank item identifier"),
        ({"item_id": None, "system": "alpha", "score": 1}, "null item identifier"),
        ({"item_id": "q1", "score": 1}, "missing system identifier"),
        ({"item_id": "q1", "system": None, "score": 1}, "null system identifier"),
        ({"item_id": "q1", "system": "   ", "score": 1}, "blank system identifier"),
    ),
)
def test_generic_jsonl_refuses_missing_null_or_blank_identifiers(record, problem):
    text = "\n".join(
        (
            '{"item_id":"q1","system":"alpha","score":1}',
            json.dumps(record),
            '{"item_id":"q1","system":"beta","score":0}',
        )
    )

    with pytest.raises(ImportError_) as caught:
        parse_text(text, "jsonl")

    message = str(caught.value)
    assert "JSONL line 2" in message
    assert problem in message


def test_generic_json_array_refuses_a_non_object_record():
    text = json.dumps(
        [
            {"item_id": "q1", "system": "alpha", "score": 1},
            None,
            {"item_id": "q1", "system": "beta", "score": 0},
        ]
    )

    with pytest.raises(ImportError_) as caught:
        parse_text(text, "jsonl")

    message = str(caught.value)
    assert "JSON array record 2" in message
    assert "object" in message


def test_long_csv_refuses_a_blank_system_instead_of_inventing_one():
    text = "item_id,system,score\nq1,,1\nq1,beta,0\n"

    with pytest.raises(ImportError_) as caught:
        parse_text(text, "csv")

    message = str(caught.value)
    assert "CSV row ending near line 2" in message
    assert "blank system identifier" in message


def test_wide_csv_refuses_a_blank_item_instead_of_dropping_the_row():
    text = "item_id,alpha,beta\n,1,0\nq1,0,1\n"

    with pytest.raises(ImportError_) as caught:
        parse_text(text, "csv")

    message = str(caught.value)
    assert "CSV row ending near line 2" in message
    assert "blank item identifier" in message


@pytest.mark.parametrize("header", ("", "   "))
def test_wide_csv_refuses_a_scored_column_with_a_blank_system_header(header):
    text = f"item_id,{header},beta\nq1,1,0\nq2,0,1\n"

    with pytest.raises(ImportError_) as caught:
        parse_text(text, "csv")

    message = str(caught.value)
    assert "CSV row ending near line 2" in message
    assert "blank system identifier" in message


def test_nonblank_identifier_whitespace_is_preserved():
    text = "\n".join(
        (
            '{"item_id":" q1 ","system":" alpha ","score":1}',
            '{"item_id":" q1 ","system":" beta ","score":0}',
        )
    )

    matrix, _ = parse_text(text, "jsonl")

    assert matrix.item_ids == [" q1 "]
    assert matrix.systems == [" alpha ", " beta "]


def test_forced_promptfoo_reports_malformed_json_as_an_import_error():
    with pytest.raises(ImportError_) as caught:
        parse_text('{"results": [', "promptfoo")
    message = str(caught.value)
    assert "Promptfoo" in message
    assert "line 1" in message
    assert "column" in message


def test_openai_evals_does_not_skip_a_malformed_event_line():
    lines = [
        '{"spec":{"completion_fns":["alpha"]}}',
        '{"sample_id":"q1","type":"match","data":{"correct":1}}',
        '{"sample_id":"q2","type":"match","data":{"correct":',
    ]

    with pytest.raises(ImportError_) as caught:
        parse_text("\n".join(lines), "openai-evals")
    message = str(caught.value)
    assert "OpenAI Evals" in message
    assert "line 3" in message


@pytest.mark.parametrize(
    ("text", "fmt", "location"),
    (
        (
            '{"schema":"evalint/matrix-v2","schema":"evalint/matrix-v1",'
            '"systems":["alpha","beta"],"items":[{"id":"q1",'
            '"scores":{"alpha":1,"beta":0}}]}',
            "matrix",
            "invalid evalint matrix",
        ),
        (
            '[{"item_id":"q1","system":"alpha","score":1,"score":0},'
            '{"item_id":"q1","system":"beta","score":1}]',
            "jsonl",
            "invalid JSON array JSON",
        ),
        (
            '{"item_id":"q1","system":"alpha","score":1}\n'
            '{"item_id":"q1","system":"beta","score":1,"score":0}',
            "jsonl",
            "invalid JSONL JSON on line 2",
        ),
        (
            '{"results":[{"provider":"alpha","score":1,"score":0,'
            '"prompt":{"raw":"q1"}}]}',
            "promptfoo",
            "invalid Promptfoo JSON",
        ),
        (
            '{"spec":{"completion_fns":["alpha"]}}\n'
            '{"sample_id":"q1","type":"match",'
            '"data":{"correct":1,"correct":0}}',
            "openai-evals",
            "invalid OpenAI Evals JSON on line 2",
        ),
    ),
)
def test_json_readers_refuse_duplicate_object_members(text, fmt, location):
    with pytest.raises(ImportError_) as caught:
        parse_text(text, fmt)

    message = str(caught.value)
    assert location in message
    assert "duplicate object member" in message


def test_json_reader_allows_the_same_member_name_in_separate_objects():
    matrix, _ = parse_text(
        '[{"item_id":"q1","system":"alpha","score":1},'
        '{"item_id":"q1","system":"beta","score":0}]',
        "jsonl",
    )

    assert matrix.scores_for_system("alpha") == {"q1": 1.0}
    assert matrix.scores_for_system("beta") == {"q1": 0.0}


@pytest.mark.parametrize(
    ("text", "location"),
    (
        (
            '[{"item_id":"q1","system":"alpha",'
            '"grader":{"score":1},"metadata":{"score":0}},'
            '{"item_id":"q1","system":"beta","score":1}]',
            "JSON array record 1",
        ),
        (
            '[{"item_id":"q1","system":"alpha",'
            '"metadata":{"score":0},"grader":{"score":1}},'
            '{"item_id":"q1","system":"beta","score":1}]',
            "JSON array record 1",
        ),
        (
            '{"item_id":"q1","system":"alpha","score":1}\n'
            '{"item_id":"q1","system":"beta","score":0,'
            '"data":{"score":1}}',
            "JSONL line 2",
        ),
        (
            '[{"item_id":"q1","system":"alpha",'
            '"item":{"id":"q2"},"score":1},'
            '{"item_id":"q1","system":"beta","score":0}]',
            "JSON array record 1",
        ),
        (
            '[{"item_id":"q1","system":"alpha",'
            '"grader":{"score":true},"metadata":{"score":1}},'
            '{"item_id":"q1","system":"beta","score":0}]',
            "JSON array record 1",
        ),
        (
            '[{"item_id":"q1","system":"alpha","Score":1,"score":0},'
            '{"item_id":"q1","system":"beta","score":1}]',
            "JSON array record 1",
        ),
    ),
)
def test_generic_json_refuses_conflicting_nested_leaf_values(text, location):
    with pytest.raises(ImportError_) as caught:
        parse_text(text, "jsonl")

    message = str(caught.value)
    assert location in message
    assert "conflicting nested JSON field values" in message


def test_generic_json_allows_repeated_nested_leaf_values_when_identical():
    matrix, _ = parse_text(
        '[{"item_id":"q1","system":"alpha",'
        '"grader":{"score":1},"metadata":{"score":1}},'
        '{"item_id":"q1","system":"beta","score":0}]',
        "jsonl",
    )

    assert matrix.scores_for_system("alpha") == {"q1": 1.0}
    assert matrix.scores_for_system("beta") == {"q1": 0.0}


def test_generic_json_ignores_conflicts_between_unconsumed_nested_fields():
    matrix, _ = parse_text(
        '[{"item_id":"q1","system":"alpha","score":1,'
        '"grader":{"unused":1},"metadata":{"unused":0}},'
        '{"item_id":"q1","system":"beta","score":0}]',
        "jsonl",
    )

    assert matrix.scores_for_system("alpha") == {"q1": 1.0}
    assert matrix.scores_for_system("beta") == {"q1": 0.0}


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


@pytest.mark.parametrize(
    ("raw", "problem"),
    (
        (
            {
                "systems": ["alpha", "alpha", "beta"],
                "items": [
                    {"id": "q1", "scores": {"alpha": 1, "beta": 0}},
                ],
            },
            "duplicate system identifier",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": [
                    {"id": "q1", "scores": {"alpha": 1, "beta": 0}},
                    {"id": "q1", "scores": {"alpha": 0, "beta": 1}},
                ],
            },
            "duplicate item identifier",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": [
                    {"id": None, "scores": {"alpha": 1, "beta": 0}},
                ],
            },
            "null item identifier",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": [
                    {"scores": {"alpha": 1, "beta": 0}},
                ],
            },
            "missing item identifier",
        ),
        (
            {
                "systems": ["", "beta"],
                "items": [
                    {"id": "q1", "scores": {"": 1, "beta": 0}},
                ],
            },
            "blank system identifier",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": [
                    {"id": "q1", "scores": {"alpha": 1, "betaa": 0}},
                ],
            },
            "undeclared system identifier",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": [
                    {"id": 42, "scores": {"alpha": 1, "beta": 0}},
                ],
            },
            "item identifier must be a string",
        ),
        (
            {
                "systems": [42, "beta"],
                "items": [],
            },
            "system identifier must be a string",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": [
                    {"id": "   ", "scores": {"alpha": 1, "beta": 0}},
                ],
            },
            "blank item identifier",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": [
                    {"id": "q1", "scores": {"": 1, "beta": 0}},
                ],
            },
            "blank system identifier",
        ),
        (
            {
                "systems": "alpha",
                "items": [],
            },
            "systems must be an array",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": {"id": "q1"},
            },
            "items must be an array",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": [
                    {"id": "q1", "scores": [1, 0]},
                ],
            },
            "scores must be an object",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": [
                    {"id": "q1", "scores": None},
                ],
            },
            "scores must be an object",
        ),
        (
            {
                "systems": ["alpha", "beta"],
                "items": [
                    {"id": "q1", "scores": {}, "repeats": []},
                ],
            },
            "repeats must be an object",
        ),
    ),
)
def test_native_matrix_refuses_ambiguous_identifiers(raw, problem):
    raw["schema"] = "evalint/matrix-v1"

    with pytest.raises(ImportError_) as caught:
        parse_text(json.dumps(raw), "matrix")

    assert problem in str(caught.value)


@pytest.mark.parametrize(
    ("repeats", "scores", "problem"),
    (
        ({"alpha": 2.9}, {"alpha": 1, "beta": 0}, "positive integer"),
        ({"alpha": "3"}, {"alpha": 1, "beta": 0}, "positive integer"),
        ({"alpha": True}, {"alpha": 1, "beta": 0}, "positive integer"),
        ({"alpha": 0}, {"alpha": 1, "beta": 0}, "positive integer"),
        ({"alpha": float("nan")}, {"alpha": 1, "beta": 0}, "positive integer"),
        ({"": 2}, {"alpha": 1, "beta": 0}, "blank system identifier"),
        ({"typo": 99}, {"alpha": 1, "beta": 0}, "undeclared system"),
        ({"beta": 99}, {"alpha": 1}, "has no corresponding score"),
    ),
)
def test_native_matrix_refuses_lossy_repeat_metadata(repeats, scores, problem):
    raw = {
        "schema": "evalint/matrix-v1",
        "systems": ["alpha", "beta"],
        "items": [{"id": "q1", "scores": scores, "repeats": repeats}],
    }

    with pytest.raises(ImportError_) as caught:
        parse_text(json.dumps(raw), "matrix")

    assert problem in str(caught.value)


def test_native_matrix_accepts_integer_valued_json_repeat_numbers():
    raw = {
        "schema": "evalint/matrix-v1",
        "systems": ["alpha", "beta"],
        "items": [
            {
                "id": "q1",
                "scores": {"alpha": 1, "beta": 0},
                "repeats": {"alpha": 2.0},
            }
        ],
    }

    matrix, _ = parse_text(json.dumps(raw), "matrix")

    assert matrix.repetitions("q1", "alpha") == 2
    assert matrix.measurements == 3


@pytest.mark.parametrize(
    ("metadata", "problem"),
    (
        ({"text": None}, "text must be a string"),
        ({"text": 42}, "text must be a string"),
        ({"expected": None}, "expected must be a string"),
        ({"expected": 42}, "expected must be a string"),
        ({"tags": "safety"}, "tags must be an array"),
        ({"tags": {"safety": True}}, "tags must be an array"),
        ({"tags": None}, "tags must be an array"),
        ({"tags": ["safety", None]}, "tags[2] must be a string"),
        ({"tags": ["safety", 42]}, "tags[2] must be a string"),
    ),
)
def test_native_matrix_refuses_lossy_item_metadata(metadata, problem):
    raw = {
        "schema": "evalint/matrix-v1",
        "systems": ["alpha", "beta"],
        "items": [
            {
                "id": "q1",
                **metadata,
                "scores": {"alpha": 1, "beta": 0},
            }
        ],
    }

    with pytest.raises(ImportError_) as caught:
        parse_text(json.dumps(raw), "matrix")

    assert problem in str(caught.value)
    assert "matrix items[1]" in str(caught.value)


def test_native_matrix_accepts_omitted_and_explicit_empty_item_metadata():
    raw = {
        "schema": "evalint/matrix-v1",
        "systems": ["alpha", "beta"],
        "items": [
            {"id": "omitted", "scores": {"alpha": 1, "beta": 0}},
            {
                "id": "empty",
                "text": "",
                "expected": "",
                "tags": [],
                "scores": {"alpha": 0, "beta": 1},
            },
            {
                "id": "labeled",
                "text": "Question",
                "expected": "Answer",
                "tags": ["safety", "multilingual"],
                "scores": {"alpha": 1, "beta": 1},
            },
        ],
    }

    matrix, _ = parse_text(json.dumps(raw), "matrix")

    assert matrix.items["omitted"].text == ""
    assert matrix.items["omitted"].expected == ""
    assert matrix.items["omitted"].tags == ()
    assert matrix.items["empty"].text == ""
    assert matrix.items["empty"].expected == ""
    assert matrix.items["empty"].tags == ()
    assert matrix.items["labeled"].tags == ("safety", "multilingual")
    assert matrix.as_dict()["items"][2]["tags"] == ["safety", "multilingual"]


@pytest.mark.parametrize(
    "score",
    (
        True,
        False,
        "1",
        "0.25",
        None,
        [],
        {},
    ),
)
def test_native_matrix_refuses_non_numeric_json_scores(score):
    raw = {
        "schema": "evalint/matrix-v1",
        "systems": ["alpha", "beta"],
        "items": [
            {
                "id": "q1",
                "scores": {"alpha": score, "beta": 0},
            }
        ],
    }

    with pytest.raises(ImportError_) as caught:
        parse_text(json.dumps(raw), "matrix")

    assert "matrix items[1] score must be a JSON number" in str(caught.value)


@pytest.mark.parametrize("score", (-0.01, 1.01, float("nan"), float("inf")))
def test_native_matrix_bounds_invalid_numeric_scores_without_echoing_them(score):
    raw = {
        "schema": "evalint/matrix-v1",
        "systems": ["alpha", "beta"],
        "items": [
            {
                "id": "q1",
                "scores": {"alpha": score, "beta": 0},
            }
        ],
    }

    with pytest.raises(ImportError_) as caught:
        parse_text(json.dumps(raw), "matrix")

    assert "matrix items[1] score must be a finite JSON number in [0, 1]" in str(
        caught.value
    )
    assert repr(score) not in str(caught.value)


@pytest.mark.parametrize("score", (0, 0.0, 0.25, 1, 1.0))
def test_native_matrix_accepts_unit_json_numbers(score):
    raw = {
        "schema": "evalint/matrix-v1",
        "systems": ["alpha", "beta"],
        "items": [
            {
                "id": "q1",
                "scores": {"alpha": score, "beta": 0},
            }
        ],
    }

    matrix, _ = parse_text(json.dumps(raw), "matrix")

    assert matrix.score("q1", "alpha") == pytest.approx(float(score))


@pytest.mark.parametrize(
    ("schema_fields", "problem"),
    (
        ({}, "schema is missing"),
        ({"schema": None}, "schema is unsupported"),
        ({"schema": 1}, "schema is unsupported"),
        ({"schema": "evalint/matrix-v2"}, "schema is unsupported"),
    ),
)
def test_native_matrix_requires_its_exact_supported_schema(schema_fields, problem):
    raw = {
        **schema_fields,
        "systems": ["alpha", "beta"],
        "items": [{"id": "q1", "scores": {"alpha": 1, "beta": 0}}],
    }

    with pytest.raises(ImportError_) as caught:
        parse_text(json.dumps(raw), "matrix")

    assert problem in str(caught.value)
    assert "evalint/matrix-v1" in str(caught.value)


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


def test_a_wholly_unscored_long_form_item_still_counts_toward_coverage():
    matrix, _ = load_text(
        "item_id,system,score\n"
        "q1,alpha,1\n"
        "q1,beta,0\n"
        "q2,alpha,n/a\n"
        "q2,beta,1\n"
        "q3,alpha,n/a\n"
        "q3,beta,n/a\n"
    )

    assert matrix.item_ids == ["q1", "q2", "q3"]
    assert matrix.observations == 3
    assert matrix.density == pytest.approx(0.5)


def test_a_named_but_wholly_unscored_system_survives_parsing():
    matrix, _ = parse_text(
        "item_id,system,score\n"
        "q1,alpha,1\n"
        "q1,beta,n/a\n"
        "q1,gamma,0\n"
        "q2,alpha,0\n"
        "q2,beta,n/a\n"
        "q2,gamma,1\n"
    )

    assert matrix.systems == ["alpha", "beta", "gamma"]
    assert matrix.scores_for_system("beta") == {}


def test_promptfoo_keeps_a_test_case_when_its_graders_return_no_score():
    payload = {
        "results": [
            {
                "provider": "alpha",
                "testCase": {"vars": {"case": "q1"}},
                "score": 1,
            },
            {
                "provider": "beta",
                "testCase": {"vars": {"case": "q1"}},
                "score": 0,
            },
            {
                "provider": "alpha",
                "testCase": {"vars": {"case": "q2"}},
                "score": None,
            },
            {
                "provider": "beta",
                "testCase": {"vars": {"case": "q2"}},
                "score": None,
            },
        ]
    }

    matrix, fmt = load_text(json.dumps(payload))
    assert fmt == "promptfoo"
    assert len(matrix.items) == 2
    assert matrix.density == pytest.approx(0.5)


def test_promptfoo_preserves_a_provider_with_no_usable_scores():
    payload = {
        "results": [
            {
                "provider": "alpha",
                "testCase": {"vars": {"case": "q1"}},
                "score": 1,
            },
            {
                "provider": "silent-provider",
                "testCase": {"vars": {"case": "q1"}},
                "score": None,
            },
        ]
    }

    matrix, fmt = parse_text(json.dumps(payload))
    assert fmt == "promptfoo"
    assert matrix.systems == ["alpha", "silent-provider"]
    assert matrix.scores_for_system("silent-provider") == {}


def test_current_promptfoo_jsonl_output_is_read_automatically_and_when_forced():
    for requested_format in ("auto", "promptfoo"):
        matrix, fmt = load_text(_current_promptfoo_jsonl(), requested_format)

        assert fmt == "promptfoo"
        assert matrix.item_ids == ['{"case": "q1"}', '{"case": "q2"}']
        assert matrix.systems == ["openai:gpt-4o", "anthropic:claude"]
        assert matrix.observations == 4
        assert matrix.score('{"case": "q1"}', "openai:gpt-4o") == 1
        assert matrix.score('{"case": "q1"}', "anthropic:claude") == 0


def test_current_promptfoo_v3_json_results_remain_supported():
    payload = {
        "version": 3,
        "timestamp": "2026-08-12T00:00:00Z",
        "results": [
            json.loads(line) for line in _current_promptfoo_jsonl().splitlines()
        ],
        "prompts": [],
        "stats": {},
    }

    matrix, fmt = load_text(json.dumps(payload))

    assert fmt == "promptfoo"
    assert matrix.observations == 4


def test_promptfoo_jsonl_uses_test_index_when_memory_projections_strip_identity_text():
    records = []
    for test_idx in range(2):
        for prompt_idx, provider in enumerate(("alpha", "beta")):
            records.append(
                {
                    "testIdx": test_idx,
                    "promptIdx": prompt_idx,
                    "testCase": {},
                    "provider": {"id": provider},
                    "prompt": {},
                    "success": True,
                    "score": 1,
                }
            )
    text = "\n".join(json.dumps(record) for record in records)

    matrix, fmt = load_text(text)

    assert fmt == "promptfoo"
    assert matrix.item_ids == ["promptfoo:test:0", "promptfoo:test:1"]
    assert matrix.observations == 4


def test_malformed_promptfoo_jsonl_fails_at_the_physical_line():
    lines = _current_promptfoo_jsonl().splitlines()
    lines[1] = '{"testIdx":0,"promptIdx":1,"provider":'

    with pytest.raises(ImportError_) as caught:
        parse_text("\n".join(lines))

    message = str(caught.value)
    assert "Promptfoo JSONL" in message
    assert "line 2" in message
    assert "column" in message


def test_promptfoo_jsonl_rejects_duplicate_members_at_the_physical_line():
    lines = _current_promptfoo_jsonl().splitlines()
    lines[0] = lines[0].replace('"score": 1', '"score": 0, "score": 1')

    with pytest.raises(ImportError_) as caught:
        parse_text("\n".join(lines))

    message = str(caught.value)
    assert "Promptfoo JSONL" in message
    assert "line 1" in message
    assert "duplicate object member" in message


def test_promptfoo_jsonl_rejects_a_non_result_row_instead_of_returning_a_subset():
    lines = _current_promptfoo_jsonl().splitlines()
    lines[1] = '{"metadata":{"batch":"checkpoint"}}'

    with pytest.raises(ImportError_) as caught:
        parse_text("\n".join(lines))

    assert "Promptfoo JSONL line 2 is not an eval result" in str(caught.value)


def test_openai_evals_keeps_a_sample_when_the_grader_emits_no_score():
    events = [
        {"spec": {"completion_fns": ["alpha"]}},
        {"sample_id": "q1", "type": "match", "data": {"correct": 1}},
        {"sample_id": "q2", "type": "match", "data": {"prompt": "unscored"}},
    ]

    matrix, fmt = parse_text("\n".join(json.dumps(event) for event in events))
    assert fmt == "openai-evals"
    assert matrix.item_ids == ["q1", "q2"]
    assert matrix.observations == 1


def test_openai_evals_preserves_a_run_with_no_usable_scores():
    events = [
        {"spec": {"completion_fns": ["silent-run"]}},
        {"sample_id": "q1", "type": "match", "data": {"prompt": "unscored"}},
    ]

    matrix, fmt = parse_text("\n".join(json.dumps(event) for event in events))
    assert fmt == "openai-evals"
    assert matrix.systems == ["silent-run"]
    assert matrix.scores_for_system("silent-run") == {}


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


def test_the_same_input_path_cannot_be_counted_as_another_run(tmp_path):
    path = tmp_path / "results.csv"
    path.write_text("item_id,system,score\nq1,alpha,1\nq1,beta,0\n", encoding="utf-8")

    with pytest.raises(ImportError_) as caught:
        load_many([path, path])

    assert "duplicate input" in str(caught.value)
    assert "same physical file" in str(caught.value)


def test_a_hard_link_alias_cannot_be_counted_as_another_run(tmp_path):
    path = tmp_path / "results.csv"
    alias = tmp_path / "results-hardlink.csv"
    path.write_text("item_id,system,score\nq1,alpha,1\nq1,beta,0\n", encoding="utf-8")
    os.link(path, alias)

    with pytest.raises(ImportError_) as caught:
        load_many([path, alias])

    message = str(caught.value)
    assert str(path) in message
    assert str(alias) in message
    assert "same physical file" in message


def test_a_symbolic_link_alias_cannot_be_counted_as_another_run(tmp_path):
    path = tmp_path / "results.csv"
    alias = tmp_path / "results-symlink.csv"
    path.write_text("item_id,system,score\nq1,alpha,1\nq1,beta,0\n", encoding="utf-8")
    try:
        os.symlink(path, alias)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")

    with pytest.raises(ImportError_) as caught:
        load_many([path, alias])

    assert "same physical file" in str(caught.value)


def test_byte_identical_independent_run_files_remain_allowed(tmp_path):
    first = tmp_path / "run-1.csv"
    second = tmp_path / "run-2.csv"
    contents = "item_id,system,score\nq1,alpha,1\nq1,beta,0\n"
    first.write_text(contents, encoding="utf-8")
    second.write_text(contents, encoding="utf-8")

    matrix, _ = load_many([first, second])

    assert matrix.observations == 2
    assert matrix.measurements == 4
    assert matrix.runs == 4


def test_mixed_input_formats_have_order_independent_provenance(tmp_path):
    csv_path = tmp_path / "alpha.csv"
    jsonl_path = tmp_path / "beta.jsonl"
    csv_path.write_text(
        "item_id,system,score\nq1,alpha,1\nq2,alpha,0\n", encoding="utf-8"
    )
    jsonl_path.write_text(
        '{"item_id":"q1","system":"beta","score":0}\n'
        '{"item_id":"q2","system":"beta","score":1}\n',
        encoding="utf-8",
    )

    _, forward = load_many([csv_path, jsonl_path])
    _, reverse = load_many([jsonl_path, csv_path])

    assert forward == reverse == "mixed:csv,jsonl"


def test_merging_refuses_conflicting_text_for_the_same_item_id(tmp_path):
    first = tmp_path / "alpha.csv"
    second = tmp_path / "beta.csv"
    first.write_text(
        "item_id,text,expected,system,score\n"
        "q1,What is the capital of France?,Paris,alpha,1\n",
        encoding="utf-8",
    )
    second.write_text(
        "item_id,text,expected,system,score\n"
        "q1,What is the capital of Germany?,Berlin,beta,1\n",
        encoding="utf-8",
    )

    with pytest.raises(ImportError_) as caught:
        load_many([first, second])

    message = str(caught.value)
    assert str(first) in message
    assert str(second) in message
    assert "q1" in message
    assert "conflicting text" in message


def test_merging_refuses_conflicting_expected_answers(tmp_path):
    first = tmp_path / "alpha.csv"
    second = tmp_path / "beta.csv"
    first.write_text(
        "item_id,text,expected,system,score\nq1,Compute 2 + 2,4,alpha,1\n",
        encoding="utf-8",
    )
    second.write_text(
        "item_id,text,expected,system,score\nq1,Compute 2 + 2,5,beta,0\n",
        encoding="utf-8",
    )

    with pytest.raises(ImportError_) as caught:
        load_many([first, second])

    assert "conflicting expected" in str(caught.value)


def test_one_file_cannot_reuse_an_item_id_for_different_text(tmp_path):
    path = tmp_path / "drifted.csv"
    path.write_text(
        "item_id,text,system,score\n"
        "q1,What is the capital of France?,alpha,1\n"
        "q1,What is the capital of Germany?,beta,1\n",
        encoding="utf-8",
    )

    with pytest.raises(ImportError_) as caught:
        load(path)

    message = str(caught.value)
    assert str(path) in message
    assert "q1" in message
    assert "conflicting text" in message


def test_missing_text_can_be_filled_by_a_later_file(tmp_path):
    first = tmp_path / "alpha.csv"
    second = tmp_path / "beta.csv"
    first.write_text("item_id,system,score\nq1,alpha,1\n", encoding="utf-8")
    second.write_text(
        "item_id,text,system,score\nq1,Compute 2 + 2,beta,0\n",
        encoding="utf-8",
    )

    matrix, _ = load_many([first, second])

    assert matrix.items["q1"].text == "Compute 2 + 2"


def test_merging_does_not_drop_a_file_with_no_usable_scores(tmp_path):
    for system, scores in (
        ("alpha", (1, 0)),
        ("beta", ("n/a", "n/a")),
        ("gamma", (0, 1)),
    ):
        (tmp_path / f"{system}.csv").write_text(
            f"item_id,system,score\nq1,{system},{scores[0]}\nq2,{system},{scores[1]}\n",
            encoding="utf-8",
        )

    with pytest.raises(ImportError_) as caught:
        load_many(sorted(tmp_path.glob("*.csv")))
    message = str(caught.value)
    assert "beta" in message
    assert "no usable scores" in message


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
