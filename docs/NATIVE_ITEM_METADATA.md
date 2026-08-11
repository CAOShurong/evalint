# Native item metadata: preserve absence instead of inventing text

Research snapshot: 2026-08-12.

## The failure users hit

EvalInt's native `evalint/matrix-v1` writer emits item `text` and `expected`
values as JSON strings and `tags` as an array of strings. Public EvalInt
v0.2.19 accepted other JSON types and coerced them after parsing:

- four distinct items with `"text": null` became four copies of the literal
  text `"None"`. The real CLI exited `2` and reported one duplicate cluster of
  size four even though the producer had supplied no prompt text;
- otherwise identical items with the `text` property omitted retained the
  empty default and produced no duplicate cluster;
- `"tags": "safety"` became six labels, `s`, `a`, `f`, `e`, `t`, and `y`, and
  the native round trip persisted that character array;
- numeric text and expected-answer values became plausible strings, while a
  null tag array failed with an implementation-level iterable error.

These fixtures are synthetic. They reproduce the parser and report mechanism;
they do not measure how often external producers emit these shapes or establish
external adoption.

The distinction is part of JSON's data model, not an EvalInt invention. JSON
Schema treats `null` as different from an absent property, constrains strings
with `type: string`, and represents a tag list as an array whose `items` can
each be constrained to strings. Practitioner reports in pandas show the same
class of downstream surprise: coercing missing values to strings can create the
literal `"nan"`, and missing string values represented as `None` can disrupt
downstream machine-learning consumers.

Sources:

- [JSON Schema types and their Python equivalents](https://json-schema.org/understanding-json-schema/reference/type)
- [JSON Schema: null is not the same as absence](https://json-schema.org/understanding-json-schema/reference/null)
- [JSON Schema example: optional tags as an array of strings](https://json-schema.org/learn/getting-started-step-by-step)
- [pandas issue 25353: missing values coerced to the literal string `nan`](https://github.com/pandas-dev/pandas/issues/25353)
- [pandas issue 55721: `None` string values affecting downstream ML](https://github.com/pandas-dev/pandas/issues/55721)

## Maintained alternatives considered

| Approach | Maintenance, license, security, dependency, operating and migration cost | Decision |
| --- | --- | --- |
| Keep `str(...)` and `tuple(...)` coercion | No migration or dependency cost, but invents prompt/answer text and treats one tag as characters | Rejected. The public reproduction changed duplicate-detection input and the serialized label structure. |
| Treat `null` as missing with `value or ""` / `value or []` | Zero dependencies and a small compatibility change | Rejected. It silently repairs a producer type error and also collapses other falsey values instead of preserving a versioned contract. |
| `jsonschema` 4.26.0 | Active, MIT, Python 3.10+, 21 declared requirement entries; local with no account or service cost | Rejected. It drops EvalInt's Python 3.9 support and is heavier than three fixed field checks. |
| Pydantic 2.13.4 strict models | Active, MIT, Python 3.9+, six requirement entries including a compiled core; local with no account or service cost | Rejected. Model and dependency migration outweigh a targeted reader boundary. |
| msgspec 0.21.1 typed decoding | Active, BSD-3-Clause, Python 3.10+, three requirement entries and a compiled extension; local with no account or service cost | Rejected. It drops Python 3.9 and would replace more of the existing JSON pipeline than this defect requires. |
| Explicit checks in `Matrix.from_dict()` | Python 3.9+, linear in item and tag count, zero new dependencies, accounts, network, or operating cost | Selected. Every document emitted by `Matrix.as_dict()` already satisfies these types. |

Versions, Python requirements, licenses, dependency metadata, and latest release
activity were checked through public PyPI and GitHub APIs on the research date.
Requirement-entry counts include conditional and optional declarations, so they
are dependency-surface signals rather than exact installed-package counts.
OSV queries for the exact versions in the table returned no affected entries;
that is a point-in-time database result, not a security audit or proof that the
packages or this implementation are vulnerability-free. No alternative code is
copied or linked into EvalInt.

## Resulting contract

- Omitted `text` and `expected` properties remain valid and mean the empty
  string. When present, each property must be a JSON string; null, numbers,
  booleans, objects, and arrays fail rather than being stringified.
- An omitted `tags` property remains valid and means an empty list. When
  present, it must be a JSON array and every element must be a string. Empty
  strings and duplicate tag strings remain valid free-form labels.
- Values are preserved exactly. EvalInt does not trim, normalize, deduplicate,
  translate, or assign semantics to item tags.
- Diagnostics identify the one-based item and tag position but do not echo the
  rejected prompt, expected answer, tag, score, or other item content.
- The CLI exits `1`, writes no report to stdout, and emits no Python traceback
  for these invalid native documents.

## False positives, false negatives and migration

A hand-authored document that used JSON null to mean missing metadata now
fails. Omit the property, use `""` for missing text or expected answers, and
use `[]` for no tags. This matches the format's existing writer, so ordinary
`Matrix.as_dict()` round trips require no migration.

The check validates JSON types only. A string may still be false, stale,
misleading, duplicated under another spelling, or attached to the wrong item.
An omitted prompt remains invisible to duplicate detection; tag strings are not
currently used by EvalInt's statistics. A clean parse therefore does **not**
prove that item metadata is true, complete, safe to display in another context,
or sufficient to establish dataset identity or provenance.
