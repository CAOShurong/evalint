# Promptfoo test identity: preserve cases that reuse variables

Research snapshot: 2026-08-12.

## The reproduced gap

Promptfoo defines each test case as one example input with optional description,
variables, assertions, metadata, provider filters, and other options. Different
cases may therefore reuse the same variables while testing different contracts.
Its current JSONL export assigns each case a numeric `testIdx`.

A real `npx promptfoo@0.122.0 eval` fixture used two local providers and two
test cases. Both cases had `{"case":"q1"}`, but one asserted `Answer q1` and
the other asserted `Alternate q1`. Promptfoo emitted four rows: `testIdx` 0 had
scores `[1, 0]`, while `testIdx` 1 had `[0, 1]`. No model API, account, share,
or cloud service was used.

Public EvalInt v0.2.28 exited `0` but collapsed the two cases into one item. It
reported four runs averaged into two observations, two tied means of `0.5`, and
zero informative items. The separate cases' opposite discrimination was lost,
and the report incorrectly described them as repeat runs. The fixture is
deliberately synthetic and is not evidence of users, adoption, or performance.

Evidence:

- [Promptfoo test-case reference: a test case is one example with description,
  variables, assertions, and metadata](https://www.promptfoo.dev/docs/configuration/reference/#test-case)
- [Promptfoo output formats: JSONL emits one result with `testIdx` per
  line](https://www.promptfoo.dev/docs/configuration/outputs/#jsonl-format)
- [Promptfoo issue 1076: users need separate groups that share the same
  variables](https://github.com/promptfoo/promptfoo/issues/1076)
- [Promptfoo issue 98: a practitioner considered separate test cases with the
  same variables to expose assertion-level performance](https://github.com/promptfoo/promptfoo/issues/98)
- [Promptfoo issue 1888: repeated execution is a separate first-class
  operation](https://github.com/promptfoo/promptfoo/issues/1888)

## Reuse and alternatives considered

Repository and package metadata were checked on 2026-08-12.

| Approach | Maintenance, license, dependencies, security and platform fit | Operating and migration cost |
| --- | --- | --- |
| Use Promptfoo's own table or viewer | Promptfoo 0.122.0 is active and MIT. Its Node package requires Node 22.22+ and declares about 80 direct runtime plus 42 optional dependencies. It preserves the upstream rows, but its viewer is a larger execution and display surface. | Best for inspecting one run, but it does not provide EvalInt's post-hoc reliability, item discrimination, or reduction audit. Existing EvalInt workflows must switch tools for analysis. |
| Add an unused unique variable to every case | No new software or license issue. The identifier remains visible in exported variables and may reach templates, custom providers, logs, or caches unless every path treats it as unused. | Requires editing and maintaining every ambiguous test definition, then rerunning or rewriting existing artifacts. Provider calls can cost money. |
| Preprocess with [jq](https://github.com/jqlang/jq) | jq is maintained, cross-platform native software under the jq license. A custom filter can inject an item id, but the script must understand Promptfoo revisions and avoid copying sensitive descriptions or assertions. | Adds a conversion step and user-owned identity policy to every audit. It cannot repair an artifact consistently unless the same script and ordering are retained. |
| Compose Promptfoo's native `testIdx` with variables only when variables are ambiguous | Uses Python's standard library, adds no dependency, account, network call, or copied Promptfoo code. The index is already present in current exports. | Selected. Existing unique-variable identities do not migrate; only silently collapsed cases receive new export-local identities. |

## Resulting contract

- For each Promptfoo artifact, EvalInt first finds nonempty variable mappings
  associated with more than one valid integer `testIdx`.
- Only those ambiguous mappings become canonical identities of the form
  `promptfoo:{"test_idx":0,"vars":{...}}`.
- A variable mapping used by one `testIdx` keeps the earlier variable-only
  identity. Rows that share both variables and index remain repeat measurements
  of one item/system cell.
- Description, assertions, metadata, rendered prompt, output, provider error,
  and provider configuration are not copied into the item identity.

The public v0.2.29 artifact must turn the real four-row fixture into two items,
four observations, four measurements, two run columns, and two informative
items through both automatic and forced Promptfoo routes. A normal two-case
fixture with unique variables must keep its existing identities, while rows
with the same variables and `testIdx` must still aggregate as repeats.

## Limits and falsifiable boundaries

`testIdx` is assigned inside one export, not authenticated or durable across
separate runs. Merging files is safe only when their case ordering and meaning
are known to match. The same variables and index can hide changed descriptions
or assertions across files. Conversely, two indices split intentionally
duplicated definitions even if a user meant them as correlated repeats; use
Promptfoo's repeat feature when stochastic repetition is intended.

A malformed producer that reuses one `testIdx` for distinct cases is a false
negative and can still collapse them. A producer that assigns different indices
to the same logical case is a false positive and keeps them separate. EvalInt
does not compare assertion bodies, descriptions, metadata, prompts, outputs, or
provider configuration to guess intent because doing so would create unstable
identities and copy more untrusted or sensitive content into reports.

A clean audit proves only how the supplied rows were grouped and scored. It
does not prove that the export is complete, the producer is authentic, test
cases are independent, assertions are correct, providers ran as configured, or
the resulting ranking generalizes.
