"""Command line entry point."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pathlib
import sys
import tempfile

from . import __version__
from .dedupe import THRESHOLD
from .importers import ImportError_, load_many
from .report import Audit, Palette, audit_matrix, render
from .terminal import escape_untrusted

__all__ = ["main"]

#: Exit status when the eval set has a problem worth failing a build over.
#: Distinct from 1 so a pipeline can tell "your eval set is unsound" from "the
#: audit itself fell over".
EXIT_PROBLEMS = 2

#: Below this, reliability means the leaderboard is mostly noise.
FAIL_RELIABILITY = 0.6

# Python's splitlines() recognizes these as record boundaries. A plain
# one-id-per-line file cannot distinguish one inside an id from its delimiter.
_LINE_BREAKS = frozenset("\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")


class OutputError(Exception):
    """A requested output could not be written without risking data."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalint",
        description=(
            "Audit an LLM eval set. Reports what it can actually measure, "
            "which items are dead weight, which look broken, and how many "
            "you could drop without changing the answer."
        ),
        epilog=(
            "Examples:\n"
            "  evalint results.csv\n"
            "  evalint promptfoo-output.jsonl\n"
            "  evalint results.jsonl --json\n"
            "  evalint results.csv --fail-under 0.8\n"
            "  evalint gpt-4o.jsonl claude.jsonl llama.jsonl\n"
            "\n"
            "There must be at least two logical systems to compare: two models\n"
            "or two prompt versions. Repeat runs of the same named system are\n"
            "averaged rather than counted as independent evidence. Formats\n"
            "that log one run per file are merged on the item id. Pass each\n"
            "physical result file once; path and hard-link aliases are refused.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        type=pathlib.Path,
        nargs="+",
        metavar="FILE",
        help="eval results to audit; several files are merged on the item id",
    )
    parser.add_argument(
        "--format",
        default="auto",
        choices=("auto", "csv", "jsonl", "matrix", "promptfoo", "openai-evals"),
        help="input shape (default: detected from the file)",
    )
    parser.add_argument(
        "--similarity",
        type=float,
        default=THRESHOLD,
        metavar="N",
        help=(
            f"how alike two items must be to count as duplicates "
            f"(0-1, default: {THRESHOLD})"
        ),
    )
    parser.add_argument(
        "--no-duplicates",
        action="store_true",
        help="skip duplicate detection",
    )
    parser.add_argument(
        "--no-reduce",
        action="store_true",
        help="skip working out which items could be dropped",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        metavar="N",
        help=(
            f"exit {EXIT_PROBLEMS} if reliability is below N (a useful CI gate is 0.8)"
        ),
    )
    parser.add_argument(
        "--save-reduced",
        type=pathlib.Path,
        metavar="FILE",
        help="write the reduced set's item ids, one per line",
    )
    parser.add_argument(
        "--save-reduced-format",
        choices=("lines", "jsonl"),
        default="lines",
        help=(
            "reduced-id serialization (default: lines; jsonl preserves ids "
            "containing line breaks)"
        ),
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colour output (default: auto; NO_COLOR is honoured)",
    )
    parser.add_argument(
        "--ascii", action="store_true", help="avoid non-ASCII characters"
    )
    parser.add_argument("--version", action="version", version=f"evalint {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Intermixed, because `evalint results.csv --json` and
    # `evalint a.csv --json b.csv` are both things people type, and plain
    # parse_args rejects the second once the positional takes several values.
    args = parser.parse_intermixed_args(argv)
    _use_utf8(sys.stdout)
    _use_utf8(sys.stderr)

    if args.save_reduced is None and args.save_reduced_format != "lines":
        parser.error("--save-reduced-format requires --save-reduced")

    if args.save_reduced and not args.no_reduce:
        for path in args.paths:
            if _same_file(args.save_reduced, path):
                _print_error(
                    f"refusing to overwrite input {path} with "
                    f"--save-reduced {args.save_reduced}"
                )
                return 1

    try:
        matrix, fmt = load_many(args.paths, args.format)
    except ImportError_ as exc:
        _print_error(exc)
        return 1

    audit = audit_matrix(
        matrix,
        source=_source_name(args.paths),
        detect_duplicates=not args.no_duplicates,
        reduce=not args.no_reduce,
        similarity=args.similarity,
    )

    if args.save_reduced and audit.reduction is not None:
        try:
            _write_reduced(
                args.save_reduced,
                audit.reduction.kept,
                output_format=args.save_reduced_format,
            )
        except OutputError as exc:
            _print_error(exc)
            return 1

    if args.json:
        payload = audit.as_dict()
        payload["format"] = fmt
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        palette = Palette(args.color)
        if args.color == "never":
            palette.enabled = False
        print(render(audit, palette, ascii_only=args.ascii))

    return _exit_code(audit, args.fail_under)


def _source_name(paths: list[pathlib.Path]) -> str:
    if len(paths) == 1:
        return paths[0].name
    return f"{paths[0].name} +{len(paths) - 1} more"


def _print_error(message: object) -> None:
    print(f"evalint: {escape_untrusted(message)}", file=sys.stderr)


def _same_file(left: pathlib.Path, right: pathlib.Path) -> bool:
    """Recognise lexical aliases, symlinks, and hard links where possible."""
    try:
        return os.path.samefile(left, right)
    except OSError:
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
            os.path.abspath(right)
        )


def _write_reduced(
    path: pathlib.Path,
    item_ids: list[str],
    *,
    output_format: str = "lines",
) -> None:
    """Replace a reduced-set output only after its complete contents exist."""
    if output_format == "jsonl":
        contents = "".join(json.dumps(item_id) + "\n" for item_id in item_ids)
    else:
        has_line_break = any(
            character in _LINE_BREAKS for item_id in item_ids for character in item_id
        )
        if has_line_break:
            raise OutputError(
                "cannot write line-oriented reduced set: a kept item id contains "
                "a line break; use --save-reduced-format jsonl to preserve it"
            )
        contents = "\n".join(item_ids) + "\n"

    temporary: pathlib.Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = pathlib.Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            with contextlib.suppress(OSError):
                temporary.unlink()
        raise OutputError(f"cannot write reduced set to {path}: {exc}") from exc


def _exit_code(audit: Audit, fail_under: float | None) -> int:
    reliability = audit.summary.reliability
    if fail_under is not None:
        if reliability is None or reliability < fail_under:
            return EXIT_PROBLEMS
        return 0
    # Without an explicit gate, only an eval set that cannot rank at all is
    # treated as a failure. Dead weight and duplicates are worth knowing about
    # but are not, on their own, a reason to fail somebody's build.
    if reliability is not None and reliability < FAIL_RELIABILITY:
        return EXIT_PROBLEMS
    return 0


def _use_utf8(stream) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    with contextlib.suppress(OSError, ValueError):
        reconfigure(encoding="utf-8", errors="replace")
