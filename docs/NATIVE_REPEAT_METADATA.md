# Native repeat metadata: counts must not change while being read

Research snapshot: 2026-08-12.

## The failure users hit

`evalint/matrix-v1` stores the mean score for one item-system cell and, when
that mean represents repeated measurements, a `repeats` count under the same
system key. Public EvalInt v0.2.17 did not validate that relationship before
turning the value into an integer:

- `2.9` was truncated to `2`, so a two-system fixture exited `0` and reported
  three measurements and three runs;
- the string `"3"` was silently accepted as three repetitions;
- `repeats: {"typo": 99}` exited `0` but discarded all 99 claimed
  measurements because `typo` was not a score key;
- a declared system's repeat count was also discarded when that item had no
  corresponding score for the system.

The fixtures are synthetic. They demonstrate a parser mechanism that changes
or drops measurement-count metadata; they do not establish how often a real
producer emits one of these shapes.

Python documents that conversion from `float` to `int` discards the fractional
part. JSON Schema instead distinguishes integer-valued JSON numbers from
fractional values, rejects numeric strings for an integer field, and uses
object constraints to reject or relate unexpected properties. Pydantic exposes
a strict mode for the same reason: coercion is convenient for user input but
can be wrong at a data-contract boundary. These are established contract
mechanisms, not dependencies EvalInt needs to reproduce wholesale.

Two current practitioner reports show the operational symptom of ignoring
unknown object keys. FastMCP can drop a misspelled tool argument and run with a
default, producing a successful but semantically wrong result. OpenCode can
discard an unknown nested configuration key while the server reports healthy.
EvalInt's repeat map is smaller in scope, but the failure is the same: a clean
exit hides that declared input was not used.

Sources:

- [Python numeric conversion: float to int discards the fractional part](https://docs.python.org/3/library/stdtypes.html#numeric-types-int-float-complex)
- [JSON Schema numeric types: integer values, fractional numbers, and strings](https://json-schema.org/understanding-json-schema/reference/numeric)
- [JSON Schema object properties and additional properties](https://json-schema.org/understanding-json-schema/reference/object)
- [JSON Schema dependent requirements](https://json-schema.org/understanding-json-schema/reference/conditionals#dependentRequired)
- [Pydantic strict mode and coercion](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- [FastMCP issue 3067: unknown arguments are silently dropped](https://github.com/modelcontextprotocol/python-sdk/issues/3067)
- [OpenCode issue 39431: unknown nested keys are silently discarded](https://github.com/anomalyco/opencode/issues/39431)

## Maintained alternatives considered

| Approach | Maintenance, license, security, dependency and migration cost | Decision |
| --- | --- | --- |
| Keep `int(value)` and ignore unmatched keys | Zero dependency and migration cost | Rejected. It produced the observed fractional truncation and silent 99-count loss. |
| `jsonschema` 4.26.0 | Active, MIT, Python 3.10+, 21 requirement entries including extras; local with no service cost | Rejected. It drops EvalInt's Python 3.9 support and adds a general validator for one small map contract. |
| Pydantic 2.13.4 strict models | Active, MIT, Python 3.9+, six requirement entries including a compiled core; local with no service cost | Rejected. Strict mode fits the policy, but migrating the zero-dependency data model is substantially heavier than the check. |
| `msgspec` 0.21.1 strict structs | Active, BSD-3-Clause, Python 3.10+, three requirement entries and compiled wheels; local with no service cost | Rejected. It drops Python 3.9 and requires replacing the existing JSON-to-model boundary. |
| Explicit relationship and count checks in `Matrix.from_dict()` | Python 3.9+, linear in repeat-entry count, zero dependencies, accounts, network or operating cost | Selected. It validates the existing writer's contract at the one native-reader boundary. |

Package and repository metadata were checked through public PyPI and GitHub
APIs on the research date. Requirement-entry counts include conditional and
optional entries and are dependency-surface signals, not exact installed
package counts. The repositories were active and not archived. Their public
GitHub advisory endpoints listed zero entries for jsonschema and msgspec and
one entry for Pydantic; those endpoint results are not security audits and do
not establish that any package is safe or unsafe. No third-party code is
copied or linked into EvalInt.

## Resulting contract

- Every `repeats` key must be a nonblank system identifier already declared
  by the matrix and present in that item's `scores` object.
- Every count must be a positive integer-valued JSON number. `2` and `2.0`
  both mean two under JSON Schema's numeric model; strings, booleans,
  fractional numbers, non-finite values and counts below one fail.
- Missing repeat metadata still means one measurement. A count of one is
  accepted even though `Matrix.as_dict()` normally omits it.
- The complete repeat map is validated before any score from that item is
  recorded. A bad later key cannot leave a partially imported item behind.
- Errors identify the one-based item position and the violated relationship,
  but do not echo system names, scores, prompts or count values. The CLI exits
  `1` with empty stdout and no Python traceback.

## False positives, false negatives and remaining boundary

Producers that quote counts as strings now fail even when the string contains
digits. Producers that used a repeat key without a score must either emit the
aggregate score for that same cell or remove the unsupported count. This is an
intentional migration cost: accepting either shape requires inventing or
discarding measurement metadata.

Integral JSON values written with a decimal point remain valid, avoiding a
false positive permitted by JSON Schema's integer semantics. Counts are not
capped because this parser does not allocate or loop once per claimed repeat;
an extreme count can still make a report misleading if the producer lied.

The check cannot prove that the claimed number of measurements exists, that
repeated runs were independent, or that their stored mean was calculated
correctly. Omitted repeat metadata still defaults to one. With an explicit
`--format matrix`, this release also does not yet reject a missing or unknown
top-level schema marker, and additional item metadata remains open-ended. A
clean import is a structural consistency result, not provenance, completeness,
statistical validity or a backup of the source runs.
