# Encoding boundary: preserve identifiers or stop

Research snapshot: 2026-08-11.

## The failure users hit

EvalInt v0.2.1 read every file as UTF-8 with `errors="replace"`. That created
two opposite failures:

1. A valid UTF-8 BOM became `U+FEFF` at the start of `item_id`, so a normal
   long-form CSV was reported as containing no eval items.
2. An invalid byte inside an item or system id became `U+FFFD`. Distinct byte
   strings could collapse to the same identifier and still produce a clean,
   plausible report.

The first case is ordinary Windows interoperability, not a corrupt fixture.
Microsoft says Excel opens a UTF-8 CSV normally when it is saved with a BOM.
Python's CSV reader deliberately does not remove the mark itself, and the
Python codec documentation specifies `utf-8-sig` for decoding and skipping an
optional leading BOM.

Primary and practitioner evidence:

- [Microsoft: Opening CSV UTF-8 files correctly in Excel](https://support.microsoft.com/en-US/Excel/opening-csv-utf-8-files-correctly-in-excel)
- [Python codecs: `utf-8-sig` skips the leading UTF-8 BOM](https://docs.python.org/3/library/codecs.html#encodings-and-unicode)
- [CPython issue 23178: CSV headers retain `U+FEFF` without preprocessing](https://bugs.python.org/issue23178)
- [PowerShell `Export-Csv`: both `utf8BOM` and `utf8NoBOM` are supported encodings](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/export-csv)

## Alternatives considered

Repository activity, licenses and releases were checked through the GitHub API
on 2026-08-11.

| Approach | Maintenance / license / weight | Why it was or was not selected |
| --- | --- | --- |
| Standard-library `utf-8-sig`, strict errors | Python standard library; no dependency or operating cost | Selected. It accepts UTF-8 with or without a BOM and fails at the first invalid byte, preserving the identity boundary. |
| UTF-8 with replacement | No dependency | Rejected. It keeps the command running by silently changing identifiers, which can merge records and invalidate the audit. |
| [charset-normalizer 3.4.9](https://github.com/jawah/charset_normalizer) | Active; MIT; additional runtime dependency and detection pass | Useful when approximate recovery is the goal. Eval identifiers require deterministic bytes-to-text semantics, and a confidence guess is not evidence that the chosen legacy encoding is correct. |
| [chardet 7.4.3](https://github.com/chardet/chardet) | Active; 0BSD; additional runtime dependency and detection pass | Same uncertainty and migration cost as charset-normalizer. |
| [pandas 3.0.5](https://github.com/pandas-dev/pandas) | Active; BSD-3-Clause; NumPy-backed data stack | Supports explicit encodings but is far heavier than the zero-dependency CLI and does not decide which encoding the producer intended. |
| [csvkit](https://github.com/wireservice/csvkit) | Active; MIT; separate CLI with multiple dependencies | A reasonable explicit conversion step for legacy CSV, but not a reason to make EvalInt guess silently. |

## Resulting contract

- UTF-8 without a BOM: accepted.
- UTF-8 with one leading BOM: accepted and normalized before format detection.
- UTF-16, Windows code pages, and malformed UTF-8: exit `1` with a byte offset
  and an instruction to re-export as UTF-8.
- The string API applies the same leading-`U+FEFF` normalization as file input.

This does not prove the producer used the intended characters; it prevents
EvalInt from silently inventing different ones. Users with a known legacy
encoding should convert explicitly with a tool that names that encoding, then
audit the UTF-8 result.
