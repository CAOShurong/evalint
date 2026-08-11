# CSV headers: duplicate names lose values

Research snapshot: 2026-08-11.

## The failure users hit

EvalInt reads a CSV row as a dictionary keyed by its header. A dictionary
cannot contain the same key twice. CPython's `DictReader` therefore constructs
`dict(zip(fieldnames, row))`, so a later same-named column silently replaces
the earlier value.

Public EvalInt v0.2.12 reproduced the consequence with two `score` headers.
The first score column made alpha beat beta 1.0 to 0.0; the second contained the
opposite values. The duplicate-header file exited `0` with empty stderr and
ranked beta first, exactly matching a file that contained only the last score
column. The first scores disappeared without a warning. A repeated system
header in wide CSV loses cells by the same mechanism.

This behavior is documented as a practical problem, not a hypothetical one.
Python's issue tracker records that duplicate field names overwrite columns
silently, while the CPython implementation shows the dictionary construction.
W3C CSVW requires field names to be unique. Microsoft and AtoM import
validators instruct users to rename or remove duplicate headers rather than
guessing which column should win.

Sources:

- [CPython `DictReader` implementation](https://github.com/python/cpython/blob/main/Lib/csv.py)
- [Python issue 29614: duplicate field names overwrite silently](https://bugs.python.org/issue29614)
- [W3C CSVW unique field-name requirement](https://w3c.github.io/csvw/syntax/)
- [Microsoft CSV import validation for duplicate headers](https://learn.microsoft.com/en-us/viva/validation-errors-warnings)
- [AtoM duplicate-column-name validator](https://www.accesstomemory.org/en/docs/2.8/user-manual/import-export/csv-validation/)
- [Practitioner example of `DictReader` swallowing the first duplicate value](https://stackoverflow.com/questions/77859483/read-csv-with-duplicate-column-headers-in-python)

## Maintained alternatives considered

| Approach | Maintenance, license, dependency and migration cost | Decision |
| --- | --- | --- |
| Keep the last same-named column | Zero cost and current `DictReader` behavior | Rejected. It produced the observed silent ranking reversal. |
| Keep the first column or suffix later names automatically | Zero new dependency, but invents schema meaning and can make the ignored or renamed score column look intentional | Rejected. EvalInt cannot know which exporter column is authoritative. |
| Load through pandas and accept mangled duplicate names | Active, BSD-3-Clause, PyPI 3.0.5; Python 3.11+ plus NumPy/date-time dependencies | Rejected. Renaming to names such as `score.1` still leaves EvalInt to guess which semantic score to use and narrows Python support. |
| Require Frictionless schema validation | Active, MIT, PyPI 5.19.0; 20 base requirement entries plus explicit schema/workflow state | Rejected for the default CLI. It offers much broader validation but adds a substantial dependency and migration surface. |
| Check `DictReader.fieldnames` before reading rows | Python standard library, one linear header pass, zero runtime dependencies, accounts, services, or migration | Selected. It stops the exact data-loss mechanism at its source. |

Repository and package maintenance metadata were checked through the GitHub API
and public PyPI metadata on the research date. Requirement-entry counts include
platform conditions and are dependency-weight signals, not installed-package
counts. No external code is copied or linked into EvalInt.

## Resulting contract and limits

- Exact header strings must be unique in long and wide CSV inputs.
- The check runs after dialect parsing but before the first data row becomes a
  dictionary. An error lists at most three repeated names using escaped Python
  representations and does not include row values.
- EvalInt does not keep the first value, keep the last value, suffix a name, or
  merge columns, because each policy can change a score or system identity.
- `--format csv` bypasses shape detection but not header validation.

The check intentionally follows exact dictionary-key identity. `score` and
`Score`, headers with different whitespace, blank names, and different known
aliases such as `item_id` and `id` are not exact duplicates. Some may still be
ambiguous or unsupported, but rejecting them requires a broader schema policy
and compatibility evidence.

A clean header check proves only that no exact name will be overwritten during
dictionary construction. It does not prove that names are correct, unique after
external normalization, mapped to the intended semantics, or complete.
