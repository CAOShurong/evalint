"""Finding eval items that are the same question twice.

Duplicates are the quietest way an eval set lies. Two hundred items of which
sixty are rephrasings of each other do not measure two hundred things; they
measure a hundred and forty, with sixty of them counted twice. Every average
computed over that set is weighted towards whatever the duplicates happen to
test, and every confidence interval is narrower than the evidence supports,
because the arithmetic assumes independent observations and gets correlated
ones.

The usual answer is an embedding model, which means an API key, a GPU, or
both, plus a dependency heavier than the tool using it. That is a lot to ask
of someone who just wants to know whether their test set is sound. So this
uses character shingles and MinHash: no model, no network, no dependencies,
and it finds rephrasings that share surface form -- which is what a
copy-pasted-and-edited eval item almost always is.

What it deliberately does not claim: two items that mean the same thing in
completely different words are not detected. That needs semantics. The report
says so rather than implying the set is clean.
"""

from __future__ import annotations

import re
import unicodedata
import zlib
from dataclasses import dataclass, field

__all__ = ["Cluster", "find_duplicates", "normalise", "shingles", "similarity"]

#: Characters per shingle. Five is the usual choice for near-duplicate text:
#: short enough to survive small edits, long enough that ordinary English
#: does not collide by accident.
SHINGLE = 5

#: MinHash permutations. This only has to be a *recall* filter -- every
#: surviving pair is then checked exactly -- so accuracy costs less than speed
#: is worth. 64 estimates Jaccard to about +/-0.12, which is ample for
#: deciding whether a pair is worth an exact comparison, and halves the work.
HASHES = 64

#: Jaccard similarity at or above this is treated as the same item. Set from
#: what real eval sets look like: rephrasings of one question land around
#: 0.75-0.95, genuinely different questions on the same topic rarely clear
#: 0.5.
THRESHOLD = 0.8

#: Bands for locality-sensitive hashing. 16 bands of 4 rows over 64 hashes
#: gives a steep cutoff near 0.8: pairs above it are almost always compared,
#: pairs well below it almost never are.
BANDS = 16

#: Below this many items, exact pairwise comparison is cheaper than building
#: signatures at all, and it cannot miss anything.
EXACT_BELOW = 400

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def normalise(text: str) -> str:
    """Strip the differences that are not differences.

    Case, punctuation, whitespace runs and Unicode composition all vary
    between two copies of the same question without changing the question.
    Accents are kept: in an eval set they are as likely to be the point as
    they are to be noise.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = _PUNCTUATION.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def shingles(text: str, width: int = SHINGLE) -> set[int]:
    """Overlapping character n-grams, hashed.

    Characters rather than words, because eval items are often short and
    word-level shingles on a ten-word question leave too few to compare.
    Hashed to ints so the sets stay small on long items.
    """
    cleaned = normalise(text)
    if not cleaned:
        return set()
    if len(cleaned) <= width:
        return {zlib.crc32(cleaned.encode("utf-8"))}
    return {
        zlib.crc32(cleaned[i : i + width].encode("utf-8"))
        for i in range(len(cleaned) - width + 1)
    }


def similarity(left: str, right: str) -> float:
    """Exact Jaccard similarity of two texts' shingles."""
    a, b = shingles(left), shingles(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


#: Mixing constants for the hash permutations. Odd multipliers over a 32-bit
#: modulus, which is enough independence for MinHash and needs no library.
_MASK = 0xFFFFFFFF
_MULTIPLIERS = tuple(2 * i + 1 for i in range(HASHES))
_ADDENDS = tuple((i * 0x9E3779B1) & _MASK for i in range(HASHES))


def _signature(values: set[int]) -> tuple[int, ...]:
    """MinHash signature: the smallest value under each permutation."""
    if not values:
        return tuple([_MASK] * HASHES)
    # min() over a generator rather than an explicit loop: the comparison then
    # happens in C, which is most of the difference on a set of any size.
    return tuple(
        min(((value * multiplier) + addend) & _MASK for value in values)
        for multiplier, addend in zip(_MULTIPLIERS, _ADDENDS)
    )


@dataclass
class Cluster:
    """A group of items that are the same question."""

    #: The item kept when the cluster is collapsed: the first by id, so the
    #: choice is stable between runs rather than dependent on dict order.
    keeper: str
    duplicates: list[str] = field(default_factory=list)
    #: Lowest pairwise similarity inside the cluster, so a reader can see how
    #: near "near-duplicate" actually was.
    similarity: float = 1.0

    @property
    def size(self) -> int:
        return 1 + len(self.duplicates)

    def as_dict(self) -> dict:
        return {
            "keeper": self.keeper,
            "duplicates": list(self.duplicates),
            "size": self.size,
            "similarity": round(self.similarity, 4),
        }


def _candidate_pairs(usable: dict[str, str]) -> set[tuple[str, str]]:
    """Pairs worth an exact comparison.

    Small sets skip MinHash entirely: below a few hundred items, comparing
    every pair outright is faster than building signatures, and it cannot miss
    a pair the way a probabilistic filter can.
    """
    ids = sorted(usable)
    if len(ids) < EXACT_BELOW:
        return {(left, right) for i, left in enumerate(ids) for right in ids[i + 1 :]}

    signatures = {item_id: _signature(shingles(usable[item_id])) for item_id in ids}
    rows = max(1, HASHES // BANDS)
    buckets: dict[tuple[int, tuple[int, ...]], list[str]] = {}
    for item_id, signature in signatures.items():
        for band in range(BANDS):
            key = (band, signature[band * rows : (band + 1) * rows])
            buckets.setdefault(key, []).append(item_id)

    candidates: set[tuple[str, str]] = set()
    for members in buckets.values():
        if len(members) < 2:
            continue
        # A bucket holding a large slice of the corpus means those items are
        # all alike; capping keeps one pathological bucket from turning this
        # quadratic over the whole set. Reported by the caller rather than
        # hidden, since it is the one place recall is knowingly traded away.
        ordered = sorted(members)[:200]
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                candidates.add((left, right))
    return candidates


def find_duplicates(
    texts: dict[str, str],
    *,
    threshold: float = THRESHOLD,
) -> list[Cluster]:
    """Group items whose text is near-identical.

    Banded LSH first to find candidate pairs, then an exact Jaccard check on
    each candidate. The exact check is what keeps the output trustworthy:
    MinHash estimates, and an estimate alone would let through pairs that are
    not really duplicates, in a report whose whole point is precision.
    """
    usable = {item_id: text for item_id, text in texts.items() if normalise(text)}
    if len(usable) < 2:
        return []

    candidates = _candidate_pairs(usable)

    # Union-find over the confirmed pairs, so a chain of rephrasings ends up
    # as one cluster rather than several overlapping pairs.
    parent: dict[str, str] = {item_id: item_id for item_id in usable}
    lowest: dict[str, float] = {}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for left, right in sorted(candidates):
        score = similarity(usable[left], usable[right])
        if score < threshold:
            continue
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a
        root = find(left)
        lowest[root] = min(lowest.get(root, 1.0), score)

    grouped: dict[str, list[str]] = {}
    for item_id in usable:
        root = find(item_id)
        grouped.setdefault(root, []).append(item_id)

    clusters = []
    for root, members in grouped.items():
        if len(members) < 2:
            continue
        members.sort()
        clusters.append(
            Cluster(
                keeper=members[0],
                duplicates=members[1:],
                similarity=lowest.get(root, 1.0),
            )
        )
    clusters.sort(key=lambda c: (-c.size, c.keeper))
    return clusters
