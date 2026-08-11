"""Reading the results people already have.

Nobody re-instruments a pipeline to try a tool. Whatever eval framework is
already in use has already written a file, and this reads it: promptfoo's
JSON, OpenAI evals' JSONL, a long or wide CSV, or a JSONL of records.

Detection is by shape rather than by filename, because everything in this
space writes `.json` and `.jsonl` and none of it is labelled. Each reader
declares what it recognises, they are tried in order of specificity, and the
one that matches says so -- so a file that nothing understands produces "I do
not recognise this", never a silently empty matrix that would read as a
flawless eval set.
"""

from __future__ import annotations

import csv
import io
import json
import os
import pathlib

from .matrix import NATIVE_SCHEMA, ConflictingItem, InvalidScore, Item, Matrix

__all__ = [
    "ImportError_",
    "detect_format",
    "load",
    "load_many",
    "load_text",
    "merge",
    "parse_text",
]


class ImportError_(Exception):
    """The file could not be understood as eval results."""


class _DuplicateJsonMember(ValueError):
    """A JSON object repeated a member name, making its meaning ambiguous."""


class _ConflictingFlattenedField(ValueError):
    """Distinct nested paths would expose one leaf name with different values."""


_JSON_DEPTH_ERROR = (
    "JSON nesting is too deep for this Python runtime; reduce the nesting "
    "or export a flatter supported format"
)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build one object while rejecting names a normal ``dict`` would lose."""
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            # Do not echo the name: imported fields can contain sensitive data.
            raise _DuplicateJsonMember("duplicate object member")
        result[name] = value
    return result


def _strict_json_loads(text: str):
    """Decode JSON without silently applying a last-member-wins policy."""
    try:
        return json.loads(text, object_pairs_hook=_unique_json_object)
    except RecursionError as exc:
        raise ImportError_(_JSON_DEPTH_ERROR) from exc


def _detection_json_loads(text: str):
    """Decode a shape probe while retaining a bounded recursion boundary."""
    try:
        return json.loads(text)
    except RecursionError as exc:
        raise ImportError_(_JSON_DEPTH_ERROR) from exc


#: Column names that mean "which eval case is this", most specific first.
ITEM_KEYS = (
    "item_id",
    "item",
    "test_id",
    "case_id",
    "example_id",
    "sample_id",
    "id",
    "question",
    "input",
    "prompt",
)
#: Column names that mean "which system produced this".
SYSTEM_KEYS = (
    "system",
    "model",
    "provider",
    "variant",
    "run",
    "candidate",
    "config",
)
#: Column names that mean "how well did it do".
SCORE_KEYS = (
    "score",
    "success",
    "passed",
    "pass",
    "correct",
    "result",
    "grade",
    "accuracy",
)
#: Column names carrying the prompt text, for duplicate detection.
TEXT_KEYS = ("text", "question", "input", "prompt", "query", "instruction")
EXPECTED_KEYS = ("expected", "expected_output", "reference", "answer", "target")
GENERIC_FIELD_KEYS = frozenset(
    key
    for keys in (ITEM_KEYS, SYSTEM_KEYS, SCORE_KEYS, TEXT_KEYS, EXPECTED_KEYS)
    for key in keys
)


def _as_score(value) -> float | None:
    """Coerce whatever the grader wrote into a score in [0, 1].

    Eval tools variously emit booleans, "PASS"/"FAIL", 0/1, and floats. All of
    them mean the same thing and all of them turn up in real files.
    """
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "pass", "passed", "yes", "correct", "success", "1"):
            return 1.0
        if lowered in ("false", "fail", "failed", "no", "incorrect", "error", "0"):
            return 0.0
        try:
            return float(lowered)
        except ValueError:
            return None
    return None


def _first(record: dict, keys) -> tuple[str, object] | None:
    for key in keys:
        for actual in record:
            if actual.lower() == key:
                return actual, record[actual]
    return None


def _required_identifier(
    field: tuple[str, object] | None,
    kind: str,
    location: str,
) -> str:
    """Return one present, non-null, nonblank identifier without normalising it."""
    if field is None:
        raise ImportError_(
            f"{location} has a missing {kind} identifier; every generic result "
            "record must name both its item and system"
        )
    value = field[1]
    if value is None:
        raise ImportError_(f"{location} has a null {kind} identifier")
    identifier = str(value)
    if not identifier.strip():
        raise ImportError_(f"{location} has a blank {kind} identifier")
    return identifier


def detect_format(text: str) -> str:
    """Name the shape of a results file: ``promptfoo``, ``openai-evals``,
    ``matrix``, ``jsonl``, ``csv``, or ``unknown``."""
    stripped = text.lstrip()
    if not stripped:
        return "unknown"

    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = _detection_json_loads(text)
        except ValueError:
            # A JSON-looking file that will not parse whole is line-delimited.
            # This branch is the one an OpenAI evals log takes -- its first
            # character is `{`, so the line-delimited test below would never
            # be reached, and the format would be supported in name only.
            return _jsonl_kind(text)
        if isinstance(data, dict):
            if data.get("schema") == NATIVE_SCHEMA:
                return "matrix"
            if "results" in data and isinstance(data.get("results"), (dict, list)):
                return "promptfoo"
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return "jsonl"
        return "unknown"

    if _looks_like_jsonl(text):
        return _jsonl_kind(text)

    if _looks_like_csv(text):
        return "csv"
    return "unknown"


def _jsonl_kind(text: str) -> str:
    """Tell an OpenAI evals event stream from ordinary JSONL records."""
    if not _looks_like_jsonl(text):
        return "unknown"
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            first = _detection_json_loads(line)
        except ValueError:
            return "unknown"
        if not isinstance(first, dict):
            return "jsonl"
        # OpenAI evals writes an event stream: a spec line, then one event per
        # sample with the grade inside `data`.
        if "event_id" in first or first.get("spec") is not None:
            return "openai-evals"
        return "jsonl"
    return "unknown"


def _looks_like_jsonl(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()][:5]
    if not lines:
        return False
    for line in lines:
        try:
            _detection_json_loads(line)
        except ValueError:
            return False
    return True


def _looks_like_csv(text: str) -> bool:
    """A header and at least one row, split the same way by the same character.

    A single line of prose containing a comma is not a CSV, and calling it one
    produces "found no eval items in it" instead of "I do not recognise this",
    which sends the reader looking for a problem in a file that was never the
    right kind of file.
    """
    for delimiter in (",", "\t", ";", "|"):
        rows: list[list[str]] = []
        reader = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
        try:
            for row in reader:
                if any(cell.strip() for cell in row):
                    rows.append(row)
                if len(rows) == 5:
                    break
        except csv.Error:
            continue
        if len(rows) < 2 or len(rows[0]) < 2:
            continue
        width = len(rows[0])
        if all(len(row) == width for row in rows[1:]):
            return True
    return False


def load(path: pathlib.Path, fmt: str = "auto") -> tuple[Matrix, str]:
    """Read one results file. Returns the matrix and the format that was used."""
    matrix, used = _parse_file(path, fmt)
    _require_comparable(matrix, [path])
    return matrix, used


def load_many(paths, fmt: str = "auto") -> tuple[Matrix, str]:
    """Read several results files and merge them into one matrix.

    Needed because some formats hold exactly one run per file. An OpenAI evals
    log is a single completion function's event stream, so on its own it can
    never contain two systems to compare -- reading one and stopping would
    mean the format was supported in name only. Merging is also the natural
    shape for anyone who exports one CSV per model.

    Item ids are assumed to mean the same thing across files, which is the
    point: the same eval set, run by different systems.
    """
    paths = list(paths)
    if len(paths) == 1:
        return load(paths[0], fmt)
    _reject_duplicate_inputs(paths)

    parts: list[tuple[str, Matrix]] = []
    used_formats: list[str] = []
    for path in paths:
        matrix, used = _parse_file(path, fmt)
        parts.append((str(path), matrix))
        used_formats.append(used)
    merged = merge(parts)
    _require_comparable(merged, paths)
    return merged, _format_summary(used_formats)


def _reject_duplicate_inputs(paths: list[pathlib.Path]) -> None:
    """Refuse path aliases that would count one physical file more than once."""
    accepted: dict[tuple[object, ...], pathlib.Path] = {}
    for path in paths:
        try:
            metadata = path.stat()
        except OSError:
            # Preserve a useful duplicate error for repeated relative and
            # absolute spellings even when the eventual read will fail.
            identity: tuple[object, ...] = (
                "path",
                os.path.normcase(os.path.abspath(path)),
            )
        else:
            # This is the device/inode identity used by os.path.samefile, but
            # cached so a large batch needs one metadata read per path rather
            # than a quadratic number of samefile/stat calls.
            identity = ("file", metadata.st_dev, metadata.st_ino)
        earlier = accepted.get(identity)
        if earlier is not None:
            raise ImportError_(
                f"duplicate input {path}: it refers to the same physical file "
                f"as {earlier}; pass each result file once"
            )
        accepted[identity] = path


def _parse_file(path: pathlib.Path, fmt: str) -> tuple[Matrix, str]:
    """Parse one readable file while retaining its identity in diagnostics."""
    text = _read_file(path)
    try:
        return parse_text(text, fmt)
    except ImportError_ as exc:
        raise ImportError_(f"{path}: {exc}") from exc


def _format_summary(formats: list[str]) -> str:
    """Describe every detected input format without depending on path order."""
    unique = sorted(set(formats))
    if len(unique) == 1:
        return unique[0]
    return f"mixed:{','.join(unique)}"


def parse_text(text: str, fmt: str = "auto") -> tuple[Matrix, str]:
    """Turn one file's text into a matrix, without requiring it to be complete.

    Separate from :func:`load_text` because a single file is allowed to hold a
    single system when it is going to be merged with others.
    """
    # Excel and other Windows tools commonly prefix UTF-8 CSV with a byte
    # order mark. File reads remove its byte form through ``utf-8-sig``; this
    # handles callers of the string API with the same semantics.
    if text.startswith("\ufeff"):
        text = text[1:]
    if fmt == "auto":
        fmt = detect_format(text)
    reader = READERS.get(fmt)
    if reader is None:
        raise ImportError_(
            "could not recognise this file as eval results; pass --format to "
            f"say what it is (one of: {', '.join(sorted(READERS))})"
        )
    try:
        matrix = reader(text)
    except (ConflictingItem, InvalidScore) as exc:
        raise ImportError_(str(exc)) from exc
    if not matrix.items:
        raise ImportError_(f"read the file as {fmt}, but found no eval items in it")
    return matrix, fmt


def load_text(text: str, fmt: str = "auto") -> tuple[Matrix, str]:
    """Read results from a string. The text must be complete on its own."""
    matrix, used = parse_text(text, fmt)
    _require_comparable(matrix, None)
    return matrix, used


def merge(parts: list[tuple[str, Matrix]]) -> Matrix:
    """Combine several matrices into one.

    A repeated ``(item, system)`` cell is another measurement of the same
    logical system. It is averaged with the earlier value and its repetition
    count is retained. Treating the file name as a new system would be
    pseudoreplication: repeated stochastic runs are correlated and cannot add
    independent evidence to the item-level permutation test.

    Disjoint files with the same system name still compose into one column,
    so a run split across files keeps its coverage. Distinct models or prompt
    versions must carry distinct system names in the source data.
    """
    out = Matrix()
    origins: dict[str, str] = {}
    for source, matrix in parts:
        for item in matrix.items.values():
            try:
                out.add_item(item)
            except ConflictingItem as exc:
                first_source = origins.get(item.id)
                first_note = (
                    f"; first seen in {first_source}"
                    if first_source is not None
                    else ""
                )
                raise ImportError_(f"{source}: {exc}{first_note}") from exc
            origins.setdefault(item.id, source)
        for system in matrix.systems:
            out.add_system(system)
            for item_id, score in matrix.scores_for_system(system).items():
                out.record(
                    item_id,
                    system,
                    score,
                    repetitions=matrix.repetitions(item_id, system),
                )
    return out


def _read_file(path: pathlib.Path) -> str:
    try:
        # ``utf-8-sig`` is strict UTF-8 with one compatibility feature: it
        # consumes an optional leading UTF-8 BOM. Never use replacement here.
        # A changed item or system id can merge records and corrupt every
        # statistic downstream while still producing a plausible report.
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportError_(
            f"cannot read {path}: not valid UTF-8 near byte {exc.start}; "
            "re-export it as UTF-8 (with or without a BOM)"
        ) from exc
    except OSError as exc:
        raise ImportError_(f"cannot read {path}: {exc}") from exc


def _require_comparable(matrix: Matrix, paths) -> None:
    unscored = [
        system for system in matrix.systems if not matrix.scores_for_system(system)
    ]
    if unscored:
        names = ", ".join(repr(system) for system in unscored)
        noun = "system" if len(unscored) == 1 else "systems"
        raise ImportError_(
            f"found no usable scores for {noun} {names}. EvalInt will not hide "
            "an explicitly named system or rank a wholly unmeasured system as "
            "zero. Check grader/provider errors and the source score fields."
        )
    if len(matrix.systems) >= 2:
        return
    where = "this file" if not paths or len(paths) == 1 else "these files"
    hint = (
        ""
        if paths and len(paths) > 1
        else " Pass results for at least two distinctly named models or prompt"
        " versions. Repeat runs of one system are averaged, not counted as new"
        " systems."
    )
    raise ImportError_(
        f"found only {len(matrix.systems)} system in {where}. Every statistic "
        "here compares systems against each other, so at least two are needed "
        "-- two models or two prompt versions. Repeat runs improve each "
        "system's estimate but are not independent systems." + hint
    )


def _read_matrix(text: str) -> Matrix:
    try:
        raw = _strict_json_loads(text)
        if not isinstance(raw, dict):
            raise ValueError("the matrix root must be an object")
        return Matrix.from_dict(raw)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ImportError_(f"invalid evalint matrix: {exc}") from exc


def _json_document(text: str, label: str):
    """Decode one JSON document with a bounded, user-facing location."""
    try:
        return _strict_json_loads(text)
    except _DuplicateJsonMember as exc:
        raise ImportError_(f"invalid {label} JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ImportError_(
            f"invalid {label} JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def _json_line(line: str, line_number: int, label: str):
    """Decode one JSONL record without exposing a Python traceback."""
    try:
        return _strict_json_loads(line)
    except _DuplicateJsonMember as exc:
        raise ImportError_(
            f"invalid {label} JSON on line {line_number}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ImportError_(
            f"invalid {label} JSON on line {line_number}, column {exc.colno}: {exc.msg}"
        ) from exc


def _read_records(text: str) -> Matrix:
    """A JSONL file, or a JSON array, of flat records."""
    stripped = text.lstrip()
    if stripped.startswith("["):
        records = _json_document(text, "JSON array")
        if not isinstance(records, list):
            raise ImportError_("invalid JSON array: the root must be an array")
        locations = [
            f"JSON array record {record_number}"
            for record_number in range(1, len(records) + 1)
        ]
    else:
        records = []
        locations = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            records.append(_json_line(line, line_number, "JSONL"))
            locations.append(f"JSONL line {line_number}")
    return _from_records(records, locations)


def _from_records(records: list[object], locations: list[str] | None = None) -> Matrix:
    """Long-form records: one row per (item, system) pair."""
    matrix = Matrix()
    for record_number, record in enumerate(records, start=1):
        location = (
            locations[record_number - 1]
            if locations is not None
            else f"record {record_number}"
        )
        if not isinstance(record, dict):
            raise ImportError_(f"{location} must be a JSON object")
        try:
            flat = _flatten(record)
        except _ConflictingFlattenedField as exc:
            raise ImportError_(
                f"{location} has conflicting nested JSON field values; "
                "use one unambiguous value or a schema-specific format"
            ) from exc
        item_key = _first(flat, ITEM_KEYS)
        system_key = _first(flat, SYSTEM_KEYS)
        score_key = _first(flat, SCORE_KEYS)
        text_key = _first(flat, TEXT_KEYS)
        expected_key = _first(flat, EXPECTED_KEYS)
        item_id = _required_identifier(item_key, "item", location)
        system = _required_identifier(system_key, "system", location)
        matrix.add_item(
            Item(
                id=item_id,
                text=str(text_key[1]) if text_key else str(item_key[1]),
                expected=str(expected_key[1]) if expected_key else "",
            )
        )
        matrix.add_system(system)
        if score_key is None:
            continue
        score = _as_score(score_key[1])
        if score is None:
            continue
        matrix.record(item_id, system, score)
    return matrix


def _flatten(
    record: dict,
    prefix: str = "",
    depth: int = 0,
    _out=None,
    _recognized=None,
) -> dict:
    """One level of nesting folded into ``parent_child`` keys.

    Result files nest the interesting fields one or two levels down -- under
    ``data``, ``testCase``, ``metadata`` -- and flattening lets the same key
    matching work on all of them without a schema per tool.
    """
    if _out is None:
        _out = {}
    if _recognized is None:
        _recognized = {}
    if depth > 2:
        return _out
    for key, value in record.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            _flatten(value, f"{name}_", depth + 1, _out, _recognized)
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            _set_flattened_field(_out, _recognized, name, value)
            # Also expose the bare leaf name, so `data_correct` matches the
            # `correct` key without needing to know it was nested.
            _set_flattened_field(_out, _recognized, key, value)
    return _out


def _set_flattened_field(out: dict, recognized: dict, name: str, value) -> None:
    """Reject conflicts only for names the generic importer may consume."""
    canonical = name.lower()
    if canonical in GENERIC_FIELD_KEYS:
        if canonical in recognized:
            existing = recognized[canonical]
            if type(existing) is not type(value) or existing != value:
                raise _ConflictingFlattenedField
        else:
            recognized[canonical] = value
    if name in out:
        return
    out[name] = value


def _read_promptfoo(text: str) -> Matrix:
    """promptfoo's eval JSON: results, each with a provider and a test case."""
    data = _json_document(text, "Promptfoo")
    if not isinstance(data, dict):
        raise ImportError_("invalid Promptfoo JSON: the root must be an object")
    results = data.get("results")
    if isinstance(results, dict):
        results = results.get("results", [])
    matrix = Matrix()
    for entry in results or []:
        if not isinstance(entry, dict):
            continue
        provider = entry.get("provider")
        system = (
            provider.get("id") or provider.get("label")
            if isinstance(provider, dict)
            else provider
        )
        case = entry.get("testCase") or entry.get("test") or {}
        vars_ = case.get("vars") if isinstance(case, dict) else None
        item_id = None
        prompt_text = ""
        if isinstance(vars_, dict) and vars_:
            # promptfoo identifies a case by its variables, not by an id.
            item_id = json.dumps(vars_, sort_keys=True)
            prompt_text = " ".join(str(v) for v in vars_.values())
        if item_id is None:
            prompt = entry.get("prompt")
            if isinstance(prompt, dict):
                prompt_text = str(prompt.get("raw") or prompt.get("label") or "")
            item_id = prompt_text
        if not system or not item_id:
            continue
        matrix.add_item(Item(id=str(item_id), text=prompt_text))
        matrix.add_system(str(system))
        score = entry.get("score")
        if score is None:
            score = entry.get("success")
        score = _as_score(score)
        if score is None:
            continue
        matrix.record(str(item_id), str(system), score)
    return matrix


def _read_openai_evals(text: str) -> Matrix:
    """OpenAI evals' event stream: a spec line, then one event per sample."""
    matrix = Matrix()
    system = "run"
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        event = _json_line(line, line_number, "OpenAI Evals")
        if not isinstance(event, dict):
            continue
        spec = event.get("spec")
        if isinstance(spec, dict):
            system = str(
                spec.get("completion_fns", ["run"])[0]
                if spec.get("completion_fns")
                else spec.get("eval_name", "run")
            )
            continue
        if event.get("type") not in ("match", "metrics", None):
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        item_id = str(event.get("sample_id") or data.get("sample_id") or "")
        if not item_id:
            continue
        matrix.add_item(Item(id=item_id, text=str(data.get("prompt", ""))[:400]))
        matrix.add_system(system)
        score = _as_score(data.get("correct", data.get("score")))
        if score is None:
            continue
        matrix.record(item_id, system, score)
    return matrix


def _read_csv(text: str) -> Matrix:
    """A CSV in either shape.

    Long: one row per (item, system, score). Wide: one row per item, with a
    column per system.
    """
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect, strict=True)
    fieldnames = reader.fieldnames or []
    seen_headers: set[str] = set()
    duplicate_headers: list[str] = []
    for name in fieldnames:
        if name in seen_headers and name not in duplicate_headers:
            duplicate_headers.append(name)
        seen_headers.add(name)
    if duplicate_headers:
        displayed = ", ".join(repr(name) for name in duplicate_headers[:3])
        remaining = len(duplicate_headers) - 3
        if remaining > 0:
            displayed += f", and {remaining} more"
        raise ImportError_(
            f"duplicate CSV header name: {displayed}; each column name must be unique"
        )
    rows: list[dict] = []
    row_lines: list[int] = []
    try:
        for row in reader:
            extras = row.get(None)
            if extras is not None:
                count = len(extras)
                suffix = "" if count == 1 else "s"
                raise ImportError_(
                    f"CSV row near line {reader.line_num} has {count} extra "
                    f"field{suffix}"
                )
            if any((value or "").strip() for value in row.values()):
                rows.append(row)
                row_lines.append(reader.line_num)
    except csv.Error as exc:
        raise ImportError_(
            f"CSV syntax error near line {reader.line_num}: {exc}"
        ) from exc
    if not rows:
        return Matrix()

    headers = [header for header in fieldnames if header]
    has_system = _first(dict.fromkeys(headers), SYSTEM_KEYS) is not None
    has_score = _first(dict.fromkeys(headers), SCORE_KEYS) is not None
    if has_system and has_score:
        locations = [f"CSV row ending near line {line}" for line in row_lines]
        return _from_records(rows, locations)

    # Wide: the first identifying column names the item, and every remaining
    # column that parses as a score is a system.
    item_key = _first(dict.fromkeys(headers), ITEM_KEYS)
    id_column = item_key[0] if item_key else headers[0]
    text_key = _first(dict.fromkeys(headers), TEXT_KEYS)

    matrix = Matrix()
    for row, line in zip(rows, row_lines):
        item_id = _required_identifier(
            (id_column, row.get(id_column)),
            "item",
            f"CSV row ending near line {line}",
        )
        matrix.add_item(
            Item(
                id=item_id,
                text=str(row.get(text_key[0], item_id)) if text_key else item_id,
            )
        )
        for column, value in row.items():
            if not column or not column.strip():
                if _as_score(value) is not None:
                    raise ImportError_(
                        f"CSV row ending near line {line} has a blank system "
                        "identifier above a score"
                    )
                continue
            if column == id_column:
                continue
            if text_key and column == text_key[0]:
                continue
            score = _as_score(value)
            if score is not None:
                matrix.record(item_id, column, score)
    return matrix


#: Format name to reader. Defined last so every reader above is in scope, and
#: looked up at call time by :func:`parse_text`.
READERS = {
    "matrix": _read_matrix,
    "promptfoo": _read_promptfoo,
    "openai-evals": _read_openai_evals,
    "jsonl": _read_records,
    "csv": _read_csv,
}
