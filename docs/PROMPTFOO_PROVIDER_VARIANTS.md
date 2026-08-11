# Promptfoo provider labels preserve configured variants

Research snapshot: 2026-08-12.

## The silent failure

Promptfoo supports multiple configurations of one provider. Its provider
objects carry both an `id` and optional display `label`; filtering accepts
either value, and current `EvaluateResult` rows retain both. A practitioner
request specifically asked how to run several instances of one custom provider
with different model or temperature settings.

Public EvalInt v0.2.26 combined only provider id and `promptId`. A real
`npx promptfoo@0.122.0 eval` fixture used one local JavaScript provider twice.
Both instances deliberately returned `local:same-id`, while the configuration
labels were `pass-config` and `fail-config`. Two prompt versions and two test
cases produced eight JSONL rows across four labelled provider/prompt
combinations. The pass configuration scored `1.0` and the fail configuration
scored `0.0` for both prompts. No external model API or cloud share was used.

EvalInt v0.2.26 returned exit `0` but reported only two systems and four
observations. Each apparent prompt system had mean `0.5`, both items were
declared inert, and the reduction claimed every item could be dropped. The
source artifact instead contained four logical systems, means
`1.0/1.0/0.0/0.0`, and eight observations.

Sources:

- [Promptfoo provider configuration: object form supports id, label, and config](https://www.promptfoo.dev/docs/providers/)
- [Promptfoo configuration guide: a provider file can set id, label, and temperature](https://www.promptfoo.dev/docs/configuration/guide/)
- [Promptfoo reference: provider filtering matches either id or label](https://www.promptfoo.dev/docs/configuration/reference/)
- [Promptfoo JavaScript provider configuration passes label and config](https://www.promptfoo.dev/docs/providers/custom-api/)
- [Current `EvaluateResult`: each result stores provider id and label](https://github.com/promptfoo/promptfoo/blob/main/src/types/index.ts)
- [Practitioner issue 107: multiple instances of one provider with different model settings](https://github.com/promptfoo/promptfoo/issues/107)

The issue is evidence of the workflow, not adoption evidence for EvalInt. The
correctness defect is independently reproduced by the current producer and the
downloaded EvalInt v0.2.26 entry point.

## Reuse and alternatives considered

Project and package metadata were checked on 2026-08-12.

| Approach | Maintenance, license, dependencies, and platform fit | Cost and migration |
| --- | --- | --- |
| Use Promptfoo's viewer only | Promptfoo 0.122.0 is active and MIT; its npm package requires Node 22.22+ and declares about 80 direct runtime plus 42 optional dependencies | It presents labelled provider columns correctly, but does not perform EvalInt's post-hoc item, reliability, duplicate, and reduction audit. It therefore cannot repair an EvalInt import. |
| Give every configuration a new provider id | Promptfoo documents an id override for custom providers; no EvalInt change | It requires changing existing configs and custom code. Built-in provider ids describe the provider/model, and rerunning an already paid evaluation solely to rewrite identity is unnecessary migration cost. |
| Preprocess with [jq](https://github.com/jqlang/jq) | jq 1.8.2 is maintained and cross-platform under its bundled license; no service account | Every user must maintain and remember the same producer-specific rewrite before every audit. It also creates another transformed artifact whose provenance must be tracked. |
| Add a distinct label to EvalInt's existing composite id | Python standard library; zero new runtime dependencies, service, account, or network path | Selected. It consumes an explicit field already present in Promptfoo JSON and JSONL while leaving hidden provider configuration and secrets out of reports. |

No Promptfoo or jq code is copied. EvalInt reads public artifact fields as data,
so its existing MIT license and zero-dependency runtime remain unchanged.

## Resulting contract and migration

- A current row whose label differs from provider id becomes
  `promptfoo:{"prompt_id":"...","provider":"...","provider_label":"..."}`.
- A missing label, or the common default label equal to provider id, keeps the
  v0.2.26 two-field identity. This avoids changing the common default case.
- Repeated rows with the same provider id, label, and prompt id remain one
  logical system and are averaged as repeats.
- A present null, blank, boolean, or non-string label exits `1` before a report.
  Its value is not echoed.
- Labels and ids are opaque strings encoded as canonical JSON. Control
  characters are escaped, and rendered prompts, responses, provider config,
  endpoints, and credentials are excluded.
- Rows without `promptId` retain legacy provider-only compatibility; provider
  labels do not introduce a new identity scheme into those older envelopes.

Users who persisted v0.2.26 system names for providers with custom labels will
see the new `provider_label` member and should refresh those baselines. This is
an intentional correction: retaining the old name would preserve the observed
false comparison.

## False positives, false negatives, and limits

A label is a producer-declared distinction, not proof of configuration. Two
labels split systems even if their hidden settings are identical, which can be
a false-positive distinction. Two materially different configurations still
collapse if the producer gives them the same provider id and label, which is a
false negative. EvalInt deliberately does not serialize or compare provider
configuration because it can contain API keys, endpoints, headers, proprietary
settings, or unstable values.

Labels can also be renamed between exports without changing configuration, so
cross-file merging requires stable producer labels. A clean audit does not
prove that all configured providers ran, every row was exported, labels are
truthful, configurations are independent, or scores use the intended rubric.
