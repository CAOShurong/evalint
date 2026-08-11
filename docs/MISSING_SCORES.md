# Missing scores: expose coverage before ranking

Research snapshot: 2026-08-11.

## The failure users hit

EvalInt correctly stored a missing score as absent rather than zero, but its
report hid the resulting comparison problem. In a 3-item by 3-system fixture
with only 7 of 9 cells present, v0.2.3 printed `7 scores` and ranked system
means that were computed over different item subsets. It did not show 7/9
coverage or say those means were not directly comparable.

There was a second false-negative in v0.2.4 and v0.2.5. Importers skipped a
record before registering its item when the score was blank or unparseable.
If every system lacked a usable score for one item, the item vanished from the
denominator too. A public v0.2.5 CLI reproduction read a 3-item, 2-system CSV
with 3 valid score cells but reported 2 items, 3/4 coverage (75%), and exit
`0`; the faithful denominator is 3 items and 3/6 coverage (50%).

v0.2.6 still had the mirror-image failure for a whole system. A public CLI
reproduction supplied three explicitly named systems across two items, with
valid scores for `alpha` and `gamma` but only `n/a` for `beta`. The command
exited `0`, reported two systems and 4/4 coverage (100%), and ranked only
`alpha` and `gamma`; the named but wholly unmeasured `beta` disappeared.

Incomplete evaluation is a documented practical condition, not just a test
fixture. Research on missing benchmark scores names cost, private systems,
compute limits, and incomplete data as causes. Inspect AI's maintainers and
users have separately reproduced headline metrics that silently exclude
errored or unscored samples: one open report shows 1 success and 9 errors
appearing as accuracy 1.0, while another asks for scored/errored/unscored counts
beside every headline metric. Promptfoo's maintained export documentation says
error rows may lack grading details and deliberately keeps one JUnit test case
per eval result so provider/runtime errors remain distinguishable from failed
assertions. A practitioner report prompted Promptfoo to restore suppressed
grading information after an external assertion raised.

Sources:

- [Towards More Robust NLP System Evaluation: Handling Missing Scores in Benchmarks](https://arxiv.org/abs/2305.10284)
- [Inspect AI issue 4286: metrics silently drop errored and unscored samples](https://github.com/UKGovernmentBEIS/inspect_ai/issues/4286)
- [Inspect AI issue 4481: surface scored, errored, and unscored coverage](https://github.com/UKGovernmentBEIS/inspect_ai/issues/4481)
- [Promptfoo output formats and error-row contract](https://www.promptfoo.dev/docs/configuration/outputs/)
- [Promptfoo issue 827: an assertion error suppressed grading results](https://github.com/promptfoo/promptfoo/issues/827)

## Alternatives considered

| Approach | Cost and assumptions | Decision |
| --- | --- | --- |
| Treat missing as zero | Zero dependencies, but changes "not measured" into "failed" | Rejected. It systematically penalizes systems with incomplete runs. |
| Average every system over whatever it completed, without a warning | Existing behavior; cheap | Rejected. Different item subsets can have different difficulty, so the ranking can reflect coverage rather than quality. |
| Fail every incomplete audit | Deterministic and zero-dependency | Not selected as the default. Partial runs are useful for diagnosis, and the tool cannot know whether missingness is intentional. |
| Complete-case ranking | Comparable subset, but may discard most data or leave too few items | Not silently selected. A future explicit mode could expose both the retained count and changed ranking. |
| Imputation or partial-ranking aggregation | Research-backed methods exist, but add modeling assumptions and can invent values users mistake for observations | Not selected without an explicit user choice and validation data. |
| Report exact coverage and a comparability warning | Zero dependencies; preserves observed data and existing output while exposing the limitation | Selected for v0.2.4. |
| Drop an item when its last score is skipped | Existing v0.2.5 behavior; cheap, but shrinks both numerator and denominator and can make coverage look healthier | Rejected. Absence of every measurement is still evidence that the item was expected. |
| Retain a recognizable item before parsing its score | Python standard library; no new dependency, account, or operating cost | Selected for v0.2.6 across long-form records, Promptfoo, and OpenAI Evals. Wide CSV already registered rows before scores. |
| Drop a named system when all its scores are missing | Existing v0.2.6 behavior; allows the remaining subset to look complete | Rejected. The file explicitly says that comparison target was expected. |
| Rank an unmeasured system as zero | Produces a total order, but changes "not measured" into "failed" | Rejected for the same reason missing cells are never zero. |
| Keep the name and refuse the audit | Zero dependencies; prevents a plausible subset ranking and identifies the producer boundary to fix | Selected for v0.2.7. Partial systems with at least one valid score still use the coverage warning. |

Promptfoo 0.122.0 and Inspect AI 0.3.255 were active, MIT-licensed projects when
checked on 2026-08-11. They preserve richer producer-side error state, but they
remain full evaluation runners rather than drop-in auditors for arbitrary
exported score matrices. Promptfoo currently declares 80 direct npm runtime
dependencies, while Inspect's PyPI metadata declares a broad Python dependency
surface including extras. Migrating an existing evaluation pipeline to either
is a much larger change than retaining an already-identifiable item at import.
EvalInt's selected fix adds no runtime dependency.

## Resulting contract and limits

- Text reports show observed/expected item-by-system cells when coverage is
  incomplete and state that the ranking is not directly comparable.
- JSON summaries always include the unique observation count, expected dense
  count, and coverage fraction.
- CSV/JSONL records, Promptfoo results, and OpenAI Evals events register a
  recognizable item before deciding whether its score is usable. A wholly
  unscored item therefore stays in the item and coverage counts.
- Importers also register explicit system/provider/run names before parsing a
  score. If any such system has zero usable scores across the merged input,
  the audit exits `1` with its name and no report.
- Raw repeated measurements remain separate from unique coverage cells.
- No value is imputed, and missing never becomes zero.
- Reliability continues to use only items observed for every system.

The warning is intentionally conservative. It can report that subsets differ,
but not whether the missingness changed the ranking or why a score is absent.
An item without a recognizable id cannot be recovered. A system that never has
one valid score is refused rather than ranked. In wide CSV, a column containing
no parseable score may be indistinguishable from a non-score metadata column;
that ambiguous shape remains a documented false-negative limit unless the
producer uses long form or an explicit supported format.
Conversely, complete coverage does not prove that every run was valid or that
all systems received semantically identical inputs. Those require producer
metadata and run-level validation outside EvalInt.
