"""The command line, exercised the way a person and a CI job would use it."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

import evalint.cli as cli_module
from evalint.cli import EXIT_PROBLEMS, main

HEALTHY = "item_id,text,system,score\n" + "".join(
    f"q{n:02d},question number {n} about a distinct topic,{system},{score}\n"
    for n in range(24)
    for system, score in (
        ("alpha", 1),
        ("beta", 1 if n % 4 else 0),
        ("gamma", 1 if n % 2 else 0),
        ("delta", 1 if n % 6 == 0 else 0),
    )
)


def _write(tmp_path, text, name="results.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_healthy_file_exits_zero(tmp_path, capsys):
    assert main([str(_write(tmp_path, HEALTHY))]) == 0
    assert "evalint" in capsys.readouterr().out


def test_an_unreadable_file_exits_one_with_the_reason(tmp_path, capsys):
    path = _write(tmp_path, "this is not eval results at all", "notes.txt")
    assert main([str(path)]) == 1
    assert "evalint:" in capsys.readouterr().err


def test_a_missing_file_exits_one(tmp_path, capsys):
    assert main([str(tmp_path / "nope.csv")]) == 1
    assert "cannot read" in capsys.readouterr().err


def test_invalid_utf8_exits_one_without_a_traceback(tmp_path, capsys):
    path = tmp_path / "invalid.csv"
    path.write_bytes(
        b"item_id,system,score\nquestion-\xff,alpha,1\nquestion-\xff,beta,0\n"
    )

    assert main([str(path)]) == 1
    error = capsys.readouterr().err
    assert "not valid UTF-8" in error
    assert "Traceback" not in error


def test_an_out_of_range_score_exits_one_without_a_plausible_report(tmp_path, capsys):
    path = tmp_path / "wrong-scale.csv"
    path.write_text(
        "item_id,system,score\nq1,alpha,0\nq1,beta,50\nq2,alpha,100\nq2,beta,0\n",
        encoding="utf-8",
    )

    assert main([str(path), "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[0, 1]" in captured.err
    assert "normalize" in captured.err
    assert "Traceback" not in captured.err


def test_a_noisy_set_exits_with_the_problem_status(tmp_path, capsys):
    """Distinct from 1, so a pipeline can tell "your eval set is unsound"
    from "the audit itself fell over"."""
    noisy = "item_id,system,score\n" + "".join(
        f"q{n},{system},{(n + i) % 2}\n"
        for n in range(12)
        for i, system in enumerate(("a", "b", "c", "d"))
    )
    code = main([str(_write(tmp_path, noisy))])
    assert code in (0, EXIT_PROBLEMS)
    if code == EXIT_PROBLEMS:
        assert "reliability" in capsys.readouterr().out


def test_fail_under_gates_on_reliability(tmp_path):
    path = _write(tmp_path, HEALTHY)
    assert main([str(path), "--fail-under", "0.0"]) == 0
    assert main([str(path), "--fail-under", "1.01"]) == EXIT_PROBLEMS


def test_fail_under_treats_unmeasurable_as_a_failure(tmp_path):
    """A gate that passed because reliability could not be computed would be
    worse than no gate."""
    two = "item_id,system,score\na,x,1\na,y,0\nb,x,1\nb,y,1\n"
    assert main([str(_write(tmp_path, two)), "--fail-under", "0.8"]) == EXIT_PROBLEMS


def test_json_output_parses(tmp_path, capsys):
    main([str(_write(tmp_path, HEALTHY)), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "evalint/audit-v1"
    assert payload["format"] == "csv"
    assert payload["summary"]["systems"] == 4


def test_json_coverage_includes_items_with_no_valid_scores(tmp_path, capsys):
    path = _write(
        tmp_path,
        "item_id,system,score\n"
        "q1,alpha,1\n"
        "q1,beta,0\n"
        "q2,alpha,n/a\n"
        "q2,beta,1\n"
        "q3,alpha,n/a\n"
        "q3,beta,n/a\n",
    )

    assert main([str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["items"] == 3
    assert payload["summary"]["observations"] == 3
    assert payload["summary"]["expected_observations"] == 6
    assert payload["summary"]["coverage"] == pytest.approx(0.5)


def test_invalid_repeat_metadata_is_a_user_error_not_a_traceback(tmp_path, capsys):
    payload = {
        "schema": "evalint/matrix-v1",
        "systems": ["alpha", "beta"],
        "items": [
            {
                "id": "q1",
                "scores": {"alpha": 1, "beta": 0},
                "repeats": {"alpha": 0},
            }
        ],
    }
    path = _write(tmp_path, json.dumps(payload), "bad-matrix.json")

    assert main([str(path)]) == 1
    error = capsys.readouterr().err
    assert "invalid evalint matrix" in error
    assert "Traceback" not in error


def test_save_reduced_writes_one_id_per_line(tmp_path, capsys):
    out = tmp_path / "keep.txt"
    main([str(_write(tmp_path, HEALTHY)), "--save-reduced", str(out)])
    ids = out.read_text(encoding="utf-8").split()
    assert ids
    assert all(i.startswith("q") for i in ids)
    capsys.readouterr()


def test_save_reduced_refuses_to_overwrite_an_input(tmp_path, capsys):
    source = _write(tmp_path, HEALTHY)
    before = source.read_bytes()

    assert main([str(source), "--save-reduced", str(source)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "input" in captured.err
    assert "refus" in captured.err
    assert "Traceback" not in captured.err
    assert source.read_bytes() == before


def test_save_reduced_refuses_a_hard_link_to_an_input(tmp_path, capsys):
    source = _write(tmp_path, HEALTHY)
    alias = tmp_path / "alias.csv"
    os.link(source, alias)
    before = source.read_bytes()

    assert main([str(source), "--save-reduced", str(alias)]) == 1
    assert "input" in capsys.readouterr().err
    assert source.read_bytes() == before
    assert alias.read_bytes() == before


def test_save_reduced_reports_write_errors_without_a_traceback(tmp_path, capsys):
    source = _write(tmp_path, HEALTHY)

    assert main([str(source), "--save-reduced", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot write" in captured.err
    assert "Traceback" not in captured.err


def test_save_reduced_preserves_an_existing_output_when_replace_fails(
    tmp_path, capsys, monkeypatch
):
    source = _write(tmp_path, HEALTHY)
    output = tmp_path / "keep.txt"
    output.write_text("previous output\n", encoding="utf-8")

    def fail_replace(_source, _destination):
        raise PermissionError("fixture denies replace")

    monkeypatch.setattr(cli_module.os, "replace", fail_replace)
    assert main([str(source), "--save-reduced", str(output)]) == 1
    captured = capsys.readouterr()
    assert "cannot write" in captured.err
    assert "Traceback" not in captured.err
    assert output.read_text(encoding="utf-8") == "previous output\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "keep.txt",
        "results.csv",
    ]


def test_ascii_output_has_no_wide_characters(tmp_path, capsys):
    main([str(_write(tmp_path, HEALTHY)), "--ascii", "--color", "never"])
    assert capsys.readouterr().out.isascii()


def test_color_never_emits_no_escapes(tmp_path, capsys):
    main([str(_write(tmp_path, HEALTHY)), "--color", "never"])
    assert "\x1b[" not in capsys.readouterr().out


def test_the_format_flag_is_accepted_before_and_after_the_path(tmp_path, capsys):
    """A flag that only works on one side of the filename is a flag that is
    broken for half the people who read the README."""
    path = _write(tmp_path, HEALTHY)
    assert main(["--format", "csv", str(path)]) == 0
    assert main([str(path), "--format", "csv"]) == 0
    capsys.readouterr()


def test_several_files_are_merged(tmp_path, capsys):
    """One file per model is how OpenAI evals and plenty of home-grown
    harnesses write results, and a single such file can never hold two
    systems to compare."""
    for model, flip in (("gpt-4o", 0), ("claude", 1), ("llama", 2)):
        _write(
            tmp_path,
            "item_id,system,score\n"
            + "".join(
                f"q{n:02d},{model},{1 if (n + flip) % 3 else 0}\n" for n in range(12)
            ),
            f"{model}.csv",
        )
    paths = [str(p) for p in sorted(tmp_path.glob("*.csv"))]
    assert main([*paths, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["systems"] == 3
    assert payload["summary"]["items"] == 12
    assert payload["source"].endswith("+2 more")


def test_repeat_runs_are_reported_but_not_counted_as_systems(tmp_path, capsys):
    paths = []
    for run in ("run-1", "run-2"):
        for model, flip in (("alpha", 0), ("beta", 1)):
            paths.append(
                _write(
                    tmp_path,
                    "item_id,system,score\n"
                    + "".join(
                        f"q{n:02d},{model},{1 if (n + flip) % 3 else 0}\n"
                        for n in range(12)
                    ),
                    f"{run}-{model}.csv",
                )
            )

    assert main([*map(str, paths), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["systems"] == 2
    assert payload["summary"]["runs"] == 4
    assert payload["summary"]["measurements"] == 48


def test_a_flag_between_two_filenames_still_works(tmp_path, capsys):
    """`evalint a.csv --json b.csv` is a thing people type, and plain
    parse_args rejects it once the positional takes several values."""
    for model in ("alpha", "beta"):
        _write(
            tmp_path,
            "item_id,system,score\n"
            + "".join(f"q{n},{model},{n % 2}\n" for n in range(8)),
            f"{model}.csv",
        )
    first = str(tmp_path / "alpha.csv")
    second = str(tmp_path / "beta.csv")
    assert main([first, "--json", second]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["systems"] == 2


def test_no_duplicates_and_no_reduce_are_honoured(tmp_path, capsys):
    path = _write(tmp_path, HEALTHY)
    main([str(path), "--no-duplicates", "--no-reduce", "--color", "never"])
    out = capsys.readouterr().out
    assert "near-duplicate" not in out
    assert "fewer calls per run" not in out


def test_similarity_threshold_reaches_the_detector(tmp_path, capsys):
    text = "item_id,text,system,score\n" + "".join(
        f"q{n:02d},a question about rewriting text for clarity {n},{s},{v}\n"
        for n in range(10)
        for s, v in (("a", 1), ("b", n % 2), ("c", 0))
    )
    path = _write(tmp_path, text)
    main([str(path), "--similarity", "0.99", "--color", "never"])
    strict = capsys.readouterr().out
    main([str(path), "--similarity", "0.5", "--color", "never"])
    loose = capsys.readouterr().out
    assert ("near-duplicate" in loose) or ("near-duplicate" not in strict)


def test_version_and_help_do_not_need_a_file(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--version"])
    assert caught.value.code == 0
    assert "evalint" in capsys.readouterr().out


def test_the_module_is_runnable_with_dash_m(tmp_path):
    """`python -m evalint` has to work: it is the invocation that needs no
    entry point on PATH."""
    path = _write(tmp_path, HEALTHY)
    result = subprocess.run(
        [sys.executable, "-m", "evalint", str(path), "--color", "never"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert "evalint" in result.stdout
