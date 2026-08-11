# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.6] - 2026-08-11

### Fixed

- Preserve identifiable CSV, JSONL, Promptfoo, and OpenAI Evals items even
  when every score for an item is blank or unparseable. Earlier releases
  removed those items from both the item count and the coverage denominator,
  so a 3-item fixture with 3 of 6 valid cells reported 2 items and 75%
  coverage instead of 3 items and 50% coverage.
- Keep unparseable values missing rather than guessing that they are failures;
  the item now remains visible so the existing sparse-coverage warning can do
  its job.

### Added

- Document the scoreless-item import boundary, maintained alternatives, and
  the identifiers that cannot be recovered from malformed rows.

## [0.2.5] - 2026-08-11

### Fixed

- Refuse `--save-reduced` paths that refer to an input, including hard-link
  aliases, instead of overwriting the original eval results with item ids.
- Report output-directory, permission, and replacement failures as exit `1`
  without a traceback.
- Write reduced-set outputs through a flushed sibling temporary file and
  replace the destination only after the complete contents exist, preserving
  an existing output when the write or replacement fails.

### Added

- Document the output safety boundary, alternatives, and filesystem limits.

## [0.2.4] - 2026-08-11

### Fixed

- Make incomplete item-by-system coverage visible instead of printing a
  ranking whose system means silently use different item subsets. Text reports
  now show the observed/expected cells and a comparability warning.

### Added

- Add `observations`, `expected_observations`, and `coverage` to the JSON
  summary, plus documentation of missing-score alternatives and limitations.

## [0.2.3] - 2026-08-11

### Fixed

- Refuse numeric scores outside `[0, 1]`, `NaN`, and infinity before any
  statistics run. Earlier releases silently clamped those values and could
  turn 1-5 or 0-100 rubric scores into a plausible but corrupted audit.
- Stop guessing that a valid high pass rate means the source used the wrong
  score units. Binary eval sets can legitimately contain nearly all ones.

### Added

- Document the explicit score-unit boundary, maintained alternatives,
  normalization formula, and cases the tool cannot infer from values alone.

## [0.2.2] - 2026-08-11

### Fixed

- Accept the optional UTF-8 byte order mark emitted for Excel interoperability
  instead of losing the first CSV header and reporting that the file has no
  eval items.
- Refuse invalid UTF-8 with an actionable import error instead of silently
  replacing bytes inside item or system identifiers. Silent replacement could
  merge distinct records and produce a plausible but corrupted audit.

### Added

- Document the encoding boundary, maintained detection alternatives, and why
  strict UTF-8 is safer for identifiers than heuristic charset guessing.

## [0.2.1] - 2026-08-11

### Fixed

- Ship the [`py.typed`](https://peps.python.org/pep-0561/) marker required for
  type checkers to consume EvalInt's inline annotations. This makes the
  existing `Typing :: Typed` package classifier true for installed wheels
  instead of letting tools such as mypy reduce the public API to `Any`.
- Assert the marker's presence in both CI and release wheel builds so a future
  packaging change cannot silently remove it.

## [0.2.0] - 2026-08-11

### Fixed

- Repeated scores for the same item and logical system are averaged instead of
  using last-write-wins or inventing a new independent system from each file.
  This prevents repeated stochastic runs from making reliability and
  permutation evidence look stronger through pseudoreplication.
- Inputs containing repeat runs of only one logical system are now refused:
  repeats improve that system's estimate, but do not create a comparison.
- Invalid repeat counts in matrix JSON now return a normal import error instead
  of leaking an internal exception traceback.

### Added

- Text and JSON reports distinguish logical systems, represented runs, and raw
  score measurements. Matrix JSON preserves per-cell repeat counts.
- Research and security-boundary documentation for the repeat-run decision.

## [0.1.0] - 2026-08-03

First release.

### Added

- **Measurement.** KR-20 / Cronbach's alpha over the eval set, the standard
  error of measurement derived from it, and a plain-language verdict. Systems
  closer together than the standard error are reported as tied rather than
  ranked.
- **Item analysis.** Difficulty, variance and corrected item-total
  correlation for every item, so items that cannot affect the ranking are
  separated from items that can.
- **Broken-item detection.** Items whose weaker systems pass them more often
  than the stronger ones, confirmed by a seeded permutation test. Items that
  look inverted but cannot clear the test are reported separately as
  unproven, with the number of systems that would be needed to settle it.
- **Near-duplicate detection.** Character shingles, MinHash and banded LSH,
  with an exact Jaccard check on every candidate pair. No embedding model, no
  API key, no dependencies.
- **Set reduction.** Three layers -- provably inert, redundant, low
  information -- each verified by recomputing the ranking on what would be
  left, and rolled back with a note if the ranking moves.
- **Importers** for long and wide CSV, JSONL records, promptfoo output,
  OpenAI evals logs, and evalint's own matrix JSON. Detection is by file
  shape, not by extension.
- **Multiple input files**, merged on the item id. Required for formats that
  log one run per file, and convenient for anyone exporting one CSV per
  model. The same system name in two files is treated as two runs when the
  cells collide and as one run split across files when they do not.
- **CLI** with `--json`, `--fail-under` for CI gating, `--save-reduced`,
  `--similarity`, `--no-duplicates`, `--no-reduce`, `--color` and `--ascii`.
  Exit `2` means the eval set has a problem; exit `1` means the audit failed.

[0.1.0]: https://github.com/CAOShurong/evalint/releases/tag/v0.1.0
[0.2.0]: https://github.com/CAOShurong/evalint/compare/v0.1.0...v0.2.0
[0.2.1]: https://github.com/CAOShurong/evalint/compare/v0.2.0...v0.2.1
[0.2.2]: https://github.com/CAOShurong/evalint/compare/v0.2.1...v0.2.2
[0.2.3]: https://github.com/CAOShurong/evalint/compare/v0.2.2...v0.2.3
[0.2.4]: https://github.com/CAOShurong/evalint/compare/v0.2.3...v0.2.4
[0.2.5]: https://github.com/CAOShurong/evalint/compare/v0.2.4...v0.2.5
