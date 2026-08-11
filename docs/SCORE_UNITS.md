# Score units: normalize explicitly or stop

Research snapshot: 2026-08-11.

## The failure users hit

EvalInt v0.2.2 accepted arbitrary numeric values and clamped them into
`[0, 1]`. A 0-100 file containing `0`, `50`, and `100` therefore became `0`,
`1`, and `1`. In a real CLI reproduction, the command emitted no units warning
and returned a plausible ranking; its exit status reflected only the corrupted
set's computed reliability. `NaN` silently became zero.

This is not an exotic input. Score conventions differ across maintained eval
systems and real judge prompts:

- Promptfoo's public scoring interface uses normalized 0-1 scores.
- OpenAI score-model graders default to `[0, 1]` but expose an explicit score
  range, so exports need not use that default.
- Inspect casts custom numeric scores directly and lets a task view declare
  explicit numeric bounds; a custom scorer can therefore use 1-10 or another
  scale.
- A DeepEval user reported that GEval's hidden 0-10 internal scale and 0-1
  public scale turned an intended `0.9` into `0.09`. The report documents both
  the practical confusion and the compatibility cost of changing scales.
- Practitioner judge prompts commonly request Likert-style 1-5 or 1-10
  ratings.

Sources:

- [Promptfoo assertions and normalized custom scores](https://www.promptfoo.dev/docs/configuration/expected-outputs/)
- [OpenAI grader API: score range defaults to `[0, 1]`](https://platform.openai.com/docs/api-reference/graders)
- [Inspect scorer API: numeric values are cast directly](https://inspect.aisi.org.uk/reference/inspect_ai.scorer.html)
- [Inspect task views: numeric score bounds can be explicit](https://inspect.aisi.org.uk/task-views.html#score-columns)
- [DeepEval issue 1929: unclear 0-10 to 0-1 normalization](https://github.com/confident-ai/deepeval/issues/1929)

## Maintained alternatives considered

Repository activity, licenses, releases, and package metadata were checked via
the GitHub, PyPI, and npm APIs on 2026-08-11.

| Project or approach | Maintenance, license, and dependency shape | Fit and migration cost |
| --- | --- | --- |
| [Promptfoo 0.122.0](https://github.com/promptfoo/promptfoo) | Active; MIT; about 80 direct npm runtime dependencies | Produces normalized 0-1 assertion scores and runs the eval itself. Useful upstream, but adopting the runner is a much larger migration than auditing existing result files. |
| [Inspect AI 0.3.255](https://github.com/UKGovernmentBEIS/inspect_ai) | Active; MIT; about 40 non-extra Python requirements | Preserves custom numeric values and can display an explicit range. It does not establish the intended scale for arbitrary third-party exports. |
| [DeepEval 4.1.7](https://github.com/confident-ai/deepeval) | Active; Apache-2.0; about 29 non-extra Python requirements | Provides many evaluators and normalizes its own metrics, but the reported scale-confusion issue shows why implicit conversion is unsafe. Migrating requires adopting a full eval framework. |
| Clamp or infer from observed values | No dependency or operating cost | Rejected. Clamping destroys ordering and distances. A heuristic cannot distinguish a valid high pass rate from 0-100 values that saturated at one. |
| Strict unit interval with explicit external conversion | Python standard library; EvalInt remains zero-dependency and offline | Selected. It stops before corrupting statistics and makes the producer's known scale part of the conversion step. |

No extra package can reliably infer the conceptual score scale from numbers
alone, so adding a dependency would increase install and security surface
without resolving the ambiguity.

## Resulting contract

- Finite scores from `0` through `1`, including fractional values: accepted.
- In the versioned native matrix format, score values must be JSON numbers;
  see [the native score-type contract](NATIVE_SCORE_TYPES.md). Generic CSV and
  third-party JSON importers retain their compatibility coercion.
- Booleans and documented pass/fail strings: converted to `0` or `1`.
- Numeric values below `0`, above `1`, `NaN`, and infinity: exit `1` before a
  report is printed.
- A known `[MIN, MAX]` scale can be normalized explicitly with
  `(score - MIN) / (MAX - MIN)` before running EvalInt.
- Arbitrary unparseable text such as `n/a` remains a missing score, not zero.

The boundary prevents silent numeric corruption; it does not prove that an
in-range value used the intended rubric. A 1-5 export containing only `1`
cannot be distinguished from a valid unit score using values alone. EvalInt
therefore reports no heuristic "wrong units" warning for otherwise valid
data. Scale metadata or an explicit producer-side conversion is required to
close that remaining false-negative case.
