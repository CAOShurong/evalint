# Multi-file provenance: name the input and every format

Research snapshot: 2026-08-11.

## The failure users hit

EvalInt accepts several result files because many evaluation tools emit one
file per model or run. Public v0.2.8 produced two misleading diagnostics at
that boundary:

- the same CSV and JSONL inputs reported `"format": "jsonl"` in one order and
  `"format": "csv"` in the reverse order even though the ranking was identical;
- a six-line truncated JSONL member exited `1` with its line and column but did
  not name that member, leaving the user to search the whole batch.

This is provenance at a deliberately small scale: an audit result should say
which representation supplied it, and a parse location needs an artifact as
well as a line. W3C PROV describes provenance as information used to assess a
data product's quality, reliability, or trustworthiness. SARIF likewise models
a physical diagnostic location as an artifact location plus a text region.

Practitioners report the same failure mode outside EvalInt. A Docker Compose
issue says a large configuration was difficult to debug because a parser error
named neither the env file nor its line. A Tauri feature request obtained a
JSON line and column, then still asked for the file that produced the error.

Sources:

- [W3C PROV semantics and provenance purpose](https://www.w3.org/TR/prov-sem/)
- [OASIS SARIF artifact locations and text regions](https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/sarif-v2.1.0-os.html)
- [MLflow dataset source and lineage tracking](https://mlflow.org/docs/latest/dataset/)
- [Docker Compose issue 8763: error omitted file and line](https://github.com/docker/compose/issues/8763)
- [Tauri issue 9951: JSON location still omitted the failing file](https://github.com/tauri-apps/tauri/issues/9951)

## Maintained alternatives considered

| Approach | Maintenance, license, dependency and migration cost | Decision |
| --- | --- | --- |
| Require every input to be converted to one format first | No EvalInt dependency, but duplicates files and adds a preprocessing/migration step before an audit | Rejected. The supported readers already compose safely at the matrix boundary. |
| Adopt MLflow dataset tracking | Active, Apache-2.0, source/digest/schema lineage; PyPI 3.15.1 listed 59 requirement entries when checked | Rejected for this boundary. It adds project state and a large dependency surface to a zero-runtime-dependency CLI. |
| Adopt DVC data lineage | Active, Apache-2.0, file and pipeline lineage; PyPI 3.67.1 listed 82 requirement entries when checked | Rejected for this boundary. It is valuable for versioned pipelines but would require repository workflow and storage metadata migration. |
| Add `jsonlines` 4.0.0 | Maintained, BSD-3-Clause, one `attrs` runtime dependency; supplies JSONL line numbers but neither batch filenames nor mixed-format summaries | Not selected. It does not solve the provenance layer owned by the caller. |
| Wrap existing path-based parsers and summarize detected formats | Standard library only, no account, service, storage or migration cost | Selected. It fixes the observed boundary without replacing the maintained format readers. |

Repository and package maintenance metadata were checked through the GitHub
API and public PyPI metadata on the research date. Requirement-entry counts
include conditional and extra requirements and are dependency-weight signals,
not installed-package counts.

## Resulting contract and limits

- `load()` and `load_many()` retain the caller-supplied path when content
  parsing fails. Existing JSON/JSONL line and column detail remains intact.
- String-only `parse_text()` and `load_text()` have no path to report.
- A batch whose files all use one representation keeps that format name.
- A mixed auto-detected batch reports sorted unique formats as
  `mixed:<format>,<format>`, independent of input order.
- EvalInt still merges scores by item and logical system, not by file format.

The compact report `source` remains a display label, not a manifest. EvalInt
does not hash, sign, copy, authenticate, or retain input files, and it cannot
prove that an export is complete or original. Use a data-lineage or artifact
system when those stronger properties are required.
