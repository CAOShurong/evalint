# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
