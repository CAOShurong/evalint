# Native score types: a boolean pass flag is not a numeric score

Research snapshot: 2026-08-12.

## The failure users hit

EvalInt's native `evalint/matrix-v1` writer emits each score as a JSON number
from 0 through 1. Public EvalInt v0.2.20 instead called `float(...)` on every
score value before validating the unit range. Real installed-CLI reproductions
showed that:

- JSON `true` and `false` silently became scores `1.0` and `0.0`;
- quoted values such as `"1"` and `"0.25"` silently became numeric scores;
- a boolean-score matrix exited `0` and produced an ordinary ranking;
- a quoted-score matrix produced the same ranking as a numeric matrix, hiding
  the producer's incompatible field type;
- JSON null, arrays, and objects failed only through implementation-level
  `float()` messages rather than the native-format contract.

The fixtures are synthetic. They prove the parser, ranking, and diagnostic
mechanism; they do not measure prevalence or establish external adoption.

JSON itself separates numbers, strings, and booleans. JSON Schema's numeric
reference accepts integer and fractional JSON numbers but explicitly rejects a
number inside a string. Python creates the accidental boolean behavior because
`bool` is a subclass of `int`; Python's own documentation discourages relying
on `False` and `True` as 0 and 1. An active GenAI observability proposal likewise
defines `gen_ai.eval.score` as a float and `gen_ai.eval.passed` as a separate
boolean field.

Practitioner requests show why silent coercion remains contentious. Pydantic's
strict-configuration request specifically cites `float` accepting `"1"` and
the bool/int edge; the requester said the missing boundary prevented a strong
workplace recommendation. A later bug report calls boolean-to-string coercion
unexpected even when numeric coercion was explicitly enabled.

Sources:

- [JSON Schema numeric types and quoted-number rejection](https://json-schema.org/understanding-json-schema/reference/numeric)
- [Python built-in types: booleans are integer subclasses, but numeric reliance is discouraged](https://docs.python.org/3/library/stdtypes.html#boolean-type-bool)
- [Pydantic issue 1098: practitioner request for strict configuration](https://github.com/pydantic/pydantic/issues/1098)
- [Pydantic issue 7820: unexpected boolean coercion](https://github.com/pydantic/pydantic/issues/7820)
- [OpenLLMetry issue 3460: separate float eval score and boolean pass attributes](https://github.com/traceloop/openllmetry/issues/3460)

## Maintained alternatives considered

| Approach | Maintenance, license, security, dependency, operating and migration cost | Decision |
| --- | --- | --- |
| Keep `float(...)` coercion | Zero migration and dependency cost; convenient for hand-authored files | Rejected. It made pass flags and quoted fields indistinguishable from the writer's numeric contract. |
| Accept booleans but reject strings | Small change, but preserves Python's implementation accident as native semantics | Rejected. Community eval conventions model numeric score and boolean pass as separate fields. |
| `jsonschema` 4.26.0 | Active, MIT, Python 3.10+, 21 declared requirement entries; local with no account or service cost | Rejected. It drops EvalInt's Python 3.9 support and is heavier than one scalar check. |
| Pydantic 2.13.4 strict models | Active, MIT, Python 3.9+, six requirement entries including a compiled core; local with no account or service cost | Rejected. A model/dependency migration is disproportionate to one versioned reader boundary. |
| msgspec 0.21.1 typed decoding | Active, BSD-3-Clause, Python 3.10+, three requirement entries and a compiled extension; local with no account or service cost | Rejected. It drops Python 3.9 and would replace more of the current JSON pipeline. |
| Explicit native score check | Python 3.9+, linear in score count, zero new dependencies, accounts, network, or operating cost | Selected. Every score emitted by `Matrix.as_dict()` already satisfies it. |

Versions, Python requirements, licenses, dependency metadata, and release
activity were checked through public PyPI and GitHub APIs on the research date.
Requirement-entry counts include optional and conditional declarations, so
they are dependency-surface signals rather than exact installed counts. OSV
queries for the exact versions in the table returned no affected entries; that
is a point-in-time database result, not a security audit or proof that the
packages or this implementation are vulnerability-free. No alternative code is
copied or linked into EvalInt.

## Resulting contract

- Every value inside a native item's `scores` object must be a JSON number.
  Integers and fractional numbers are accepted; strings, booleans, null,
  arrays, and objects fail before a score is recorded.
- A numeric value must still be finite and within `[0, 1]`. The native error
  identifies the one-based item position without echoing the rejected score,
  item id, system name, prompt, answer, or other item content.
- The CLI exits `1`, writes no report to stdout, and emits no Python traceback
  for a rejected native score.
- Generic CSV and third-party JSON/JSONL importers retain their documented
  compatibility coercion. CSV has no JSON scalar types, and some external
  producers use boolean pass/fail fields. This change governs only EvalInt's
  own versioned round-trip representation.

## False positives, false negatives and migration

Hand-authored native documents with quoted numeric scores now fail; remove the
quotes. Producers that wrote boolean pass flags into `scores` must emit numeric
`1` or `0`, or map their boolean field through a generic supported importer.
Ordinary `Matrix.as_dict()` round trips require no migration.

A numeric JSON value from 0 through 1 can still be wrong, stale, fabricated,
miscalibrated, reported on another scale that happens to fit the range, or
attached to the wrong item or system. The check does not authenticate a grader,
prove score independence, reconstruct omitted measurements, or distinguish a
deliberate binary numeric score from a converted boolean. A clean parse proves
only that the serialized value has the native score type and unit range.
