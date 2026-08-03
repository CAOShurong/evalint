#!/usr/bin/env python3
"""Generate the example eval results used by the README and the tests.

Deterministic from a fixed seed, so the numbers quoted in the README are
reproducible and CI can verify the documentation still matches the code.

The set is built to look like a real one that nobody has tended: mostly fine,
with the four defects that turn up again and again.

* items every system passes -- the demo suite everyone keeps for confidence
* items no system passes -- usually a grader that never matches
* items whose expected answer is wrong, so the weaker systems "pass" them
* copy-pasted near-duplicates, which make the set look bigger than it is

Eight systems, because the whole point of the tool is that fewer than about
that many cannot support a claim that an item is broken.
"""

from __future__ import annotations

import csv
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "example-results.csv"

#: The underlying ability of each system. Deliberately spread, and with two
#: close pairs, so the "these two are tied" logic has something to catch.
SYSTEMS = {
    "gpt-4o-mini": 0.52,
    "llama-3-8b": 0.38,
    "mistral-7b": 0.41,
    "claude-haiku": 0.63,
    "gpt-4o": 0.79,
    "claude-sonnet": 0.81,
    "gemini-flash": 0.66,
    "qwen-72b": 0.71,
}

TOPICS = [
    "arithmetic word problems",
    "SQL generation",
    "date parsing",
    "unit conversion",
    "JSON extraction",
    "summarisation",
    "code review",
    "regex writing",
    "tone rewriting",
    "citation lookup",
]

ITEMS = 240


SUBJECTS = [
    "an invoice",
    "a support ticket",
    "a git diff",
    "a log line",
    "a receipt",
    "a changelog",
    "a stack trace",
    "a CSV export",
    "a config file",
    "an email thread",
    "a PR description",
    "a shell transcript",
]
ASKS = [
    "Extract every date and normalise it to ISO 8601.",
    "Return the total as a number with no currency symbol.",
    "Say whether this describes a regression, in one word.",
    "Rewrite this for a customer who is already annoyed.",
    "List the table names this touches.",
    "Give the smallest regex that matches all of these and nothing else.",
    "Summarise what changed, in under twenty words.",
    "Name the file most likely to contain the bug.",
]


def _question(rng: random.Random, topic: str, index: int) -> str:
    """A question that reads like somebody wrote it, not like a template.

    Deliberately varied: eval items generated from one sentence pattern are
    textually near-identical to each other, which makes any surface-similarity
    duplicate check cluster the whole set together. Real sets are messier, and
    a demo that is not would flatter the tool.
    """
    subject = SUBJECTS[(index * 7 + rng.randrange(3)) % len(SUBJECTS)]
    ask = ASKS[(index * 5 + rng.randrange(2)) % len(ASKS)]
    return f"Given {subject} about {topic}: {ask}"


def build() -> list[dict]:
    rng = random.Random(20260803)
    rows: list[dict] = []
    rows_text: dict[str, str] = {}

    for index in range(ITEMS):
        topic = TOPICS[index % len(TOPICS)]
        text = _question(rng, topic, index)

        if index < 44:
            kind = "trivial"  # everyone passes: kept for confidence, buys nothing
        elif index < 56:
            kind = "impossible"  # nobody passes: the grader never matches
        elif index < 66:
            kind = "wrong-answer"  # the expected answer is wrong
        elif 150 <= index < 186:
            kind = "duplicate"  # copy-pasted and lightly edited
        else:
            kind = "normal"

        if kind == "duplicate":
            # The same question as an earlier one, reworded the way somebody
            # editing a spreadsheet would reword it.
            source = index - 84
            text = rows_text[f"item-{source:03d}"] + " Answer concisely."

        rows_text[f"item-{index:03d}"] = text

        for system, skill in SYSTEMS.items():
            if kind == "trivial":
                score = 1
            elif kind == "impossible":
                score = 0
            elif kind == "wrong-answer":
                # Graded against a wrong reference, so the systems that answer
                # badly are the ones that "match" it.
                score = 1 if skill < 0.6 else 0
            else:
                score = 1 if rng.random() < skill else 0
            rows.append(
                {
                    "item_id": f"item-{index:03d}",
                    "text": text,
                    "system": system,
                    "score": score,
                }
            )
    return rows


def main() -> int:
    rows = build()
    with open(OUT, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["item_id", "text", "system", "score"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"{OUT.name}: {len(rows)} rows, {ITEMS} items, {len(SYSTEMS)} systems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
