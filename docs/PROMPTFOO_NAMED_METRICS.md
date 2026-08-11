# Promptfoo named metrics: audit one dimension, not only the average

Research snapshot: 2026-08-12.

## The reproduced gap

Promptfoo assertions may carry a `metric` name. Current result rows expose the
per-metric values in `namedScores`, while their top-level `score` is the
weighted aggregate of all assertions. Aggregation is useful for one headline,
but opposite strengths can cancel and make every item look inert.

A real `npx promptfoo@0.122.0 eval` fixture used two local providers, two test
cases, and `Accuracy` plus `Safety` assertions. The accuracy provider emitted
per-row named scores `{"Accuracy":1,"Safety":0}`; the safety provider emitted
the reverse. Every top-level score was `0.5`. No model API, account, share, or
cloud service was used.

Public EvalInt v0.2.29 exited `0` but could read only the aggregate. It reported
two tied systems at `0.5`, zero informative items out of two, and a reduction
that dropped both items. Auditing `Accuracy` should instead expose means 1 and
0; auditing `Safety` should reverse them. The fixture is deliberately synthetic
and is not evidence of users, adoption, or performance.

Evidence:

- [Promptfoo assertions and metrics: weighted top-level scores, named metrics,
  custom scoring, and derived metrics](https://www.promptfoo.dev/docs/configuration/expected-outputs/)
- [Promptfoo output formats: top-level scores are aggregate while component
  results retain assertion detail](https://www.promptfoo.dev/docs/configuration/outputs/)
- [Promptfoo issue 9354: named-metric denominators can disagree between filtered
  and canonical aggregation](https://github.com/promptfoo/promptfoo/issues/9354)
- [Promptfoo issue 9887: a practitioner describes fragile external
  post-processing for precision, recall, and F1](https://github.com/promptfoo/promptfoo/issues/9887)
- [Promptfoo issue 1626: exported named scores were not visible as expected in
  the UI](https://github.com/promptfoo/promptfoo/issues/1626)
- [Promptfoo issue 4386: a second reproducible request to surface named scores
  from a Python assertion](https://github.com/promptfoo/promptfoo/issues/4386)

## Reuse and alternatives considered

Repository and package metadata were checked on 2026-08-12.

| Approach | Maintenance, license, dependencies, security and platform fit | Operating and migration cost |
| --- | --- | --- |
| Use Promptfoo's viewer and metric filters | Promptfoo 0.122.0 is active and MIT. Its Node package requires Node 22.22+ and declares about 80 direct runtime plus 42 optional dependencies. The viewer can filter metrics but is a larger browser-facing execution surface. | Best for inspecting the upstream run, but it does not provide EvalInt's reliability, discrimination, duplicate, and reduction audit. A user must change analysis tools rather than reuse the exported artifact in an existing CLI/CI workflow. |
| Export CSV and inspect metric columns in a spreadsheet | Promptfoo and desktop spreadsheets are maintained cross-platform options, but CSV expands the artifact and spreadsheet import/formula behavior adds another parsing and execution surface. | Requires a second export or conversion plus one manual analysis per metric. It does not reproduce EvalInt's audit, and rerunning a provider-backed eval can cost time and money. |
| Project `namedScores` with [jq](https://github.com/jqlang/jq) or a custom script | jq is maintained, cross-platform native software under the jq license; Python's standard library is already available to EvalInt users. Either can select a key, but the user-owned script must preserve item/system/error semantics and avoid leaking other fields. | Adds a conversion artifact and mapping policy to maintain across Promptfoo schema changes. A wrong filter can silently omit rows or convert absence to zero before EvalInt sees it. |
| Add an exact named-metric selector to the existing Promptfoo reader | Reuses the current zero-runtime-dependency Python parser and Promptfoo's public artifact shape. It adds no account, network call, copied upstream code, or service lock-in. | Selected. Default aggregate behavior is unchanged; users opt in with one flag and can audit the existing JSON or JSONL file offline. |

## Resulting contract

`evalint results.jsonl --promptfoo-metric Accuracy` selects the exact,
case-sensitive `Accuracy` key from each current Promptfoo row:

- the selected numeric value replaces that row's top-level aggregate score;
- a row without the key remains an expected but missing measurement, lowering
  reported coverage instead of becoming zero;
- if no row contains the key, the command exits `1` with empty report stdout
  and does not list other metric names;
- malformed `namedScores` or a selected boolean/string/object value fails with
  a bounded diagnostic that does not echo the value;
- selected values still pass EvalInt's finite `[0, 1]` score validation;
- `failureReason=2` provider, grader, or runtime errors remain missing even if
  the errored row happens to contain the key;
- selecting a metric for CSV, native matrix, generic JSONL, or OpenAI Evals
  input is refused rather than silently ignored.

The Python `load`, `load_many`, `parse_text`, and `load_text` APIs expose the
same opt-in behavior through the keyword-only `promptfoo_metric="Accuracy"`
argument.

The text report includes the requested metric in its escaped source label. JSON
adds `"promptfoo_metric":"Accuracy"`. Imported assertion bodies, reasons,
weights, available metric names, rendered prompts, outputs, provider errors,
and provider configuration are not enumerated.

## Limits and falsifiable boundaries

EvalInt consumes each exported per-row named score; it does not reconstruct
assertion weights, `namedScoreWeights`, derived metrics, or Promptfoo's prompt-
level denominator. Promptfoo issue 9354 documents that upstream filtered and
canonical denominators can diverge for some legacy/imported rows. Selecting a
metric does not repair that producer-side discrepancy.

The same metric name can mean different things across tests, providers, files,
or versions. Different names can also describe the same construct. Missing
keys are treated as missing observations even though Promptfoo's derived-metric
machinery may use zero defaults in a different aggregation context. This choice
avoids inventing an observed failure, but it can produce a false negative if
the producer intended omission to mean zero. Conversely, an incorrectly
emitted zero remains an observed zero.

Only normalized finite scores in `[0, 1]` fit EvalInt's current statistical
contract. Counts, costs, latencies, token totals, and unbounded derived values
must not be passed as named quality scores. A clean audit proves only how the
supplied selected values behave as a matrix. It does not prove completeness,
metric validity, stable meaning, correct weighting, provider execution,
independence, or generalization.
