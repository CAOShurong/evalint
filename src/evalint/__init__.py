"""evalint -- audit an LLM eval set the way you would audit an exam.

Every eval framework runs your test cases. None of them ask whether the test
cases are any good. This does: what the set can actually measure, which items
cannot affect the answer, which ones look broken, and how many you could stop
paying for without changing the ranking.

    from evalint import audit_matrix, load_text

    matrix, _ = load_text(open("results.csv").read())
    audit = audit_matrix(matrix)
    print(audit.summary.reliability, audit.summary.reliability_verdict)
    for stat in audit.broken():
        print("check this item:", stat.item_id)
"""

from __future__ import annotations

from .dedupe import Cluster, find_duplicates, similarity
from .importers import (
    ImportError_,
    detect_format,
    load,
    load_many,
    load_text,
    merge,
    parse_text,
)
from .matrix import InvalidScore, Item, Matrix, System
from .reduce import Reduction, kendall_tau, reduce_set
from .report import Audit, audit_matrix, render
from .stats import ItemStats, SetStats, item_stats, set_stats

__version__ = "0.2.7"

__all__ = [
    "Audit",
    "Cluster",
    "ImportError_",
    "InvalidScore",
    "Item",
    "ItemStats",
    "Matrix",
    "Reduction",
    "SetStats",
    "System",
    "__version__",
    "audit_matrix",
    "detect_format",
    "find_duplicates",
    "item_stats",
    "kendall_tau",
    "load",
    "load_many",
    "load_text",
    "merge",
    "parse_text",
    "reduce_set",
    "render",
    "set_stats",
    "similarity",
]
