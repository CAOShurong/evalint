"""The results you already have, in the shape the statistics need.

Everything in this tool is computed from one table: for each eval item, how
each system scored on it. Every eval framework produces that table in a
different shape, so the importers normalise into this and nothing downstream
has to know where the numbers came from.

Scores are kept as floats in [0, 1] rather than booleans. Plenty of eval
setups are graded on a rubric or by a judge model rather than pass/fail, and
throwing that resolution away at the door would make every statistic coarser
than the data actually is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["Item", "Matrix", "System"]


@dataclass(frozen=True)
class System:
    """One thing being measured: a model, a prompt version, a pipeline."""

    name: str

    def __str__(self) -> str:
        return self.name


@dataclass
class Item:
    """One eval case, and what it is made of.

    ``text`` is whatever identifies the case to a human -- the prompt, the
    question, the input. It is what duplicate detection compares, and it is
    optional because some result files carry only ids.
    """

    id: str
    text: str = ""
    #: Free-form labels from the source file: category, capability, tags.
    tags: tuple[str, ...] = ()
    #: Whatever the source called the expected answer, if it gave one.
    expected: str = ""


class Matrix:
    """Item-by-system scores, plus the bookkeeping to keep them honest.

    Missing cells are real: a system may not have been run on every item, and
    treating an absent score as zero would turn "not measured" into "failed",
    which is the single most misleading thing this tool could do. So cells are
    stored sparsely and every statistic states what it was computed over.
    """

    def __init__(self) -> None:
        self.items: dict[str, Item] = {}
        self.systems: list[str] = []
        #: (item id, system) -> mean score in [0, 1]. Repeated measurements
        #: are averaged within the logical system rather than promoted to
        #: independent systems.
        self._scores: dict[tuple[str, str], float] = {}
        #: Number of raw measurements represented by each mean score.
        self._score_counts: dict[tuple[str, str], int] = {}

    # -- building ----------------------------------------------------------

    def add_item(self, item: Item) -> Item:
        existing = self.items.get(item.id)
        if existing is None:
            self.items[item.id] = item
            return item
        # A later record may carry text an earlier one lacked; keep the
        # richer version rather than the first one seen.
        if not existing.text and item.text:
            existing.text = item.text
        if not existing.expected and item.expected:
            existing.expected = item.expected
        if item.tags and not existing.tags:
            existing.tags = item.tags
        return existing

    def record(
        self,
        item_id: str,
        system: str,
        score: float,
        *,
        repetitions: int = 1,
    ) -> None:
        """Record one or more repeated measurements for a logical system.

        LLM runs are often repeated because generation and grading are
        stochastic. Those repetitions improve the estimate for that system,
        but they are not additional independent systems. Keeping their count
        while averaging the cell prevents pseudoreplication downstream.
        """
        if repetitions < 1:
            raise ValueError("repetitions must be at least 1")
        if system not in self.systems:
            self.systems.append(system)
        key = (item_id, system)
        value = _clamp(score)
        previous_count = self._score_counts.get(key, 0)
        total_count = previous_count + repetitions
        previous_total = self._scores.get(key, 0.0) * previous_count
        self._scores[key] = (previous_total + value * repetitions) / total_count
        self._score_counts[key] = total_count

    # -- reading -----------------------------------------------------------

    def score(self, item_id: str, system: str) -> float | None:
        return self._scores.get((item_id, system))

    def scores_for_item(self, item_id: str) -> dict[str, float]:
        return {
            system: self._scores[(item_id, system)]
            for system in self.systems
            if (item_id, system) in self._scores
        }

    def scores_for_system(self, system: str) -> dict[str, float]:
        return {
            item_id: self._scores[(item_id, system)]
            for item_id in self.items
            if (item_id, system) in self._scores
        }

    def repetitions(self, item_id: str, system: str) -> int:
        """Raw measurements represented by one logical score cell."""
        return self._score_counts.get((item_id, system), 0)

    @property
    def item_ids(self) -> list[str]:
        return list(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @property
    def observations(self) -> int:
        """Unique item-by-system cells after repeat aggregation."""
        return len(self._scores)

    @property
    def measurements(self) -> int:
        """Raw score measurements read before repeat aggregation."""
        return sum(self._score_counts.values())

    def runs_for_system(self, system: str) -> int:
        """Maximum repeated measurements observed for one item of a system."""
        counts = [
            count
            for (item_id, name), count in self._score_counts.items()
            if name == system and item_id in self.items
        ]
        return max(counts, default=0)

    @property
    def runs(self) -> int:
        """Run columns represented across all logical systems."""
        return sum(self.runs_for_system(system) for system in self.systems)

    @property
    def has_repeats(self) -> bool:
        return any(count > 1 for count in self._score_counts.values())

    @property
    def density(self) -> float:
        """Fraction of the grid that was actually measured."""
        total = len(self.items) * len(self.systems)
        return self.observations / total if total else 0.0

    def system_total(self, system: str) -> float:
        return sum(self.scores_for_system(system).values())

    def system_mean(self, system: str) -> float:
        scores = self.scores_for_system(system)
        return sum(scores.values()) / len(scores) if scores else 0.0

    def ranking(self) -> list[tuple[str, float]]:
        """Systems best first. This ordering is what the tool tries to preserve."""
        return sorted(
            ((s, self.system_mean(s)) for s in self.systems),
            key=lambda pair: (-pair[1], pair[0]),
        )

    def subset(self, item_ids) -> Matrix:
        """A new matrix over just these items, scores carried across."""
        keep = list(item_ids)
        out = Matrix()
        for item_id in keep:
            item = self.items.get(item_id)
            if item is None:
                continue
            out.add_item(item)
        out.systems = list(self.systems)
        for item_id in out.items:
            for system in self.systems:
                score = self._scores.get((item_id, system))
                if score is not None:
                    out._scores[(item_id, system)] = score
                    out._score_counts[(item_id, system)] = self._score_counts[
                        (item_id, system)
                    ]
        return out

    def as_dict(self) -> dict:
        return {
            "schema": "evalint/matrix-v1",
            "systems": list(self.systems),
            "items": [
                {
                    "id": item.id,
                    "text": item.text,
                    "tags": list(item.tags),
                    "expected": item.expected,
                    "scores": self.scores_for_item(item.id),
                    "repeats": {
                        system: self.repetitions(item.id, system)
                        for system in self.systems
                        if self.repetitions(item.id, system) > 1
                    },
                }
                for item in self.items.values()
            ],
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Matrix:
        matrix = cls()
        matrix.systems = list(raw.get("systems", ()))
        for entry in raw.get("items", ()):
            matrix.add_item(
                Item(
                    id=str(entry["id"]),
                    text=str(entry.get("text", "")),
                    tags=tuple(entry.get("tags", ())),
                    expected=str(entry.get("expected", "")),
                )
            )
            for system, score in (entry.get("scores") or {}).items():
                repetitions = int((entry.get("repeats") or {}).get(system, 1))
                matrix.record(
                    str(entry["id"]),
                    str(system),
                    float(score),
                    repetitions=repetitions,
                )
        return matrix


def _clamp(value: float) -> float:
    """Scores outside [0, 1] are a units mistake, not a signal.

    A grader emitting 0-100 or -1/1 is common enough that silently accepting
    it would corrupt every statistic downstream while looking fine. Clamping
    keeps one bad row from poisoning the whole report; the CLI warns when it
    sees a file whose range suggests the wrong units.
    """
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))
