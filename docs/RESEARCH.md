# Research: repeat runs without pseudoreplication

Research snapshot: 2026-08-11.

## The user problem

LLM evaluation is nondeterministic, so practitioners deliberately run the same
test more than once. A Promptfoo user described the concrete failure mode as a
test that passes on one run and fails on another, making the result hard to
trust; Promptfoo now exposes both global and per-test repeat controls. Inspect
AI likewise models repeated samples as epochs and defaults to reducing their
scores with a mean. A NAACL 2025 paper found that ignoring nondeterminism hides
meaningful evaluation variability.

Sources:

- [Promptfoo issue #1888: unstable tests need repeated runs](https://github.com/promptfoo/promptfoo/issues/1888)
- [Promptfoo test-case documentation: `options.repeat`](https://www.promptfoo.dev/docs/configuration/test-cases/#repeating-an-individual-test)
- [Inspect AI `Epochs`: repeated samples are reduced, by default with a mean](https://inspect.aisi.org.uk/reference/inspect_ai.html#epochs)
- [Song et al., NAACL 2025: Evaluation of LLMs Should Not Ignore Non-Determinism](https://aclanthology.org/2025.naacl-long.211/)

The statistical constraint is equally important: repeated observations of one
experimental unit are not new independent units. SciPy's permutation-test
documentation distinguishes independent observations from paired observations
and pairings because the valid permutations depend on that structure. The
classic definition of pseudoreplication is using inferential statistics where
replicates are not statistically independent.

- [SciPy permutation-test assumptions](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html)
- [Hurlbert 1984, Pseudoreplication and the Design of Ecological Field Experiments](https://doi.org/10.2307/1942661)

## What v0.1.0 did wrong

When the same `(item, system)` cells appeared in several files, EvalInt v0.1.0
prefixed each system with the file name and treated every run as an independent
system. Within one file, a repeated cell silently used the last score. Eight
runs each of two models could therefore appear as sixteen systems, giving the
item-level permutation test far more apparent evidence than the two logical
systems actually provide.

This is falsifiable with four files: two runs each for `alpha` and `beta`.
v0.1.0 reports four systems. The corrected behavior reports two systems, four
runs and the raw measurement count, with each item score averaged within its
named system. Repeating only `alpha` remains one logical system and is refused
as incomparable.

## Maintained alternatives and why composition wins

Repository activity, licenses, releases and dependency manifests were checked
through the GitHub API and the projects' primary documentation on 2026-08-11.
Published-advisory counts were also checked, but absence of a published advisory
is not evidence that a project is secure.

| Project | Maintenance and license | Dependency / cost shape | Fit and migration cost |
| --- | --- | --- | --- |
| [Promptfoo](https://github.com/promptfoo/promptfoo) | Active; MIT; v0.122.0 | Node application with about 80 direct runtime dependencies and many optional integrations; running repeats can incur provider cost | Excellent runner and repeat producer, but not a zero-dependency post-hoc psychometric audit. EvalInt should ingest its output rather than replace it. |
| [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) | Active; MIT | About 40 direct runtime requirements; epochs can multiply model calls | Correctly reduces epochs and provides a full evaluation framework. Adopting it requires moving the evaluation workflow, while EvalInt is intended to read existing exports. |
| [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) | Active; MIT; v0.4.12 | At least 14 core Python dependencies plus backend/task extras and model execution cost | Broad benchmark runner, not an item-quality linter for arbitrary score matrices. |
| [cleanlab](https://github.com/cleanlab/cleanlab) | Maintained; Apache-2.0; v2.9.0 | Five direct scientific-stack dependencies, including NumPy, pandas and scikit-learn | Finds label and data-quality problems in ML datasets, but does not preserve EvalInt's score-matrix workflow or zero-dependency install. |

The smallest compatible solution is therefore to adopt the established reducer
semantics inside EvalInt: keep the logical system name, average repeated cells,
and retain counts. Adding a runner or scientific stack would add installation,
operating and migration cost without fixing the import boundary more directly.

## Limits after the fix

- Grouping uses the exact source `system` name. Aliases such as `gpt4` and
  `gpt-4` remain distinct until the producer normalizes them.
- Averaging prevents false independence but does not estimate within-system
  confidence intervals or model stochasticity. EvalInt still audits the set,
  not the generation process.
- Duplicate rows might be accidental. EvalInt reports their measurement and
  run counts, but cannot infer whether the producer intended the repetition.
- Uneven or missing repeats are averaged from the measurements that exist; a
  missing score is still not treated as zero.
- A small p-value flags an item for human review. It does not prove that an
  answer key is wrong, and a clean report does not prove that an eval is valid.
