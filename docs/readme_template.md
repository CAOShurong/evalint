# evalint

**Audit an LLM eval set the way you would audit an exam.**

[![CI](https://github.com/CAOShurong/evalint/actions/workflows/ci.yml/badge.svg)](https://github.com/CAOShurong/evalint/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/evalint.svg)](https://pypi.org/project/evalint/)
[![Python](https://img.shields.io/pypi/pyversions/evalint.svg)](https://pypi.org/project/evalint/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Every eval framework runs your test cases. None of them ask whether the test
cases are any good.

So you get a leaderboard: `claude-sonnet 0.729`, `gpt-4o 0.729`. Two numbers,
three decimal places, and no way to know whether that gap means anything, how
many of those 240 items could have told you anything in the first place, or
which of them are scored against an answer that is simply wrong.

`evalint` reads the results you already have and answers those questions.

<!--SHOT_REPORT-->

Nothing to instrument, nothing to install alongside it, no API key, no model.
It reads a CSV, a JSONL, a promptfoo dump or an OpenAI evals log, and it has
zero runtime dependencies.

---

## Install

```bash
pip install evalint
```

```bash
evalint results.csv
```

Python 3.9+. The only requirement is that the file compares **at least two
logical systems** — two models or two prompt versions. Repeated stochastic
runs of one system are averaged within that system; they improve its score
estimate but do not become independent systems. Every statistic here is about
telling systems apart, so one logical system is not a smaller version of the
answer; it is no answer, and the tool says so instead of printing something.

---

## What it tells you

### Whether the leaderboard means anything

**Reliability** (KR-20 / Cronbach's alpha) is the fraction of the spread
between your systems that is signal rather than noise. It is what licenses a
sentence like "A beat B", and almost nobody computes it for an eval set.

From that comes the **smallest real difference** — systems closer together
than this are not distinguishable by your set, however many decimal places
the leaderboard prints. In the example above that threshold is `0.026`, which
is why the top two are reported as tied rather than as first and second.

### What you are paying for and not using

An item that every system passes, or that none do, contributes an identical
constant to every system's total. It is arithmetically incapable of changing
the ranking — while still costing an API call on every run, forever.

The example set has 240 items. 58 of them cannot affect the answer, and 151
reproduce the ranking exactly: **37% fewer calls per run, same result.**

### Which items are broken

<!--SHOT_ITEM_MAP-->

Each dot is one eval item, placed by how hard it is and by how well it agrees
with everything else in the set.

The vertical axis is **discrimination**: the correlation between an item's
score and the system's score on every *other* item. A good item is passed
more often by the systems that do better overall — it sits above the line.

An item *below* the line is passed more often by the systems that do
**worse**. There is no version of "a hard question" that behaves that way.
In practice it means the expected answer is wrong, and the systems that
"pass" it are the ones that answer badly enough to match.

The example has ten of those, planted deliberately, and `evalint` names all
ten and nothing else.

---

## Reading your own results

Formats are detected by shape, not by filename, because everything in this
space writes `.json` and none of it is labelled.

| What you have | What to run |
| --- | --- |
| A CSV: `item_id, system, score` | `evalint results.csv` |
| A wide CSV: one column per model | `evalint results.csv` |
| JSONL records | `evalint results.jsonl` |
| promptfoo's `--output` JSON | `evalint promptfoo.json` |
| OpenAI evals logs (one run each) | `evalint gpt-4o.jsonl claude.jsonl` |
| One file per model | `evalint *.csv` |

Scores may be `1`/`0`, `true`/`false`, `PASS`/`FAIL`, or a float in `[0, 1]`
from a rubric or a judge model. Fractional scores keep their resolution:
rounding them at the door would make every statistic coarser than your data
actually is. Numeric values outside `[0, 1]`, plus `NaN` and infinity, exit
`1` before a report is produced. EvalInt does not silently clamp or guess a
scale: normalize a known `[MIN, MAX]` rubric explicitly with
`(score - MIN) / (MAX - MIN)`. The evidence and limitations are documented in
[`docs/SCORE_UNITS.md`](docs/SCORE_UNITS.md).

Input text must be UTF-8. A leading UTF-8 byte order mark (BOM), commonly used
for Excel-compatible CSV, is accepted. Invalid byte sequences exit `1` with
the byte position instead of silently changing an item or system id. EvalInt
does not guess legacy encodings; see [`docs/ENCODING.md`](docs/ENCODING.md) for
the safety decision and conversion options.

Several files are merged on the item id. The same system name always means the
same logical system: repeated item scores are averaged, while disjoint items
fill out the same column. Distinct models or prompt versions must therefore
have distinct `system` names in the source data. Reports show logical systems,
represented runs and raw score measurements separately.

Missing scores remain missing rather than becoming failures. When systems were
not scored on the same items, the text report shows the observed/expected cell
coverage and warns that means and ranks use different denominators. JSON
reports expose `observations`, `expected_observations`, and `coverage` in the
summary. An identifiable item remains in that denominator even when every one
of its score values is blank or unparseable; earlier releases silently removed
the whole item. If an explicitly named system has no usable score anywhere,
the audit exits `1` and names it instead of silently dropping it or ranking it
as zero. This warning does not impute data or make an incomplete comparison
valid; see [`docs/MISSING_SCORES.md`](docs/MISSING_SCORES.md).

Every nonblank JSONL and OpenAI Evals line must be complete JSON. A malformed
record exits `1` with its line and column instead of being skipped or leaking a
Python traceback. EvalInt never repairs a partial score record and then reports
on the survivors; see [`docs/MALFORMED_JSON.md`](docs/MALFORMED_JSON.md).

### In CI

```bash
evalint results.csv --fail-under 0.8
```

Exit `2` means the eval set has a problem; exit `1` means the audit itself
failed. Distinct, so a pipeline can tell them apart.

```bash
evalint results.csv --json | jq '.summary.reliability'
```

To save the reduced set's item ids, choose a separate output path:

```bash
evalint results.csv --save-reduced keep.txt
```

EvalInt refuses an output that is the same file as any input, including a
hard-link alias. It writes a complete temporary file in the destination
directory and replaces an existing non-input output only after the write and
flush succeed. Write failures exit `1` without a traceback or a partial target.
See [`docs/OUTPUT_SAFETY.md`](docs/OUTPUT_SAFETY.md) for the observed failure,
alternatives, and filesystem limits.

---

## What it will not claim

This section exists because the failure that matters is not "missed a
problem". It is naming an item that turns out to be fine — a reader who opens
two flagged items, finds nothing wrong and stops believing the rest has been
made worse off than if the tool had said nothing.

**A negative correlation alone is not evidence.** With a handful of systems,
an ordinary item that the weaker ones happened to get right looks exactly
like one whose answer key is wrong. Measured on five systems: genuinely
broken items land near −0.60, and *innocent* ones reach −0.71. The two
populations overlap completely, so no threshold can separate them.

What separates them is more columns, not a better cutoff. So every accusation
runs a **seeded permutation test** — the item's scores are shuffled against
the systems' overall scores, and the reported `chance` is how often a result
this negative comes out of pure luck. Items that clear it are listed as
`BROKEN`. Items that look inverted but cannot clear it get their own section
that says so:

> 19 items lean the wrong way, and 8 systems cannot rule out luck. More
> independent systems would settle it.

**With three systems, nothing can be proven.** There are only six possible
orderings, so the smallest achievable p-value is about 1/6. That is the
correct answer rather than a limitation to route around, and the report says
it instead of guessing.

**Reliability is not reported when it would be meaningless.** Fewer than
three systems, or no spread between them at all, and you get the reason
rather than a number. A reliability figure computed on two systems is
arithmetic without information, and it would be the most quotable wrong
number in the report.

**A missing score is not a zero.** Cells are stored sparsely, and every
statistic states what it was computed over. Treating "not run" as "failed" is
the single most misleading thing this tool could do.

**A repeated run is not a new system.** Promptfoo repeats, Inspect epochs and
duplicate `(item, system)` rows are averaged within the named system before
item statistics are computed. Counting correlated repeats as independent
columns is pseudoreplication: it can shrink a permutation p-value without
adding a genuinely independent model or prompt version. Repeat counts survive
matrix JSON round trips and remain visible in text and JSON reports.

**Duplicate detection is textual.** It uses character shingles and MinHash —
no embedding model, no API key, no GPU — so it finds copy-pasted-and-edited
items, which is what eval duplicates almost always are. Two items that mean
the same thing in completely different words are **not** detected. That needs
semantics, and the README saying so is enforced by a test.

**The reduction is verified, not assumed.** Every layer of it recomputes the
ranking on what would be left, and rolls back with a note if the ranking
moves:

> 47 near-duplicates were left in place: removing them changed the ranking,
> so they are not interchangeable despite the similar wording

That check was written after an early version reported "96% fewer calls" next
to a leaderboard that had quietly reversed.

---

## How it works

Classical test theory, which has been the standard toolkit in educational
measurement for about a century, pointed at eval sets instead of school
exams. Three quantities do the work:

- **Difficulty** — the mean score on an item. Zero variance means it cannot
  affect the ranking.
- **Discrimination** — the *corrected* item-total correlation. Corrected
  means the item is removed from the total it is compared against; leaving it
  in correlates the item with itself and flatters short sets most.
- **Reliability** — KR-20 over the items, and from it the standard error of
  measurement.

Duplicate detection is character 5-shingles → 64-permutation MinHash → banded
LSH for candidate pairs → an exact Jaccard check on every candidate. The
exact check is what keeps the output trustworthy; below a few hundred items
it skips the signatures entirely, because exhaustive comparison is faster and
cannot miss anything.

All of it is standard library. No numpy, no scipy, no pandas.

---

## Why this exists

There is a lot of tooling for *running* evals — promptfoo, OpenAI evals,
deepeval, Inspect, LangSmith — and it is good. There is very little for
asking whether the eval set itself is sound, which is strange, because the
same question about school exams has a century-old answer and a name.

The nearest things are dataset-quality advice in eval framework docs (which
is prescriptive rather than something you can run) and academic work on
benchmark contamination and saturation (which is about public benchmarks, not
the 200-row CSV your team actually ships against). Neither will tell you that
item 57 is scored against a wrong answer.

The evidence and maintained alternatives behind the repeat-run behavior are
recorded in [`docs/RESEARCH.md`](docs/RESEARCH.md). Runtime trust boundaries
and disclosure instructions are in [`SECURITY.md`](SECURITY.md).

---

## Full output

The figure at the top of this page, as text:

<!--TEXT_REPORT-->

## Command line

<!--TEXT_HELP-->

---

## Development

```bash
git clone https://github.com/CAOShurong/evalint
cd evalint
python -m pip install -e ".[dev]"
python -m pytest
```

The example set, the figures and the numbers quoted above are all generated
by running the tool:

```bash
python docs/make_example.py     # regenerate the example results
python docs/build_docs.py       # regenerate README.md and its figures
```

CI runs `python docs/build_docs.py --check`, so the documentation cannot
drift away from the code without a build going red.

---

## Licence

MIT
