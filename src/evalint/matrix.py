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

__all__ = [
    "NATIVE_SCHEMA",
    "ConflictingItem",
    "InvalidScore",
    "Item",
    "Matrix",
    "System",
]

NATIVE_SCHEMA = "evalint/matrix-v1"


class ConflictingItem(ValueError):
    """One item id was attached to incompatible identifying metadata."""


class InvalidScore(ValueError):
    """A score cannot be interpreted on EvalInt's declared unit scale."""


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


def _native_identifier(value, kind: str, location: str) -> str:
    """Validate an identifier from evalint's own versioned matrix format."""
    if value is None:
        raise ValueError(f"{location} has a null {kind} identifier")
    if not isinstance(value, str):
        raise ValueError(f"{location} {kind} identifier must be a string")
    if not value.strip():
        raise ValueError(f"{location} has a blank {kind} identifier")
    return value


def _native_repeat_count(value, location: str) -> int:
    """Validate a raw-measurement count without lossy numeric coercion."""
    if isinstance(value, bool):
        raise ValueError(f"{location} count must be a positive integer")
    if isinstance(value, int):
        count = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        # JSON Schema treats 2 and 2.0 as the same integer-valued JSON number.
        count = int(value)
    else:
        raise ValueError(f"{location} count must be a positive integer")
    if count < 1:
        raise ValueError(f"{location} count must be a positive integer")
    return count


def _native_optional_string(entry: dict, field: str, location: str) -> str:
    """Validate an optional string field without inventing text by coercion."""
    value = entry.get(field, "")
    if not isinstance(value, str):
        raise ValueError(f"{location} {field} must be a string")
    return value


def _native_tags(entry: dict, location: str) -> tuple[str, ...]:
    """Validate free-form labels without treating a string as an iterable."""
    value = entry.get("tags", [])
    if not isinstance(value, list):
        raise ValueError(f"{location} tags must be an array")
    for position, tag in enumerate(value, start=1):
        if not isinstance(tag, str):
            raise ValueError(f"{location} tags[{position}] must be a string")
    return tuple(value)


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

        # Readers use the id as a display fallback when no prompt text exists.
        # It is missing metadata, not evidence that the prompt literally was
        # the id, so a later source may still fill it in.
        existing_text = "" if existing.text == existing.id else existing.text
        incoming_text = "" if item.text == item.id else item.text
        if existing_text and incoming_text and existing_text != incoming_text:
            raise ConflictingItem(
                f"item {item.id!r} has conflicting text; the same item id must "
                "identify the same eval case in every row and file"
            )
        if not existing_text and incoming_text:
            existing.text = incoming_text

        if existing.expected and item.expected and existing.expected != item.expected:
            raise ConflictingItem(
                f"item {item.id!r} has conflicting expected answers; the same "
                "item id must identify the same eval case in every row and file"
            )
        if not existing.expected and item.expected:
            existing.expected = item.expected
        if item.tags and not existing.tags:
            existing.tags = item.tags
        return existing

    def add_system(self, system: str) -> str:
        """Register a named comparison target before a score is available."""
        if system not in self.systems:
            self.systems.append(system)
        return system

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
        value = _unit_score(score)
        self.add_system(system)
        key = (item_id, system)
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
            "schema": NATIVE_SCHEMA,
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
        if "schema" not in raw:
            raise ValueError(f"matrix schema is missing; expected {NATIVE_SCHEMA!r}")
        if raw["schema"] != NATIVE_SCHEMA:
            raise ValueError(
                f"matrix schema is unsupported; expected {NATIVE_SCHEMA!r}"
            )

        systems = raw.get("systems", ())
        if not isinstance(systems, list):
            raise ValueError("matrix systems must be an array")

        matrix = cls()
        declared_systems: set[str] = set()
        for position, value in enumerate(systems, start=1):
            system = _native_identifier(value, "system", f"matrix systems[{position}]")
            if system in declared_systems:
                raise ValueError(
                    f"matrix systems[{position}] has a duplicate system identifier"
                )
            declared_systems.add(system)
            matrix.add_system(system)

        items = raw.get("items", ())
        if not isinstance(items, list):
            raise ValueError("matrix items must be an array")

        item_ids: set[str] = set()
        for position, entry in enumerate(items, start=1):
            if not isinstance(entry, dict):
                raise ValueError(f"matrix items[{position}] must be an object")
            if "id" not in entry:
                raise ValueError(
                    f"matrix items[{position}] has a missing item identifier"
                )
            item_id = _native_identifier(
                entry["id"], "item", f"matrix items[{position}]"
            )
            if item_id in item_ids:
                raise ValueError(
                    f"matrix items[{position}] has a duplicate item identifier"
                )
            item_ids.add(item_id)
            matrix.add_item(
                Item(
                    id=item_id,
                    text=_native_optional_string(
                        entry, "text", f"matrix items[{position}]"
                    ),
                    tags=_native_tags(entry, f"matrix items[{position}]"),
                    expected=_native_optional_string(
                        entry, "expected", f"matrix items[{position}]"
                    ),
                )
            )

            scores = entry.get("scores", {})
            if not isinstance(scores, dict):
                raise ValueError(f"matrix items[{position}] scores must be an object")
            repeats = entry.get("repeats", {})
            if not isinstance(repeats, dict):
                raise ValueError(f"matrix items[{position}] repeats must be an object")
            repeat_counts: dict[str, int] = {}
            for raw_system, value in repeats.items():
                system = _native_identifier(
                    raw_system,
                    "system",
                    f"matrix items[{position}] repeat",
                )
                if system not in declared_systems:
                    raise ValueError(
                        f"matrix items[{position}] repeat has an undeclared system "
                        "identifier"
                    )
                if raw_system not in scores:
                    raise ValueError(
                        f"matrix items[{position}] repeat has no corresponding score"
                    )
                repeat_counts[system] = _native_repeat_count(
                    value,
                    f"matrix items[{position}] repeat",
                )
            for raw_system, score in scores.items():
                system = _native_identifier(
                    raw_system,
                    "system",
                    f"matrix items[{position}] score",
                )
                if system not in declared_systems:
                    raise ValueError(
                        f"matrix items[{position}] score has an undeclared system "
                        "identifier"
                    )
                matrix.record(
                    item_id,
                    system,
                    float(score),
                    repetitions=repeat_counts.get(system, 1),
                )
        return matrix


def _unit_score(value: float) -> float:
    """Return a valid unit score, refusing ambiguous or non-finite values."""
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise InvalidScore(
            f"score must be a finite number in [0, 1], got {value!r}; "
            "normalize a known [MIN, MAX] scale explicitly with "
            "(score - MIN) / (MAX - MIN)"
        )
    return score
