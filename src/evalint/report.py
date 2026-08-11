"""Saying what the numbers mean, in the order someone needs them.

The audience is not a psychometrician. Somebody has an eval set, a leaderboard
they half trust, and a bill. So the report leads with what the set can and
cannot tell them, then with what they are paying for and not using, then with
the specific items worth opening. Every number that rests on an assumption
says which one.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from .dedupe import THRESHOLD, Cluster, find_duplicates
from .matrix import Matrix
from .reduce import Reduction, reduce_set
from .stats import ItemStats, SetStats, item_stats, set_stats

__all__ = ["Audit", "Palette", "audit_matrix", "render"]


@dataclass
class Audit:
    """Everything computed about one eval set."""

    source: str
    matrix: Matrix
    stats: dict[str, ItemStats]
    summary: SetStats
    clusters: list[Cluster] = field(default_factory=list)
    reduction: Reduction | None = None
    #: Retained in the v1 JSON schema; invalid score units now fail at import.
    units_warning: str = ""

    @property
    def duplicate_items(self) -> int:
        return sum(len(c.duplicates) for c in self.clusters)

    def broken(self) -> list[ItemStats]:
        found = [s for s in self.stats.values() if s.looks_broken]
        found.sort(key=lambda s: (s.discrimination or 0.0, s.item_id))
        return found

    def suspects(self) -> list[ItemStats]:
        found = [s for s in self.stats.values() if s.suspect]
        found.sort(key=lambda s: (s.discrimination or 0.0, s.item_id))
        return found

    def as_dict(self) -> dict:
        summary = self.summary.as_dict()
        summary["runs"] = self.matrix.runs
        summary["measurements"] = self.matrix.measurements
        return {
            "schema": "evalint/audit-v1",
            "source": self.source,
            "summary": summary,
            "duplicate_clusters": [c.as_dict() for c in self.clusters],
            "duplicate_items": self.duplicate_items,
            "reduction": None if self.reduction is None else self.reduction.as_dict(),
            "ranking": [
                {"system": name, "mean": round(mean, 4)}
                for name, mean in self.matrix.ranking()
            ],
            "broken": [s.as_dict() for s in self.broken()],
            "suspect": [s.as_dict() for s in self.suspects()],
            "units_warning": self.units_warning,
        }


class Palette:
    ROLES = {
        "bad": "\x1b[38;5;167m",
        "warn": "\x1b[38;5;179m",
        "ok": "\x1b[38;5;71m",
        "muted": "\x1b[38;5;244m",
        "accent": "\x1b[38;5;74m",
    }

    def __init__(self, enabled: str = "auto", stream=None) -> None:
        stream = stream or sys.stdout
        if enabled == "auto":
            self.enabled = (
                os.environ.get("NO_COLOR") is None
                and hasattr(stream, "isatty")
                and stream.isatty()
                and os.environ.get("TERM") != "dumb"
            )
        else:
            self.enabled = enabled == "always"

    def paint(self, text: str, role: str) -> str:
        if not self.enabled or not text:
            return text
        return f"{self.ROLES[role]}{text}\x1b[0m"

    def bold(self, text: str) -> str:
        return f"\x1b[1m{text}\x1b[0m" if self.enabled and text else text


def _bar(fraction: float, width: int, unicode_ok: bool) -> str:
    full, empty = ("█", "·") if unicode_ok else ("#", ".")
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    return full * filled + empty * (width - filled)


def render(audit: Audit, palette: Palette, *, ascii_only: bool = False) -> str:
    arrow = "->" if ascii_only else "→"
    sep = " - " if ascii_only else " · "
    rows: list[str] = []
    summary = audit.summary
    matrix = audit.matrix

    rows.append(palette.bold(f"evalint  {audit.source}"))
    rows.append(
        "  "
        + palette.paint(
            f"{summary.items} items{sep}{summary.systems} systems"
            + (f"{sep}{matrix.runs} runs" if matrix.has_repeats else "")
            + f"{sep}{matrix.measurements} scores",
            "muted",
        )
    )
    if matrix.has_repeats:
        rows.append(
            "  "
            + palette.paint(
                "repeat scores were averaged within each logical system; "
                "they do not increase statistical independence",
                "muted",
            )
        )
    if audit.units_warning:
        rows.append("  " + palette.paint(audit.units_warning, "warn"))

    # -- what the set can tell you ----------------------------------------
    rows.append("")
    rows.append(palette.bold("Measurement"))
    if summary.reliability is None:
        rows.append(
            "  "
            + palette.paint(
                f"reliability could not be computed: {summary.reliability_verdict}",
                "warn",
            )
        )
    else:
        role = (
            "ok"
            if summary.reliability >= 0.8
            else "warn"
            if summary.reliability >= 0.6
            else "bad"
        )
        rows.append(
            f"  reliability     {palette.paint(f'{summary.reliability:.2f}', role)}"
            f"   {palette.paint(summary.reliability_verdict, 'muted')}"
        )
    if summary.standard_error is not None:
        rows.append(
            "  smallest real difference  "
            + palette.paint(f"{summary.standard_error:.3f}", "accent")
            + palette.paint(
                "   systems closer than this are not distinguishable", "muted"
            )
        )
    share = summary.informative / summary.items if summary.items else 0.0
    rows.append(
        f"  informative     {_bar(share, 12, not ascii_only)} "
        f"{summary.informative}/{summary.items}"
        + palette.paint(
            f"   {summary.items - summary.informative} cannot affect the ranking",
            "muted",
        )
    )

    # -- what is being paid for and not used -------------------------------
    waste: list[tuple[int, str]] = []
    if summary.everyone_passes:
        waste.append((summary.everyone_passes, "every system passes"))
    if summary.everyone_fails:
        waste.append((summary.everyone_fails, "no system passes"))
    if audit.duplicate_items:
        waste.append((audit.duplicate_items, "near-duplicate of another item"))
    if waste:
        rows.append("")
        rows.append(palette.bold("Paying for, not using"))
        for count, why in waste:
            rows.append(
                f"  {palette.paint(f'{count:>5}', 'warn')}  "
                + palette.paint(why, "muted")
            )

    reduction = audit.reduction
    if reduction is not None and reduction.dropped:
        verdict = (
            "same ranking"
            if reduction.ranking_preserved
            else f"ranking agreement {reduction.tau:.2f}"
        )
        detail = (
            f"reliability {reduction.reliability_before:.2f} {arrow} "
            f"{reduction.reliability_after:.2f}"
            if reduction.reliability_before is not None
            and reduction.reliability_after is not None
            else ""
        )
        rows.append("")
        rows.append(
            "  "
            + palette.paint(
                f"{len(reduction.kept)} of {reduction.original_items} items "
                f"reproduce the {verdict}",
                "ok" if reduction.ranking_preserved else "warn",
            )
            + palette.paint(
                f"   {reduction.saving:.0%} fewer calls per run"
                + (f"{sep}{detail}" if detail else ""),
                "muted",
            )
        )

    # -- items worth opening -----------------------------------------------
    broken = audit.broken()
    if broken:
        rows.append("")
        rows.append(palette.bold("Probably broken"))
        rows.append(
            "  "
            + palette.paint(
                "the worse systems pass these more often than the better ones,"
                " which usually means the expected answer is wrong",
                "muted",
            )
        )
        for stat in broken[:10]:
            rows.append(
                f"  {palette.paint('BROKEN', 'bad')} {stat.item_id}"
                + palette.paint(
                    f"   discrimination {stat.discrimination:+.2f}"
                    f"{sep}chance {stat.chance:.3f}",
                    "muted",
                )
            )
        if len(broken) > 10:
            rows.append("  " + palette.paint(f"+{len(broken) - 10} more", "muted"))

    suspects = audit.suspects()
    if suspects:
        rows.append("")
        rows.append(palette.bold("Inverted, but unproven"))
        rows.append(
            "  "
            + palette.paint(
                f"{len(suspects)} items lean the wrong way, and "
                f"{summary.systems} systems cannot rule out luck. More independent"
                " systems would settle it.",
                "muted",
            )
        )

    # -- the ranking itself --------------------------------------------------
    rows.append("")
    rows.append(palette.bold("Ranking"))
    ranking = matrix.ranking()
    best = ranking[0][1] if ranking else 0.0
    for name, mean in ranking:
        tie = ""
        if (
            summary.standard_error is not None
            and name != ranking[0][0]
            and abs(best - mean) < summary.standard_error
        ):
            tie = palette.paint("  tied with the leader", "warn")
        rows.append(f"  {name:<24} {_bar(mean, 14, not ascii_only)} {mean:.3f}{tie}")

    return "\n".join(rows)


def audit_matrix(
    matrix: Matrix,
    *,
    source: str = "results",
    detect_duplicates: bool = True,
    reduce: bool = True,
    similarity: float = THRESHOLD,
) -> Audit:
    """Run every check over an already-loaded matrix."""
    stats = item_stats(matrix)
    summary = set_stats(matrix, stats)

    clusters = []
    if detect_duplicates:
        texts = {
            item_id: item.text for item_id, item in matrix.items.items() if item.text
        }
        if texts:
            clusters = find_duplicates(texts, threshold=similarity)

    reduction = None
    if reduce:
        reduction = reduce_set(matrix, stats, clusters)

    return Audit(
        source=source,
        matrix=matrix,
        stats=stats,
        summary=summary,
        clusters=clusters,
        reduction=reduction,
        units_warning="",
    )
