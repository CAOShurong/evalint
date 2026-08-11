# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.21] - 2026-08-12

### Fixed

- Require score values in the native `evalint/matrix-v1` format to be JSON
  numbers. Earlier releases silently turned booleans into 1/0 and quoted
  numbers into floats, then used them in ordinary rankings and statistics.
- Return a bounded item-position error for nonnumeric, nonfinite, or
  out-of-range native scores without echoing the rejected value or labels.
  Generic CSV and third-party import compatibility remains unchanged.

### Added

- Document numeric-type evidence, maintained strict-validation alternatives,
  migration cost, and the limits of type and range validation.

## [0.2.20] - 2026-08-12

### Fixed

- Validate native item metadata before constructing an item: `text` and
  `expected` must be strings when present, while `tags` must be an array of
  strings. Earlier releases turned JSON null into the literal text `"None"`,
  which could manufacture duplicate-item findings, and split a string tag into
  character labels.
- Keep omitted metadata compatible with the existing empty string and empty
  tag-list defaults, while returning a bounded exit-`1` import error for a
  present field of the wrong type.

### Added

- Document the reproduced report distortion, maintained validation
  alternatives, migration path, and limits of structural metadata checks.

## [0.2.19] - 2026-08-12

### Fixed

- Require the exact `evalint/matrix-v1` schema marker in the native reader,
  including when the caller passes `--format matrix`. Earlier releases could
  reject an unknown or missing marker during detection, recommend the format
  flag, and then silently interpret the same document as v1 with exit `0`.
- Share one schema constant across native detection, serialization, and
  deserialization so those three boundaries cannot drift independently.

### Added

- Document versioned JSON alternatives, forward-compatibility and migration
  costs, the reproduced format-override contradiction, and the limits of an
  exact marker check.

## [0.2.18] - 2026-08-12

### Fixed

- Validate native `repeats` maps before recording an item: each key must be a
  declared system with a score on that item, and each count must be a positive
  integer-valued JSON number. Earlier releases silently truncated fractional
  counts, coerced quoted counts, and discarded unmatched or typoed counts
  while returning an ordinary report.

### Added

- Document the repeat-count contract, reproduced measurement/run-count errors,
  maintained validation alternatives, migration cost, and the limits of
  structural validation.

## [0.2.17] - 2026-08-12

### Fixed

- Validate identity in the native `evalint/matrix-v1` reader: item and system
  identifiers must be nonblank strings and unique in their arrays, while score
  keys must reference a declared system. Earlier releases could count one
  duplicated system name twice, merge duplicate item objects as hidden repeat
  runs, coerce null ids to `"None"`, or add a typoed score key as a new system.
- Refuse malformed native `systems`, `items`, `scores`, and `repeats`
  containers with bounded import errors instead of relying on incidental Python
  conversions.

### Added

- Document the native matrix contract, zero-dependency validation decision,
  migration cost, and exact-uniqueness false-positive/false-negative limits.

## [0.2.16] - 2026-08-12

### Fixed

- Refuse generic JSON/JSONL and CSV records whose required item or system
  identifier is missing, null, empty, or whitespace-only. Earlier releases
  could silently skip the record, merge null ids under `"None"`, or rank an
  anonymous CSV system while producing an ordinary exit-`0` report.
- Refuse non-object generic JSON records, blank item ids in wide CSV, and
  scored wide columns with blank system headers instead of discarding them
  from a plausible subset.

### Added

- Report bounded JSONL line, JSON-array record, and CSV logical-row locations
  without echoing the rejected row, and document validation alternatives plus
  false-positive and false-negative limits.

## [0.2.15] - 2026-08-12

### Fixed

- Refuse plain `--save-reduced` output when a kept item id contains a line
  boundary. Earlier releases silently split one logical id across physical
  lines; a reproduced report kept 3 ids while its output contained 6 lines.
- Validate the complete plain serialization before creating a temporary file,
  so a refused write preserves an existing destination.

### Added

- Add `--save-reduced-format jsonl` for lossless one-record-per-line export of
  arbitrary string ids, including embedded newlines, NUL, quotes, and Unicode.
- Document delimiter alternatives, dependency and migration costs, conservative
  Unicode line-boundary handling, and downstream parsing limits.

## [0.2.14] - 2026-08-11

### Fixed

- Render imported system names, item ids, path labels, warnings, and error
  details as inert single-line text before writing a human-readable terminal
  report. Control characters such as ANSI clear-screen, cursor-positioning,
  hyperlink, newline, and bidirectional overrides are now shown as visible
  escape spellings instead of being interpreted by the terminal.
- Preserve EvalInt's own trusted colour sequences while escaping only data
  labels. `--color never` emits no ESC bytes, and `--ascii` also escapes
  non-ASCII labels.
- Keep machine-readable JSON lossless: imported labels remain unchanged in
  structured output rather than being silently rewritten in the data model.

### Added

- Document the terminal-output trust boundary, the reproduced v0.2.13
  behavior, rejected dependency and blanket-stripping alternatives, and the
  distinction between safe display text and unchanged JSON data.

## [0.2.13] - 2026-08-11

### Fixed

- Refuse exact duplicate CSV header names before `DictReader` turns a row into
  a dictionary. Earlier releases silently kept the last same-named column; two
  reproduced `score` columns with opposite values reversed the ranking while
  the CLI exited `0` with an ordinary report.
- Apply the same check to long and wide CSV so repeated model columns cannot
  discard earlier scores either.

### Added

- Document the header-identity contract, maintained schema-validation
  alternatives, and case/alias collisions that this exact check does not infer.

## [0.2.12] - 2026-08-11

### Fixed

- Auto-detect valid CSV files whose quoted prompt or answer fields contain the
  delimiter, doubled quotes, or embedded newlines. Earlier releases counted
  separators on physical lines and rejected these standard records as unknown
  even though `--format csv` could parse them.
- Refuse unterminated quoted CSV fields with a bounded line-numbered import
  error, including when CSV is forced, instead of accepting a partial record.
- Refuse rows with more fields than the header instead of ignoring their
  overflow or exposing an internal error.

### Added

- Document CSV dialect alternatives, detection limits, and why automatic
  recognition is not proof that an export is complete or semantically valid.

## [0.2.11] - 2026-08-11

### Fixed

- Refuse to count one physical result file more than once when it is passed
  through repeated path spellings, symbolic links, or hard links. Earlier
  releases silently doubled its run and measurement counts while emitting a
  plausible report.
- Keep byte-identical but physically independent files valid because they can
  represent legitimate repeated stochastic runs.

### Added

- Document duplicate-input alternatives, filesystem-identity limits, and why
  a successful alias check is not content or provenance deduplication.

## [0.2.10] - 2026-08-11

### Fixed

- Refuse to merge the same item id when nonempty prompt text or expected
  answers conflict. Earlier releases silently attached scores for different
  eval cases to one first-seen item and could emit a plausible clean report.
- Name both the first and conflicting input files for cross-file identity
  drift without echoing the prompt or answer contents.
- Treat an item-id display fallback as missing text so a later source with
  real prompt text can still enrich the item instead of being ignored.

### Added

- Export `ConflictingItem` for callers that build `Matrix` objects directly.
- Document the item-identity boundary, maintained validation/versioning
  alternatives, and the drift that id-only exports cannot reveal.

## [0.2.9] - 2026-08-11

### Fixed

- Name the failing input path when a path-based import contains malformed or
  unsupported content, while retaining the existing line and column detail.
  Earlier multi-file runs said where inside a file parsing failed but not
  which member of the batch was responsible.
- Report mixed auto-detected inputs with a deterministic format summary such
  as `mixed:csv,jsonl`. Earlier releases returned only the last file's format,
  so reversing identical inputs changed the report metadata.

### Added

- Document the multi-file provenance boundary, maintained lineage
  alternatives, and why a format/path label is not an integrity proof.

## [0.2.8] - 2026-08-11

### Fixed

- Report malformed JSONL with its record line and column, exit `1`, and emit
  no traceback. Earlier releases sampled five lines during detection, then
  leaked a Python traceback when a later record was truncated or corrupt.
- Stop silently skipping malformed OpenAI Evals event lines.
- Convert malformed forced-format Promptfoo JSON into the same bounded import
  error instead of leaking `JSONDecodeError`.

### Added

- Document JSON/JSONL syntax handling, maintained parser alternatives, and why
  EvalInt refuses to skip or auto-repair corrupt score records.

## [0.2.7] - 2026-08-11

### Fixed

- Preserve explicitly named systems in long-form CSV/JSONL, Promptfoo, OpenAI
  Evals, matrix, and merged inputs even when a system has no usable scores.
  Earlier releases could drop that system and report 100% coverage for the
  remaining systems.
- Exit `1` with the unscored system name instead of either hiding the system or
  ranking a wholly unmeasured system as zero.

### Added

- Add a public `Matrix.add_system()` builder method so importers can preserve
  the difference between a named-but-unmeasured system and no system record.

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
[0.2.6]: https://github.com/CAOShurong/evalint/compare/v0.2.5...v0.2.6
[0.2.7]: https://github.com/CAOShurong/evalint/compare/v0.2.6...v0.2.7
[0.2.8]: https://github.com/CAOShurong/evalint/compare/v0.2.7...v0.2.8
[0.2.9]: https://github.com/CAOShurong/evalint/compare/v0.2.8...v0.2.9
[0.2.10]: https://github.com/CAOShurong/evalint/compare/v0.2.9...v0.2.10
[0.2.11]: https://github.com/CAOShurong/evalint/compare/v0.2.10...v0.2.11
[0.2.12]: https://github.com/CAOShurong/evalint/compare/v0.2.11...v0.2.12
[0.2.13]: https://github.com/CAOShurong/evalint/compare/v0.2.12...v0.2.13
[0.2.14]: https://github.com/CAOShurong/evalint/compare/v0.2.13...v0.2.14
[0.2.15]: https://github.com/CAOShurong/evalint/compare/v0.2.14...v0.2.15
[0.2.16]: https://github.com/CAOShurong/evalint/compare/v0.2.15...v0.2.16
[0.2.17]: https://github.com/CAOShurong/evalint/compare/v0.2.16...v0.2.17
[0.2.18]: https://github.com/CAOShurong/evalint/compare/v0.2.17...v0.2.18
[0.2.19]: https://github.com/CAOShurong/evalint/compare/v0.2.18...v0.2.19
