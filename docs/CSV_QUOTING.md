# CSV quoting: detect records, not physical lines

Research snapshot: 2026-08-11.

## The failure users hit

CSV commonly carries prompts and expected answers, so commas, quote characters,
and line breaks are ordinary field content. RFC 4180 and Python's CSV API allow
those characters inside double-quoted fields. Python also distinguishes a
logical record from a physical line because one record may span several lines.

Public EvalInt v0.2.11 nevertheless detected CSV by counting raw delimiter
characters on each physical line. Two reproduced, standards-shaped files used
quoted prompts containing either commas or embedded newlines. Auto mode called
both `unknown` and exited `1`; forcing `--format csv` parsed both successfully
as 2 items and 2 systems. The parser already understood the data, while the
earlier preflight rejected it.

Practitioners report the same boundary in production tools. A current Azure
Data Factory discussion describes quoted commas working until a field also
contains a newline. A DuckDB issue shows dialect sniffing changing with escaped
commas and quotes. These are not rare punctuation choices for LLM prompts.

Sources:

- [RFC 4180 CSV fields, quotes, and line breaks](https://www.rfc-editor.org/rfc/rfc4180)
- [Python `csv` reader, dialect, quoting, and logical line behavior](https://docs.python.org/3/library/csv.html)
- [DuckDB issue 14304: escaped commas and quotes confuse sniffing](https://github.com/duckdb/duckdb/issues/14304)
- [Practitioner discussion: quoted commas plus newlines in a CSV pipeline](https://www.reddit.com/r/dataengineering/comments/1hzt7de/adf_handling_of_csv_files_with_commas_in_data/)

## Maintained alternatives considered

| Approach | Maintenance, license, dependency and migration cost | Decision |
| --- | --- | --- |
| Keep raw per-line delimiter counts and require `--format csv` | No dependency, but every affected user must diagnose and override a false negative | Rejected. It contradicts the semantics of the parser reached by the override. |
| Add CleverCSV | Active, MIT, PyPI 0.8.5; three base requirements (`chardet`, `regex`, `packaging`) and a replacement dialect layer | Not selected. Its stronger messy-file detection is valuable, but the reproduced standard quoted records need only EvalInt's existing parser. |
| Require csvkit preprocessing | Active, MIT, PyPI 2.2.0; eight base requirement entries and a separate command/migration step | Rejected. It is a broad conversion suite rather than a runtime fix for EvalInt's preflight. |
| Load through pandas | Active, BSD-3-Clause, PyPI 3.0.5; requires Python 3.11 while EvalInt supports 3.9, plus NumPy and date/time dependencies | Rejected. It would narrow platform fit and replace a zero-dependency reader for no benefit on this case. |
| Parse candidate logical records with Python `csv.reader` | Python standard library and PSF license; zero new dependencies, accounts, state, operating cost, or migration | Selected. Detection and reading now agree on quoted-field semantics. |

Repository and package maintenance metadata were checked through the GitHub API
and public PyPI metadata on the research date. Requirement-entry counts include
conditional entries and are dependency-weight signals, not installed-package
counts. No external code is copied or linked into EvalInt.

## Resulting contract and limits

- Auto detection tries comma, tab, semicolon, and pipe dialects and examines up
  to five nonblank logical records. A candidate needs at least a header plus one
  row, at least two fields, and consistent field counts.
- Double-quoted fields may contain the delimiter, doubled quote characters, and
  CR/LF newlines without changing the logical row width.
- The whole selected CSV is parsed strictly. An unterminated quote or a row
  wider than its header stops import with a line-numbered error; no report is
  emitted from the accepted prefix.
- `--format csv` bypasses shape detection but not strict parsing.

This deliberately does not guess every CSV-like dialect. Single-quote quoting,
backslash escapes, multi-character delimiters, comments, preambles, or early
ragged rows may remain false negatives and need conversion. Conversely, a
small non-eval table with consistent delimiters can be classified as CSV, then
fail later because it has no supported item/system/score shape.

A clean parse proves only structural readability under the selected dialect.
It does not prove that all intended rows were exported, headers mean what the
producer intended, scores use the right units, copied files are independent,
or inputs are original and retained elsewhere.
