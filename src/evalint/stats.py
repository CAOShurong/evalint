"""Classical test theory, pointed at an eval set instead of a school exam.

An eval set is a test. The thing being tested is not a student, it is a model
or a prompt or a pipeline, and the question the numbers are supposed to answer
is "which of these is better". Educational measurement has spent a century
working out when a test can answer that and when it cannot, and none of that
machinery is normally pointed at eval sets.

The three quantities that do the work:

**Difficulty** is the mean score on an item. An item everything passes, or
everything fails, has zero variance and therefore contributes exactly nothing
to telling systems apart. It is not a bad item in some aesthetic sense -- it
is arithmetically incapable of affecting the ranking, while still costing a
full API call every run.

**Discrimination** is the correlation between an item's score and the total
score on everything else. A good item is passed more often by the systems that
do better overall. A *negative* correlation means the item is passed more
often by the systems that do worse, which in practice almost always means the
expected answer is wrong.

**Reliability** (KR-20, Cronbach's alpha) is how much of the spread between
systems is signal rather than noise. It is what licenses a sentence like "A
beat B", and it is the number nobody computes.

One honest caveat runs through all of it: here the "subjects" are systems, and
people usually compare two or three. Every statistic below is unstable at that
size, so each carries the count it was computed from and the report says so
rather than printing a confident-looking decimal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .matrix import Matrix

__all__ = [
    "ItemStats",
    "SetStats",
    "correlation",
    "item_stats",
    "set_stats",
    "variance",
]

#: Below this many systems, discrimination and reliability are too unstable to
#: report as numbers. Two systems give a correlation of exactly +1 or -1 for
#: every item that varies at all, which looks meaningful and is not.
MIN_SYSTEMS_FOR_CORRELATION = 3

#: Discrimination at or below this is the *shape* of a broken item: the worse
#: systems pass it more often than the better ones.
#:
#: On its own this threshold accuses innocent items, and the measurement says
#: so. On five systems, deliberately broken items land around -0.60 while
#: ordinary items -- passed by the weaker systems purely by luck -- reach
#: -0.71. The two populations overlap completely, so a threshold alone cannot
#: tell them apart, and a tool that reported "21 broken items" on that basis
#: would be sending people to fix 13 that were fine.
#:
#: What separates them is not a better cutoff, it is more independent systems.
#: Repeated runs of one system are averaged before this function is reached;
#: treating them as new columns would manufacture significance through
#: pseudoreplication. :func:`chance_of_negative` measures whether genuinely
#: independent evidence is there yet instead of assuming it.
BROKEN_DISCRIMINATION = -0.15

#: A negative discrimination is only worth acting on when chance can be ruled
#: out at about this level. Deliberately loose -- this is a "go and look at
#: this item" signal, not a hypothesis test anyone is publishing.
BROKEN_SIGNIFICANCE = 0.05

#: Permutation resamples. Enough to resolve p-values around 0.05 without
#: making the run noticeably slow on a few thousand items.
PERMUTATIONS = 400

#: Below this, an item is contributing little to the ranking even though it
#: still costs a call every run.
WEAK_DISCRIMINATION = 0.1


def variance(values) -> float:
    """Population variance. Population, not sample: these are all the systems
    there are, not a draw from some larger pool of systems."""
    values = list(values)
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def correlation(xs, ys) -> float | None:
    """Pearson correlation, or ``None`` when it is not defined.

    Undefined is a real answer here and must not be rounded to zero: if either
    side has no variance the correlation genuinely does not exist, and
    reporting 0.0 would look like "measured, and it is uninformative" rather
    than "could not be measured".
    """
    xs, ys = list(xs), list(ys)
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    spread_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    spread_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if spread_x == 0 or spread_y == 0:
        return None
    return numerator / (spread_x * spread_y)


@dataclass
class ItemStats:
    """What one eval item is contributing."""

    item_id: str
    #: Mean score across systems. 1.0 = everything passes, 0.0 = nothing does.
    difficulty: float
    #: Variance across systems. Zero means this item cannot affect the ranking.
    variance: float
    #: Corrected item-total correlation, or ``None`` when undefined.
    discrimination: float | None
    #: How many systems were actually scored on this item.
    observed: int
    #: How often a discrimination this negative arises by chance, given the
    #: number of columns available. ``None`` when not computed.
    chance: float | None = None

    @property
    def is_flat(self) -> bool:
        """Every system scored the same, so it separates nothing."""
        return self.variance == 0.0

    @property
    def everyone_passes(self) -> bool:
        return self.is_flat and self.difficulty >= 0.999

    @property
    def everyone_fails(self) -> bool:
        return self.is_flat and self.difficulty <= 0.001

    @property
    def is_informative(self) -> bool:
        """Capable of affecting which system comes out ahead."""
        return not self.is_flat

    @property
    def is_inverted(self) -> bool:
        """The worse systems pass it more often than the better ones."""
        return (
            self.discrimination is not None
            and self.discrimination <= BROKEN_DISCRIMINATION
        )

    @property
    def looks_broken(self) -> bool:
        """Inverted, *and* unlikely enough to be chance to be worth checking.

        Both halves are required. Inversion alone is common with a handful of
        systems -- an ordinary item that the weaker ones happened to get right
        looks identical to one whose expected answer is wrong. Without the
        second half this property would name innocent items, and a reader who
        checked two of them and found nothing would stop believing the rest.
        """
        return (
            self.is_inverted
            and self.chance is not None
            and self.chance <= BROKEN_SIGNIFICANCE
        )

    @property
    def suspect(self) -> bool:
        """Inverted, but the evidence is not there to say more than that."""
        return self.is_inverted and not self.looks_broken

    @property
    def is_weak(self) -> bool:
        return (
            self.discrimination is not None
            and BROKEN_DISCRIMINATION < self.discrimination < WEAK_DISCRIMINATION
            and not self.is_flat
        )

    def as_dict(self) -> dict:
        return {
            "id": self.item_id,
            "difficulty": round(self.difficulty, 4),
            "variance": round(self.variance, 6),
            "discrimination": (
                None if self.discrimination is None else round(self.discrimination, 4)
            ),
            "chance": None if self.chance is None else round(self.chance, 4),
            "observed": self.observed,
            "informative": self.is_informative,
            "looks_broken": self.looks_broken,
            "suspect": self.suspect,
        }


def chance_of_negative(
    own: list[float],
    rest: list[float],
    observed: float,
    *,
    permutations: int = PERMUTATIONS,
    seed: int = 0,
) -> float:
    """How often a discrimination this negative arises purely by chance.

    A permutation test, because the alternative is a distributional assumption
    that does not hold. The item's scores are shuffled against the systems'
    overall scores; under the null, the pairing carries no information, so
    every shuffle is as likely as the one observed. The answer is the fraction
    of shuffles at least as negative as what was actually seen.

    With three systems there are only six orderings, so the smallest possible
    answer is about 1/6 and no item can clear a 0.05 bar -- which is the
    correct outcome, not a limitation to route around. Three systems genuinely
    cannot distinguish a broken item from an unlucky one, and the report says
    that instead of guessing.

    Seeded, so two runs over the same file agree. A p-value that flickered
    between runs would be worse than none.
    """
    if len(own) != len(rest) or len(own) < 3:
        return 1.0
    import random

    rng = random.Random(seed)
    shuffled = list(own)
    at_least_as_extreme = 0
    for _ in range(permutations):
        rng.shuffle(shuffled)
        value = correlation(shuffled, rest)
        if value is not None and value <= observed:
            at_least_as_extreme += 1
    # The observed arrangement is itself one of the possibilities, so it is
    # counted in both parts. Without that the estimate can reach exactly zero,
    # which claims more certainty than a finite number of resamples supports.
    return (at_least_as_extreme + 1) / (permutations + 1)


def item_stats(matrix: Matrix, *, test_chance: bool = True) -> dict[str, ItemStats]:
    """Difficulty, variance and discrimination for every item."""
    out: dict[str, ItemStats] = {}
    systems = matrix.systems
    enough_systems = len(systems) >= MIN_SYSTEMS_FOR_CORRELATION

    # Each system's total, so the "rest" score can be found by subtraction
    # rather than by re-summing the whole row for every item.
    totals = {system: matrix.system_total(system) for system in systems}

    for item_id in matrix.items:
        scores = matrix.scores_for_item(item_id)
        values = list(scores.values())
        if not values:
            out[item_id] = ItemStats(item_id, 0.0, 0.0, None, 0)
            continue

        difficulty = sum(values) / len(values)
        spread = variance(values)

        discrimination = None
        chance = None
        if enough_systems and len(scores) >= MIN_SYSTEMS_FOR_CORRELATION:
            # Corrected item-total: the item is removed from the total it is
            # correlated against. Leaving it in correlates the item with
            # itself, which inflates every number and flatters short sets most.
            own = [scores[s] for s in scores]
            rest = [totals[s] - scores[s] for s in scores]
            discrimination = correlation(own, rest)
            # Only tested where it could change an answer. The permutation is
            # the expensive part, and a positively discriminating item is
            # never going to be accused of anything.
            if (
                test_chance
                and discrimination is not None
                and discrimination <= BROKEN_DISCRIMINATION
            ):
                chance = chance_of_negative(
                    own,
                    rest,
                    discrimination,
                    seed=_stable_seed(item_id),
                )

        out[item_id] = ItemStats(
            item_id=item_id,
            difficulty=difficulty,
            variance=spread,
            discrimination=discrimination,
            observed=len(values),
            chance=chance,
        )
    return out


def _stable_seed(item_id: str) -> int:
    """A seed that depends on the item but not on the run.

    ``hash()`` is salted per process, so using it would make the p-values move
    between runs of the same file.
    """
    import zlib

    return zlib.crc32(item_id.encode("utf-8"))


@dataclass
class SetStats:
    """What the eval set as a whole can and cannot tell you."""

    items: int
    systems: int
    #: Items with any variance across systems -- the ones that can move a
    #: ranking at all.
    informative: int
    everyone_passes: int
    everyone_fails: int
    #: Inverted and unlikely to be chance -- worth opening.
    looks_broken: int
    #: Inverted, but this many systems cannot rule out luck.
    suspect: int
    weak: int
    #: KR-20 / Cronbach's alpha, or ``None`` when there are too few systems.
    reliability: float | None
    #: Standard error of measurement, in the same units as the mean score.
    standard_error: float | None
    #: Spread of system means; without it, reliability is meaningless.
    system_spread: float

    @property
    def dead_weight(self) -> int:
        """Items that cost a call every run and change nothing."""
        return self.everyone_passes + self.everyone_fails

    @property
    def reliability_verdict(self) -> str:
        """Plain words, because 0.68 means nothing to most readers."""
        if self.reliability is None:
            return "not measurable with this few systems"
        if self.reliability >= 0.9:
            return "strong enough to trust small differences"
        if self.reliability >= 0.8:
            return "good enough for ranking, not for small margins"
        if self.reliability >= 0.6:
            return "weak: only large differences mean anything"
        return "too noisy to rank systems reliably"

    def as_dict(self) -> dict:
        return {
            "items": self.items,
            "systems": self.systems,
            "informative": self.informative,
            "everyone_passes": self.everyone_passes,
            "everyone_fails": self.everyone_fails,
            "looks_broken": self.looks_broken,
            "suspect": self.suspect,
            "weak": self.weak,
            "reliability": (
                None if self.reliability is None else round(self.reliability, 4)
            ),
            "reliability_verdict": self.reliability_verdict,
            "standard_error": (
                None if self.standard_error is None else round(self.standard_error, 4)
            ),
            "system_spread": round(self.system_spread, 4),
        }


def set_stats(matrix: Matrix, stats: dict[str, ItemStats] | None = None) -> SetStats:
    """Reliability and the counts that explain it."""
    stats = stats if stats is not None else item_stats(matrix)
    systems = matrix.systems

    reliability = _reliability(matrix, stats)
    totals = [matrix.system_mean(s) for s in systems]
    spread = math.sqrt(variance(totals))

    standard_error = None
    if reliability is not None and reliability < 1.0:
        # SEM = SD * sqrt(1 - reliability): the part of an observed score that
        # is noise. Two systems closer together than this are not
        # distinguishable by this eval set, however many decimal places the
        # leaderboard prints.
        standard_error = spread * math.sqrt(max(0.0, 1.0 - reliability))

    return SetStats(
        items=len(matrix.items),
        systems=len(systems),
        informative=sum(1 for s in stats.values() if s.is_informative),
        everyone_passes=sum(1 for s in stats.values() if s.everyone_passes),
        everyone_fails=sum(1 for s in stats.values() if s.everyone_fails),
        looks_broken=sum(1 for s in stats.values() if s.looks_broken),
        suspect=sum(1 for s in stats.values() if s.suspect),
        weak=sum(1 for s in stats.values() if s.is_weak),
        reliability=reliability,
        standard_error=standard_error,
        system_spread=spread,
    )


def _reliability(matrix: Matrix, stats: dict[str, ItemStats]) -> float | None:
    """KR-20 / Cronbach's alpha over the item scores.

    alpha = k/(k-1) * (1 - sum(item variances) / variance of totals)

    Returns ``None`` rather than a number whenever the formula would be
    meaningless: fewer than two items, too few systems, or no spread between
    the systems at all. A reliability figure computed on two systems is
    arithmetic without information, and printing it would be the most
    quotable wrong number in the report.
    """
    systems = matrix.systems
    if len(systems) < MIN_SYSTEMS_FOR_CORRELATION:
        return None
    item_ids = [i for i in matrix.items if stats[i].observed >= len(systems)]
    count = len(item_ids)
    if count < 2:
        return None

    totals = [sum(matrix.score(i, s) or 0.0 for i in item_ids) for s in systems]
    total_variance = variance(totals)
    if total_variance == 0:
        # Every system scored identically overall. Reliability is undefined,
        # and the report says the set cannot separate them at all.
        return None

    item_variance = sum(stats[i].variance for i in item_ids)
    alpha = (count / (count - 1)) * (1 - item_variance / total_variance)
    # Alpha is bounded above by 1; negative values are possible and mean the
    # items disagree with each other more than chance, which is worth showing
    # rather than clipping to zero.
    return min(1.0, alpha)
