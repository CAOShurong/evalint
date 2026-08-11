# Missing scores: expose coverage before ranking

Research snapshot: 2026-08-11.

## The failure users hit

EvalInt correctly stored a missing score as absent rather than zero, but its
report hid the resulting comparison problem. In a 3-item by 3-system fixture
with only 7 of 9 cells present, v0.2.3 printed `7 scores` and ranked system
means that were computed over different item subsets. It did not show 7/9
coverage or say those means were not directly comparable.

Incomplete evaluation is a documented practical condition, not just a test
fixture. Research on missing benchmark scores names cost, private systems,
compute limits, and incomplete data as causes. Inspect's maintained eval suite
uses an explicit `Score.unscored()` state for grader-instrument failures,
excludes it from metrics, and records a reason; its metric utilities also have
an explicit `on_missing="skip"` policy.

Sources:

- [Towards More Robust NLP System Evaluation: Handling Missing Scores in Benchmarks](https://arxiv.org/abs/2305.10284)
- [Inspect Evals changelog: unscored failures and explicit missing-score handling](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/CHANGELOG.md)
- [Inspect scoring metrics](https://inspect.aisi.org.uk/metrics.html)

## Alternatives considered

| Approach | Cost and assumptions | Decision |
| --- | --- | --- |
| Treat missing as zero | Zero dependencies, but changes "not measured" into "failed" | Rejected. It systematically penalizes systems with incomplete runs. |
| Average every system over whatever it completed, without a warning | Existing behavior; cheap | Rejected. Different item subsets can have different difficulty, so the ranking can reflect coverage rather than quality. |
| Fail every incomplete audit | Deterministic and zero-dependency | Not selected as the default. Partial runs are useful for diagnosis, and the tool cannot know whether missingness is intentional. |
| Complete-case ranking | Comparable subset, but may discard most data or leave too few items | Not silently selected. A future explicit mode could expose both the retained count and changed ranking. |
| Imputation or partial-ranking aggregation | Research-backed methods exist, but add modeling assumptions and can invent values users mistake for observations | Not selected without an explicit user choice and validation data. |
| Report exact coverage and a comparability warning | Zero dependencies; preserves observed data and existing output while exposing the limitation | Selected for v0.2.4. |

Promptfoo, Inspect AI, and DeepEval remain full evaluation runners rather than
drop-in auditors for arbitrary exported score matrices. Migrating to one can
prevent or label some failures upstream, but it is a much larger change than
making an existing export honest at read time.

## Resulting contract and limits

- Text reports show observed/expected item-by-system cells when coverage is
  incomplete and state that the ranking is not directly comparable.
- JSON summaries always include the unique observation count, expected dense
  count, and coverage fraction.
- Raw repeated measurements remain separate from unique coverage cells.
- No value is imputed, and missing never becomes zero.
- Reliability continues to use only items observed for every system.

The warning is intentionally conservative. It can report that subsets differ,
but not whether the missingness changed the ranking or why a score is absent.
Conversely, complete coverage does not prove that every run was valid or that
all systems received semantically identical inputs. Those require producer
metadata and run-level validation outside EvalInt.
