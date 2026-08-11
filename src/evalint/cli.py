"""Command line entry point."""

from __future__ import annotations

import argparse
import contextlib
import json
import pathlib
import sys

from . import __version__
from .dedupe import THRESHOLD
from .importers import ImportError_, load_many
from .report import Audit, Palette, audit_matrix, render

__all__ = ["main"]

#: Exit status when the eval set has a problem worth failing a build over.
#: Distinct from 1 so a pipeline can tell "your eval set is unsound" from "the
#: audit itself fell over".
EXIT_PROBLEMS = 2

#: Below this, reliability means the leaderboard is mostly noise.
FAIL_RELIABILITY = 0.6


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
            "  evalint promptfoo-output.json\n"
            "  evalint results.jsonl --json\n"
            "  evalint results.csv --fail-under 0.8\n"
            "  evalint gpt-4o.jsonl claude.jsonl llama.jsonl\n"
            "\n"
            "There must be at least two logical systems to compare: two models\n"
            "or two prompt versions. Repeat runs of the same named system are\n"
            "averaged rather than counted as independent evidence. Formats\n"
            "that log one run per file are merged on the item id.\n"
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

    try:
        matrix, fmt = load_many(args.paths, args.format)
    except ImportError_ as exc:
        print(f"evalint: {exc}", file=sys.stderr)
        return 1

    audit = audit_matrix(
        matrix,
        source=_source_name(args.paths),
        detect_duplicates=not args.no_duplicates,
        reduce=not args.no_reduce,
        similarity=args.similarity,
    )

    if args.save_reduced and audit.reduction is not None:
        args.save_reduced.write_text(
            "\n".join(audit.reduction.kept) + "\n", encoding="utf-8"
        )

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
