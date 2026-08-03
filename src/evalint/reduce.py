"""How much of the eval set you could stop paying for.

Every item costs a call on every run, forever. Some of them cannot affect the
answer: an item every system passes is arithmetically incapable of changing a
ranking, and a duplicate of an item already in the set adds cost without
adding an independent observation.

The reduction is built in three layers, hardest evidence first, so that a
reader can stop at whatever level of confidence they are comfortable with:

1. **Provably inert.** Zero variance across systems. Removing these cannot
   change any ranking, ever, because they contribute an identical constant to
   every system's total. This needs no judgement and no threshold.
2. **Redundant.** Near-duplicates collapsed to one representative. Slightly
   weaker: they are the same *question*, so they carry the same information,
   but they were still separate observations.
3. **Low information.** Kept only until the ranking stops matching. This is
   the part that trades something away, so it is verified rather than assumed:
   the ranking produced by the subset is compared against the full set's.

Nothing is deleted. The result is a list of ids and a verdict, and what to do
about it is the reader's call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dedupe import Cluster
from .matrix import Matrix
from .stats import ItemStats, set_stats

__all__ = ["Reduction", "kendall_tau", "reduce_set"]

#: Reliability may fall by at most this much before a reduction is refused.
#: Small, because the whole promise is "same answer, fewer items"; a cheaper
#: set that measures worse is not a saving, it is a downgrade.
MAX_RELIABILITY_LOSS = 0.02


def kendall_tau(left: list[str], right: list[str]) -> float:
    """Rank agreement between two orderings of the same systems.

    Kendall rather than Spearman because the quantity people actually care
    about is pairwise: "did A still beat B". Tau counts exactly the pairs
    whose order survived.

    Returns 1.0 for identical orderings, -1.0 for exactly reversed.
    """
    if len(left) != len(right) or len(left) < 2:
        return 1.0
    position = {name: index for index, name in enumerate(right)}
    if set(left) != set(position):
        return 0.0
    concordant = discordant = 0
    for i, a in enumerate(left):
        for b in left[i + 1 :]:
            if position[a] < position[b]:
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else 1.0


@dataclass
class Reduction:
    """A smaller set, and the evidence that it says the same thing."""

    kept: list[str] = field(default_factory=list)
    #: Zero-variance items. Removing these provably changes nothing.
    inert: list[str] = field(default_factory=list)
    #: Near-duplicates of an item that was kept.
    redundant: list[str] = field(default_factory=list)
    #: Items dropped because the ranking survived without them.
    low_information: list[str] = field(default_factory=list)

    original_items: int = 0
    #: Rank agreement between the reduced set and the full set, 1.0 = identical.
    tau: float = 1.0
    ranking_preserved: bool = True
    reliability_before: float | None = None
    reliability_after: float | None = None
    #: Anything the reduction declined to do, and why.
    notes: list[str] = field(default_factory=list)

    @property
    def dropped(self) -> int:
        return len(self.inert) + len(self.redundant) + len(self.low_information)

    @property
    def saving(self) -> float:
        """Fraction of calls per run that would no longer happen."""
        return self.dropped / self.original_items if self.original_items else 0.0

    def as_dict(self) -> dict:
        return {
            "original_items": self.original_items,
            "kept": len(self.kept),
            "dropped": self.dropped,
            "saving": round(self.saving, 4),
            "tau": round(self.tau, 4),
            "ranking_preserved": self.ranking_preserved,
            "reliability_before": (
                None
                if self.reliability_before is None
                else round(self.reliability_before, 4)
            ),
            "reliability_after": (
                None
                if self.reliability_after is None
                else round(self.reliability_after, 4)
            ),
            "inert": list(self.inert),
            "redundant": list(self.redundant),
            "low_information": list(self.low_information),
            "notes": list(self.notes),
        }


def _ranking_of(matrix: Matrix, item_ids: list[str]) -> list[str]:
    return [name for name, _ in matrix.subset(item_ids).ranking()]


def _information(stat: ItemStats) -> float:
    """How much an item contributes to separating systems.

    Variance is how much the item moves at all; discrimination is whether it
    moves in agreement with everything else. An item that varies a lot but
    disagrees with the rest of the set is noise, and multiplying the two
    ranks it accordingly without needing a special case.
    """
    if stat.discrimination is None:
        return stat.variance
    return stat.variance * max(0.0, stat.discrimination)


def reduce_set(
    matrix: Matrix,
    stats: dict[str, ItemStats],
    clusters: list[Cluster] | None = None,
    *,
    max_reliability_loss: float = MAX_RELIABILITY_LOSS,
) -> Reduction:
    """Find the smallest subset that still gives the same ranking."""
    reduction = Reduction(original_items=len(matrix.items))
    full_ranking = [name for name, _ in matrix.ranking()]
    baseline = set_stats(matrix, stats)
    reduction.reliability_before = baseline.reliability

    # 1. Provably inert.
    inert = {i for i, s in stats.items() if s.is_flat}
    reduction.inert = sorted(inert)

    # 2. Redundant. Only duplicates of something that is itself being kept:
    #    dropping every member of a cluster would lose the question entirely.
    #
    #    Verified, not assumed. Duplicate detection works on surface text, so
    #    two items can read alike and still be scored differently -- a
    #    templated pair where only the number changed is textually near
    #    identical and genuinely tests different things. Dropping those would
    #    move the ranking, so the whole redundancy step is rolled back if it
    #    does. Without this check a bad clustering silently produces a
    #    confident "96% fewer calls" next to a reversed leaderboard.
    proposed: set[str] = set()
    for cluster in clusters or ():
        alive = [m for m in [cluster.keeper, *cluster.duplicates] if m not in inert]
        if len(alive) < 2:
            continue
        proposed.update(alive[1:])

    redundant: set[str] = set()
    if proposed:
        candidate = [i for i in matrix.items if i not in inert and i not in proposed]
        if len(candidate) >= 2 and _ranking_of(matrix, candidate) == full_ranking:
            redundant = proposed
        else:
            reduction.notes.append(
                f"{len(proposed)} near-duplicates were left in place: removing "
                "them changed the ranking, so they are not interchangeable "
                "despite the similar wording"
            )
    reduction.redundant = sorted(redundant)

    survivors = [
        item_id
        for item_id in matrix.items
        if item_id not in inert and item_id not in redundant
    ]

    # 3. Low information, verified rather than assumed. Weakest first, and
    #    stop at the first drop the ranking does not survive.
    survivors.sort(key=lambda i: _information(stats[i]))
    dropped: set[str] = set()
    for item_id in survivors:
        candidate = [i for i in survivors if i not in dropped and i != item_id]
        if len(candidate) < 2:
            break
        if _ranking_of(matrix, candidate) != full_ranking:
            break
        trial = matrix.subset(candidate)
        trial_stats = set_stats(trial)
        if (
            baseline.reliability is not None
            and trial_stats.reliability is not None
            and baseline.reliability - trial_stats.reliability > max_reliability_loss
        ):
            break
        dropped.add(item_id)

    reduction.low_information = sorted(dropped)
    reduction.kept = sorted(i for i in survivors if i not in dropped)

    final = matrix.subset(reduction.kept)
    final_ranking = [name for name, _ in final.ranking()]
    reduction.tau = kendall_tau(final_ranking, full_ranking)
    reduction.ranking_preserved = final_ranking == full_ranking
    reduction.reliability_after = set_stats(final).reliability
    return reduction
