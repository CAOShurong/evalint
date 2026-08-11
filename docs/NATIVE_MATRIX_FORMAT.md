# Native matrix identity: one item and one system mean one thing

Research snapshot: 2026-08-12.

## The failure users hit

`evalint/matrix-v1` is EvalInt's own round-trip format, emitted by
`Matrix.as_dict()` and accepted by `Matrix.from_dict()`. Public EvalInt v0.2.16
did not enforce the identity invariants its writer already follows:

- `systems: ["alpha", "alpha", "beta"]` exited `0`, reported three systems,
  listed `alpha` twice in the ranking, and counted three represented runs even
  though only two distinct systems existed;
- two entries with the same item id exited `0`, collapsed to one item, and
  turned their four score values into repeated measurements without saying the
  input contained duplicate item objects;
- an item id of JSON `null` became the string `"None"`, while an empty system
  name became an anonymous ranked system;
- a score key absent from the declared `systems` array silently appended a new
  system, so a typo could change the comparison set.

All fixtures are synthetic. They prove the parser mechanism and the resulting
counts; they are not evidence of external adoption or a measured incidence
rate.

The invariant has established representations. JSON Schema separates array
element type from uniqueness through `items` and `uniqueItems`, and separates
string type from nonempty length. The maintained LM Evaluation Harness release
notes explicitly changed duplicate task/group configurations from silent
overwriting to a visible skip. A Hugging Face Datasets request describes stable
dataset ids as necessary for finding evaluation items. These are not drop-in
implementations for EvalInt, but they show why identity is data, not display
metadata.

Sources:

- [JSON Schema array items and uniqueness](https://json-schema.org/understanding-json-schema/reference/array)
- [JSON Schema string type and length](https://json-schema.org/understanding-json-schema/reference/string)
- [LM Evaluation Harness releases: duplicate configs are no longer silently overwritten](https://github.com/EleutherAI/lm-evaluation-harness/releases)
- [Hugging Face Datasets issue 6532: id-based lookup during inference/evaluation](https://github.com/huggingface/datasets/issues/6532)

## Maintained alternatives considered

| Approach | Maintenance, license, security, dependency and migration cost | Decision |
| --- | --- | --- |
| Keep duplicates and infer systems from score keys | Zero migration cost | Rejected. The public reproduction counted one name twice and let a typo change the comparison set. |
| Deduplicate by keeping the first/last entry | Zero dependency cost, but discards declared scores or metadata and invents precedence | Rejected. A versioned round-trip file should be repaired at its source. |
| Coerce scalar ids to strings | Matches the earlier parser but makes JSON `1` collide with `"1"` and JSON null become `"None"` | Rejected for EvalInt's own format. Generic importers retain their compatibility policy. |
| `jsonschema` 4.26.0 | Active, MIT, Python 3.10+, 21 requirement entries including extras; local and no service cost | Rejected. It drops Python 3.9 and adds a general validator for a small fixed contract. |
| `fastjsonschema` 2.22.1 | Active, BSD-3-Clause, Python `>3.10`, eight requirement entries including extras; code-generating validator | Rejected. It narrows platform fit and code generation is unnecessary for this local boundary. |
| Pydantic 2.13.4 | Active, MIT, Python `>3.9`, six requirement entries including a compiled core | Rejected. Model/dependency migration is heavier than validating the existing serializer contract. |
| Explicit checks in `Matrix.from_dict()` | Python 3.9+, linear in item/system count, zero dependencies, accounts, network or operating cost | Selected. Every valid `Matrix.as_dict()` round trip already satisfies it. |

Package and repository metadata were checked through public PyPI and GitHub
APIs on the research date. Requirement-entry counts include conditional and
optional entries, so they are dependency-surface signals rather than exact
installed-package counts. Published GitHub advisory endpoints listed zero
entries for jsonschema and fastjsonschema and one medium 2021 advisory for old
Pydantic releases. Those endpoint results are not security audits and do not
prove absence or presence of a current vulnerability. No external validator
code is copied or linked into EvalInt.

## Resulting contract

- The root `schema` property is required and must be exactly
  `evalint/matrix-v1`; see [the version contract](NATIVE_SCHEMA_VERSION.md).
- `systems` and `items` are JSON arrays. Every system identifier and item `id`
  is a string containing at least one non-whitespace character.
- Optional item `text` and `expected` values are strings, while `tags` is an
  array of strings. Missing properties retain the writer's empty defaults;
  null or other mismatched types fail instead of being coerced. See
  [the item metadata contract](NATIVE_ITEM_METADATA.md).
- System identifiers are unique within `systems`; item identifiers are unique
  within `items`. Diagnostics identify the one-based array position but do not
  echo the identifier, score, prompt, answer, or other row data.
- Every `scores` key is a nonblank string already declared in `systems`. A typo
  cannot silently add another comparison target.
- Every score value is a finite JSON number in `[0, 1]`; booleans, quoted
  numbers, null, arrays, and objects fail instead of being coerced. See
  [the native score-type contract](NATIVE_SCORE_TYPES.md).
- Every JSON object uses each exact member name at most once, including the
  root schema marker and nested score objects. See
  [the duplicate-member contract](DUPLICATE_JSON_MEMBERS.md).
- `scores` and `repeats`, when present, are objects. Repeated measurements use
  the existing per-item `repeats` map written by `Matrix.as_dict()` rather than
  duplicate item or system entries. Repeat keys must have a corresponding score
  and positive integer-valued count; see
  [the repeat metadata contract](NATIVE_REPEAT_METADATA.md).
- Nonblank whitespace is preserved exactly. The reader validates identity but
  does not normalize names or merge spelling variants.
- Import errors are wrapped as bounded `invalid evalint matrix` messages. The
  CLI exits `1` with empty stdout and no Python traceback.

## False positives, false negatives and remaining boundary

Hand-authored files that omitted `systems` and relied on score keys to infer
the comparison set now fail. Numeric ids that the old reader stringified also
fail. Neither shape is emitted by `Matrix.as_dict()`; migration requires
declaring the systems once and representing ids as explicit JSON strings.

Uniqueness is exact. `"alpha"` and `" alpha "` remain distinct, as do Unicode
lookalikes and case variants. Additional top-level or item metadata is still
allowed, and this targeted reader is not a complete JSON Schema implementation.
It does not authenticate identifiers, prove systems are independent, prove
items are the same cases as another dataset, or detect a producer that omitted
an item before serialization.

A clean native-matrix check means only that the accepted file preserved the
identity structure EvalInt itself writes. It does not validate answer keys,
scores, evaluation provenance, dataset completeness, or the statistical claims
of the resulting audit.
