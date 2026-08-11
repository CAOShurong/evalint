# Required identifiers: refuse plausible reports from anonymous records

Research snapshot: 2026-08-12.

## The failure users hit

Every generic long-form result record needs two identities: the eval item and
the system that produced its score. Public EvalInt v0.2.15 did not enforce that
contract:

- four JSONL records whose `item_id` was `null` exited `0`; `str(None)` merged
  them into one item named `"None"` and two score cells;
- a long CSV with two blank `system` cells exited `0` and ranked an anonymous
  system named `""` above `beta`;
- two JSONL records without any item key were silently skipped, leaving the
  other two rows to produce a plausible one-item, two-system report.

The fixtures are synthetic and deliberately small. They demonstrate the
mechanism and consequence; they are not evidence that a particular exporter
or number of users has hit EvalInt itself.

The input condition is realistic. JSON distinguishes a missing property from
an explicit `null`, and a string schema still accepts `""` unless it also sets
`minLength`. W3C's tabular-data model gives an empty CSV cell a semantic null
value. Practitioners report LLM workflow outputs where a schema-declared string
arrives as `null`, an `id` is null, or model metadata visible in one node is
unavailable as `model_name` downstream. A generic importer therefore cannot
treat missing, null, and blank identity as harmless variants.

Sources:

- [JSON Schema string constraints](https://json-schema.org/understanding-json-schema/reference/string)
- [JSON Schema required properties](https://json-schema.org/understanding-json-schema/reference/object#required)
- [W3C model for tabular data](https://www.w3.org/TR/tabular-data-model/)
- [n8n issue 14559: a schema-declared string arrived as null](https://github.com/n8n-io/n8n/issues/14559)
- [n8n community: a model returned null for an id](https://community.n8n.io/t/structured-output-parser-issue/31984)
- [Practitioner report: downstream `model_name` is consistently null](https://www.reddit.com/r/n8n/comments/1mf4a9e/struggling_to_extract_llm_model_name_from_ai_node/)

## Maintained alternatives considered

| Approach | Maintenance, license, security, dependency and migration cost | Decision |
| --- | --- | --- |
| Keep skipping missing records and coercing null | Zero migration cost | Rejected. It produced the observed subset and identity merge without any error. |
| Warn and continue | Zero dependency cost, but automation can discard stderr and still consume a plausible report | Rejected. Identity is required to assign every score cell. |
| Invent an id from the row number, file name, or hash | Zero dependency cost but changes identity semantics and can prevent legitimate cross-file merging | Rejected. EvalInt cannot infer exporter intent. |
| `jsonschema` 4.26.0 | Active, MIT, Python 3.10+, 21 requirement entries including extras; local and no service cost | Rejected for the default CLI. It would drop Python 3.9 and adds a general schema stack for two narrow fields. |
| Pydantic 2.13.4 | Active, MIT, Python `>3.9`, six requirement entries including a compiled core; local and no service cost | Rejected. Model adoption and dependency/platform migration outweigh this boundary. GitHub lists one medium 2021 advisory affecting old Pydantic releases; that history is not evidence about current safety. |
| Pandera 0.32.1 | Active, MIT, Python 3.10+, 55 requirement entries including extras; designed for broader dataframe validation | Rejected. It narrows platform fit and is much heavier than the existing streaming-independent record model. |
| Explicit standard-library checks | Python 3.9+, linear in record count, zero runtime dependencies, accounts, network or format migration for valid inputs | Selected. It stops before statistics at the exact point identity would otherwise be lost. |

Package metadata and repository activity were checked through public PyPI and
GitHub APIs on the research date. Requirement-entry counts include conditional
and optional entries, so they indicate dependency surface rather than an exact
installed-package count. GitHub's published-advisory endpoints returned zero
entries for jsonschema and Pandera and one for Pydantic; absence from that
endpoint is not a security audit or proof that a package has no vulnerabilities.
No external validation code is copied or linked into EvalInt.

## Resulting contract

- Every nonblank generic JSONL line and every element of a generic JSON array
  must be an object with a recognized item identifier and system identifier.
- Long CSV rows must have non-null, nonblank item and system identifiers. Wide
  CSV rows must have a non-null, nonblank item identifier; a score under a
  blank system header is also rejected rather than discarded.
- Missing keys, explicit nulls, empty strings, and whitespace-only strings exit
  `1` before a report. JSONL errors name the physical line; JSON-array errors
  name the one-based record; CSV errors name the physical line where the
  logical row ends, which remains useful for quoted multiline cells.
- Diagnostics identify the field and location but do not echo the row or its
  other potentially sensitive values.
- Nonblank identifiers retain their exact spelling, including leading or
  trailing whitespace. EvalInt refuses absence but does not silently normalize
  identities and merge previously distinct records.
- Missing or unparseable **scores** keep their existing meaning: the named item
  and system remain in the coverage denominator while that score cell is
  unmeasured.
- Promptfoo and OpenAI Evals use their format-specific readers. Their event and
  metadata filtering is not changed by this generic-record rule.

## False positives, false negatives and remaining boundary

An exporter that mixes metadata-only objects into an otherwise generic JSONL
file will now be rejected. That is an intentional fail-closed choice for this
format, whose records promise one item/system pair each; users should select a
dedicated event-stream format or remove those objects explicitly. A producer
that deliberately uses whitespace as its entire identity is also rejected.

EvalInt does not trim valid identifiers. `"q1"` and `" q1 "` therefore remain
different, which avoids an unrequested merge but can miss aliases that another
system would normalize. It still accepts non-string scalar identifiers by
their existing string conversion, does not prove that two names represent
independent systems, and does not cross-check multiple recognized aliases in
one record. The native `evalint/matrix-v1` reader and dedicated third-party
event readers have their own structural contracts rather than this generic-row
location model.

A clean identifier check proves only that accepted generic records had usable
names at import time. It does not prove the input is complete, that no exporter
record was omitted before EvalInt saw it, that ids resolve in another dataset,
that system labels describe the intended models, or that the evaluation and
its statistics are valid.
