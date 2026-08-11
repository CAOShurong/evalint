# Duplicate JSON members: do not let the last value silently win

Research snapshot: 2026-08-12.

## The failure users hit

Public EvalInt v0.2.21 decoded JSON into an ordinary Python dictionary. When
one object repeated a member name, the later value silently replaced the
earlier one. Public installed-CLI reproductions showed that:

- a native document declaring `evalint/matrix-v2` and then repeating `schema`
  as `evalint/matrix-v1` bypassed the version gate and produced an ordinary
  exit-`0` report;
- repeating a native score changed `1` to `0` before ranking;
- repeating a generic JSONL score did the same thing on that record.

The fixtures are synthetic. They prove the parser and report mechanism, not
that a particular producer is malicious or that users have already received
such files.

RFC 8259 says object member names should be unique. It also explains why this
is an interoperability boundary rather than harmless style: implementations
disagree, with some reporting only the last pair, some reporting an error, and
others exposing all pairs. The Python standard library deliberately accepts
an `object_pairs_hook`, which receives the ordered pairs before constructing a
dictionary and therefore before a repeated name can be lost.

The open CPython request for duplicate-key warnings documents real practitioner
friction and the trade-off. One user reported hitting the problem more than
once with external JSON and noted that JSON Schema cannot validate it after
ordinary loading. Another expected an exception after spending time finding
the cause. A maintainer objected to imposing overhead on every standard-library
load for a rare case, while a later commenter recommended `object_pairs_hook`
for callers that need strict validation. EvalInt is exactly such a targeted
external-data boundary, so it can opt in without changing Python globally.

Sources:

- [RFC 8259 section 4: object member uniqueness and parser disagreement](https://www.rfc-editor.org/rfc/rfc8259#section-4)
- [Python `json.loads` and `object_pairs_hook`](https://docs.python.org/3/library/json.html#json.loads)
- [CPython issue 89217: duplicate-key warning request and practitioner reports](https://github.com/python/cpython/issues/89217)

## Maintained alternatives considered

| Approach | Maintenance, license, security, dependency, operating and migration cost | Decision |
| --- | --- | --- |
| Keep Python's last-member-wins result | Zero migration or dependency cost | Rejected. The public reproduction changed the supported schema version and core score while still returning a plausible report. |
| Keep the first or expose all pairs | Zero new dependency with a custom representation, but invents semantics that EvalInt's object-shaped formats do not define | Rejected. Different parsers would still disagree and downstream importers expect one value per name. |
| Validate the resulting dictionary with `jsonschema` 4.26.0 | Active, MIT, Python 3.10+, 21 requirement entries; local with no account or service fee | Rejected. A dictionary has already lost the repeated pair, and the package would also drop EvalInt's Python 3.9 support. |
| Replace the import models with Pydantic 2.13.4 | Active, MIT, Python 3.9+, six requirement entries including a compiled core; local with no account or service fee | Rejected. It is a much larger model migration and still needs duplicate detection at the decoding boundary. |
| Replace the decoder with msgspec 0.21.1 | Active, BSD-3-Clause, Python 3.10+, three requirement entries and a compiled extension; local with no account or service fee | Rejected. It drops Python 3.9 and replaces the parser for a boundary the standard library already exposes. |
| Use `json.loads(..., object_pairs_hook=...)` in actual readers | Python 3.9+, linear in object members, zero dependencies, accounts, network or operating cost | Selected. It rejects ambiguity before any pair is discarded and preserves the existing object representation. |

Versions, Python requirements, licenses, dependency metadata, and issue state
were checked through public PyPI and GitHub APIs on the research date.
Requirement-entry counts include optional and conditional declarations, so
they are dependency-surface signals rather than exact installed counts. These
checks are not security audits and do not prove that an alternative or this
implementation is vulnerability-free. No third-party code is copied or linked
into EvalInt.

## Resulting contract

- EvalInt's actual readers reject a repeated name in any JSON object, including
  nested objects. This applies to native matrices, generic JSON arrays and
  JSONL, Promptfoo documents, and OpenAI Evals JSONL events.
- The same name may appear once in each of several separate objects. JSON arrays
  may therefore contain many normal records with `score`, `item_id`, or other
  shared field names.
- Automatic detection remains a shape probe. The selected reader performs the
  strict check, so a recognized native or third-party shape gets a useful
  duplicate-member error instead of being downgraded to an unknown format.
- A document error names its format; a JSONL error also gives the physical
  line. It does not echo the repeated name, either value, prompt text, answer,
  item id, or system name. The CLI exits `1`, writes no report to stdout, and
  emits no Python traceback.

## False positives, false negatives and migration

A producer that intentionally repeated a name and relied on first-wins,
last-wins, or multi-value behavior now fails. Migration is to emit the name
once with the intended value. This is an intentional compatibility break at
the input boundary because no single interpretation is portable across JSON
implementations.

The check cannot recover a member already discarded by an upstream parser. It
does not detect semantically overlapping aliases such as `score` and `result`,
case variants, duplicate records, repeated item objects, or two different names
that a producer intended to mean the same thing. It also does not authenticate
the file, establish provenance, prove completeness, validate every field, or
show that an accepted score is true. A clean parse proves only that each object
presented directly to EvalInt used each exact member name at most once.
