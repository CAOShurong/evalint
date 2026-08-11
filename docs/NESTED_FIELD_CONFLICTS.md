# Nested field conflicts: path order must not change a score

Research snapshot: 2026-08-12.

## The failure users hit

EvalInt's generic JSON/JSONL importer accepts useful fields nested under
producer-specific objects such as `data`, `grader`, or `metadata`. Public
EvalInt v0.2.22 exposed each scalar under both its full flattened path and its
bare leaf name. When two paths ended in the same recognized leaf, a dictionary
update silently selected one value.

Two public installed-CLI fixtures contained the same members and differed only
in whether `grader` or `metadata` appeared first. One record supplied
`grader.score = 1` and `metadata.score = 0`. Both files exited `0`, but their
reports disagreed:

- one ranked beta above alpha, gave alpha a mean of `0.0`, and called the item
  informative with system spread `0.5`;
- the reordered object tied both systems at `1.0`, counted one
  `everyone_passes` item, and proposed dropping it as inert.

The fixtures are synthetic. They prove that path traversal order changed the
score and downstream audit; they do not measure prevalence, show a particular
producer is affected, or establish malicious intent.

This behavior contradicts the data model. RFC 8259 defines a JSON object as an
unordered collection, so member order cannot communicate which nested score a
generic importer should trust. Established normalization tools make conflicts
explicit. Current pandas documentation provides `record_prefix` and
`meta_prefix` to distinguish flattened names, and its implementation raises a
`Conflicting metadata name` error rather than overwriting one. Practitioner
questions show that the failure is initially confusing but the migration is
concrete: add a distinguishing prefix. A current OpenSearch Data Prepper report
likewise documents field-path collisions causing rejected records and requiring
explicit renaming/deletion rather than an implicit winner.

Sources:

- [RFC 8259: a JSON object is an unordered collection](https://www.rfc-editor.org/rfc/rfc8259#section-1)
- [pandas `json_normalize`: path separators and record/metadata prefixes](https://pandas.pydata.org/docs/reference/api/pandas.json_normalize.html)
- [pandas source: conflicting normalized metadata requires a prefix](https://github.com/pandas-dev/pandas/blob/99fc41da30855dc942c1a728f9670363d255498e/pandas/io/json/_normalize.py)
- [Practitioner question: overlapping normalized names need a prefix](https://stackoverflow.com/questions/52085169/valueerror-conflicting-metadata-name-name-need-distinguishing-prefix-in-pandas)
- [Data Prepper issue 5616: real field-path collisions and explicit migration](https://github.com/opensearch-project/data-prepper/issues/5616)

## Maintained alternatives considered

| Approach | Maintenance, license, security, dependency, operating and migration cost | Decision |
| --- | --- | --- |
| Keep whichever nested path is visited last | Zero migration, dependency, account, or service cost | Rejected. Reordering an unordered object changed both the ranking and item diagnosis. |
| Always prefer the first, last, shallowest, or deepest path | Zero new dependencies but invents one global producer contract | Rejected. `grader.score` and `metadata.score` have no universal precedence, and guessing can still produce a plausible wrong report. |
| pandas 3.0.5 `json_normalize` | Active, BSD-3-Clause, Python 3.11+, 84 declared requirement entries including optional entries; local with no account or service fee | Not selected. Its conflict refusal supports the decision, but the compiled data stack drops Python 3.9 and is disproportionate for selecting five field roles. |
| `flatten-dict` 0.5.0 | Active, MIT, Python 3.10+, zero declared requirements; local with no account or service fee | Not selected. Preserving full paths avoids data loss but still cannot decide which arbitrary path owns EvalInt's semantic score, and it drops Python 3.9. |
| JMESPath 1.1.0 with explicit field expressions | Active, MIT, Python 3.9+, zero declared requirements; local with no account or service fee | Deferred. Explicit mapping is sound for a known producer, but adding a mapping language, CLI surface, and per-export configuration is a larger migration than failing an ambiguous generic record. |
| Track recognized aliases during the existing bounded traversal | Python 3.9+, linear in inspected scalar fields, zero dependencies, accounts, network, or operating cost | Selected. It preserves broad nested-field compatibility while refusing only collisions that can affect an imported item, system, score, text, or expected answer. |

Package versions, Python requirements, licenses, declared requirements, release
activity, and repository state were checked through public PyPI and GitHub APIs
on the research date. Requirement-entry counts include optional and conditional
entries, so they indicate dependency surface rather than exact installed
package counts. These checks are not security audits and do not prove that an
alternative or this implementation is vulnerability-free. No third-party code
is copied or linked into EvalInt.

## Resulting contract

- The generic JSON array and JSONL reader still discovers recognized scalar
  fields within its existing bounded nesting depth.
- Every exposed recognized name is compared case-insensitively, matching the
  importer's existing field-name lookup. If two paths expose that name with
  different JSON scalar types or values, the record fails before any item,
  system, score, prompt text, or expected answer is selected.
- A full flattened path can also conflict with a direct field: for example,
  `item_id` and `item.id` cannot silently select different identities.
- Repeated paths with the same exact scalar type and value remain accepted.
  Conflicting unrecognized metadata is ignored because it cannot affect the
  audit.
- Errors name the JSON array record or physical JSONL line, but do not echo the
  field name, path, either value, prompt, answer, item id, or system name. The
  CLI exits `1`, writes no report to stdout, and emits no Python traceback.

## False positives, false negatives and migration

A producer may intentionally include distinct `score` leaves for different
purposes and expect EvalInt to choose one. The generic format never declared
which one was authoritative, so that record now fails. Migration is to export
one unambiguous recognized leaf, flatten the intended value into the documented
generic record shape, or use a supported schema-specific importer. Boolean
`true` and numeric `1` at competing paths also fail because they are distinct
JSON types, even though the compatibility score coercion would currently map
both to the same number.

The check does not infer conflicts between different aliases such as `score`
and `correct`; the existing documented alias priority remains deterministic.
It does not inspect arrays or fields deeper than the current generic traversal,
recover values already collapsed upstream, define a producer schema, or add a
user-configurable path mapping. Promptfoo and OpenAI Evals use their dedicated
readers rather than this generic flattener.

An unambiguous imported field can still be false, stale, fabricated, attached
to the wrong item, or selected from an incomplete export. This validation does
not authenticate a producer, prove provenance, completeness, independence,
correct scale, or security. A clean parse proves only that the recognized
fields examined in each generic record did not have conflicting path values.
