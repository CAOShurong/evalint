# Promptfoo errors are missing measurements, not zero scores

Research snapshot: 2026-08-12.

## The false ranking

Promptfoo's current result contract distinguishes three outcomes with
`failureReason`: `0` for no identified failure, `1` for an assertion failure,
and `2` for another error. Provider, grader, and runtime errors can still carry
the synthetic numeric `score: 0` used by the runner's own result accounting.

A real `npx promptfoo@0.122.0 eval` fixture used one local JavaScript provider
under `pass-config` and `error-config` labels, two prompt versions, and two test
cases. The pass configuration returned the expected answer. The error
configuration threw a local sentinel exception. Promptfoo reported four passes
and four errors, exited `1`, and wrote eight JSONL rows. All four error rows had
`failureReason: 2`, `success: false`, and `score: 0`; the pass rows had reason
`0` and score `1`. No model API or cloud share was used.

Public EvalInt v0.2.27 returned exit `0`, 100% coverage, four systems, eight
observations, reliability `1.0`, and means `1.0/1.0/0.0/0.0`. It therefore
ranked two configurations whose providers never returned an answer. The error
text itself was not leaked, but the zeroes still changed the statistics.

Sources:

- [Current Promptfoo result type and `ResultFailureReason` definitions](https://github.com/promptfoo/promptfoo/blob/main/src/types/index.ts)
- [Promptfoo output formats: errors remain distinct result cases](https://www.promptfoo.dev/docs/configuration/outputs/)
- [Promptfoo test-case docs: assertions and repeats are separate concepts](https://www.promptfoo.dev/docs/configuration/test-cases/)
- [Practitioner issue 827: assertion exceptions suppressed grading results](https://github.com/promptfoo/promptfoo/issues/827)
- [Practitioner issue 4111: grader failures leave null or errored grading results](https://github.com/promptfoo/promptfoo/issues/4111)
- [Inspect AI issue 4286: headline metrics can hide errored and unscored samples](https://github.com/UKGovernmentBEIS/inspect_ai/issues/4286)
- [Inspect AI issue 4481: request to expose scored, errored, and unscored counts](https://github.com/UKGovernmentBEIS/inspect_ai/issues/4481)

The reports establish a recurring need to keep evaluation errors visible; they
are not adoption evidence for EvalInt. The specific false ranking is
independently reproduced with the current Promptfoo CLI and public EvalInt
artifact.

## Reuse and alternatives considered

Project and package metadata were checked on 2026-08-12.

| Approach | Maintenance, license, dependencies, and platform fit | Cost and migration |
| --- | --- | --- |
| Re-run or inspect only in Promptfoo | Promptfoo 0.122.0 is active and MIT; its npm package requires Node 22.22+ and declares about 80 direct runtime plus 42 optional dependencies | This is the right place to diagnose and retry the provider, but it does not repair a post-hoc EvalInt audit of an artifact that already exists. A retry can repeat paid calls. |
| Trust every numeric zero | Existing behavior and no new code | Rejected. It changes “no answer was measured” into “the answer was wrong,” creating false coverage and a false ranking. |
| Treat every row with `error` text as missing | Simple and zero-dependency | Rejected. Promptfoo also uses `error` text for ordinary assertion failures, which are valid observed scores. |
| Infer errors from a missing `gradingResult` | Simple but indirect | Rejected. Grading details can be absent for projections or producer versions, while the current result already carries an explicit reason enum. |
| Preprocess with [jq](https://github.com/jqlang/jq) | jq 1.8.2 is maintained and cross-platform under its bundled license | Every user must maintain and remember the same producer-specific filter, creating another transformed artifact and provenance step. |
| Honor `failureReason=2` in the existing importer | Python standard library; zero runtime dependencies, services, accounts, or network paths | Selected. It reuses the producer's explicit distinction and the Matrix's existing missing-coverage contract. |

No Promptfoo, Inspect, or jq code is copied. EvalInt reads the public result
marker as data, so its MIT license and zero-dependency runtime remain unchanged.

## Resulting contract

- `failureReason=0` and `failureReason=1` continue to use the row's score.
  An assertion failure is an observed zero, not missing data.
- `failureReason=2` registers the recognizable item and system but skips its
  score, regardless of the synthetic numeric value in the row.
- A wholly errored system has no usable scores and exits `1` before any report.
  A partly errored system remains auditable with exact observed/expected counts
  and the existing incomplete-coverage warning.
- A present reason must be a JSON integer `0`, `1`, or `2`. Null, booleans,
  strings, floats, and out-of-range integers fail before a report; the value is
  not echoed.
- Older results without `failureReason` retain their existing score handling.
- Error messages, stack traces, responses, prompts, and provider configuration
  are not copied into the report or diagnostic.

Against the actual eight-row fixture, the changed CLI exits `1` with empty
stdout because the two error-labelled prompt systems have no usable scores. It
names the affected canonical systems but does not echo the private provider
error or print a Python traceback.

## False positives, false negatives, and limits

This boundary trusts Promptfoo's reason marker. A producer that omits it or
marks an infrastructure error as an assertion failure can still create a false
zero. Conversely, a producer that incorrectly marks a real graded zero as
reason `2` creates missing coverage. Some teams intentionally penalize runtime
errors as zero for operational objectives; that is a policy transformation and
should be applied explicitly before EvalInt rather than silently overriding its
“missing is not zero” statistical contract.

Skipping the score does not prove why the error happened, whether a retry would
succeed, or whether the successful rows are trustworthy. A clean audit does
not prove that every configured provider ran, every grader completed, all rows
were exported, or missingness left the ranking unchanged.
