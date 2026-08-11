# Prompt variants are systems, not repeat runs

Research snapshot: 2026-08-12.

## The silent failure

EvalInt is meant to compare models **or prompt versions**. Promptfoo likewise
runs every configured prompt/provider pair and explicitly recommends multiple
prompt versions for performance comparison. Its current result type retains a
`promptId` on every row.

Public EvalInt v0.2.25 ignored that field and used only the provider id as the
system. A real `npx promptfoo@0.122.0 eval` fixture used two local providers,
two test cases, and two prompts: one prompt passed every assertion and the other
failed every assertion. No model API or cloud share was used. Promptfoo wrote
eight JSONL results across four provider/prompt combinations.

EvalInt v0.2.25 returned exit `0` but silently collapsed the file to two systems
and four observations. It averaged the good and bad prompt into a `0.5` mean
for both providers, declared both items inert, and reported that all items could
be dropped with the ranking preserved. The source artifact instead contained
four comparison systems: two with mean `1.0` and two with mean `0.0`.

Sources:

- [Promptfoo prompt configuration: create multiple versions to compare performance](https://www.promptfoo.dev/docs/configuration/prompts/)
- [Promptfoo configuration reference: each prompt/provider pair is run](https://www.promptfoo.dev/docs/configuration/reference/)
- [Promptfoo `select-best`: compare different prompt or model variations](https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/select-best/)
- [Current `EvaluateResult`: `promptId` and provider are stored per result](https://github.com/promptfoo/promptfoo/blob/main/src/types/index.ts)
- [Practitioner discussion: recurring need to compare four or five prompt versions](https://www.reddit.com/r/PromptEngineering/comments/1oj464l/tools_for_comparing_and_managing_multiple_prompt/)
- [Promptfoo issue 2453: separating comparisons into suites adds configuration and loses a unified report](https://github.com/promptfoo/promptfoo/issues/2453)

The practitioner reports are anecdotal evidence of the workflow, not adoption
evidence for EvalInt. The correctness defect is independently reproducible from
the current producer contract and actual local artifact.

## Reuse and alternatives considered

Project and package metadata were checked on 2026-08-12.

| Approach | Maintenance, license, dependencies, and platform fit | Cost and migration |
| --- | --- | --- |
| Use Promptfoo's viewer only | Promptfoo 0.122.0 is active and MIT; its npm package requires Node 22.22+ and declares about 80 direct runtime plus 42 optional dependencies | It correctly presents its own prompt/provider matrix, but it does not perform EvalInt's post-hoc item, reliability, duplicate, and reduction audit. Moving the analysis there does not repair EvalInt's import semantics. |
| Preprocess with [jq](https://github.com/jqlang/jq) | Maintained native cross-platform CLI under the jq license; no account or service | A custom script can construct `provider + promptId`, but every user must maintain the same producer-specific mapping and apply it consistently before every audit. |
| Split or relabel upstream runs | No new parser dependency | Separate files or duplicated provider labels require config changes and can require rerunning paid model calls. Separate reports also defeat the unified comparison the user requested. |
| Compose the two existing fields in EvalInt | Python standard library; zero new runtime dependencies, account, service, or network path | Selected. It changes only Promptfoo system identity, reuses the producer's explicit id, and works for JSON and JSONL already being audited. |

No Promptfoo code is copied. The two identifiers are read as data from its
public artifact format, so the existing MIT package and zero-dependency runtime
remain unchanged.

## Resulting contract

- A current row with `promptId` becomes a canonical system string containing
  prompt and provider ids. Since v0.2.27, a provider label distinct from its id
  is also included; see
  [`PROMPTFOO_PROVIDER_VARIANTS.md`](PROMPTFOO_PROVIDER_VARIANTS.md).
  Canonical JSON avoids delimiter ambiguity and escapes control characters.
- The exact opaque `promptId` is used; rendered prompt text and prompt labels
  are not included in the system identity. A distinct provider label is.
- The same provider id, provider label, and prompt id across repeated rows
  remains one system, so genuine stochastic repeats still aggregate as repeats.
- Different providers using the same prompt remain different systems, and one
  provider using different prompt ids becomes different systems.
- A present null, blank, boolean, or non-string `promptId` exits `1` before a
  report. The value is not echoed.
- Legacy results where the key is absent keep their provider-only identity.

Against the actual eight-row fixture, the changed source entry point returned
four systems, eight observations, means `1.0/1.0/0.0/0.0`, two retained items,
and no inert-item reduction. These are fixture facts, not a performance claim.

## False positives, false negatives, and limits

The boundary assumes Promptfoo assigns a different `promptId` when the prompt
version changes. If a producer reuses one id for different content, EvalInt
cannot detect the difference. If the key is missing entirely, legacy fallback
can still collapse variants; compatibility is preferred because old Promptfoo
documents did not place the id on every row.

Provider id remains the base provider component. Two materially different
provider configurations that reuse the same provider id, provider label, and
prompt id can still collapse; hidden configuration is not treated as proof of
independence. Conversely, two distinct prompt ids are treated as distinct even
if their rendered text happens to match, and two distinct provider labels split
even if their hidden configuration is identical. Those can be false-positive
distinctions, but silently merging producer-declared variants would corrupt the
comparison in the opposite and less observable direction.

The composite id is structural, not authentication. A clean audit does not
prove that the prompt ran, that every row was exported, that ids are truthful,
that prompt content is safe, or that scores use the intended rubric.
