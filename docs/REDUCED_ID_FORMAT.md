# Reduced item ids: one logical id must stay one record

Research snapshot: 2026-08-12.

## The observed failure

EvalInt accepts item ids as Unicode strings. JSON and matrix inputs can encode
a line feed inside a string as `\n`, and quoted CSV can carry the same value.
Public EvalInt v0.2.14 then joined reduced ids with newline delimiters without
checking whether an id already contained a line boundary.

A 12-item matrix fixture used ids such as `q02\nvariant`. The installed CLI
exited `0`, reported that the reduction kept 3 ids, and wrote a 36-byte output
containing 6 physical lines:

```text
q02
variant
q10
variant
q11
variant
```

A downstream filter would read six different ids. Nothing in the file marked
which adjacent lines belonged together, so the original three strings could
not be recovered without outside knowledge.

This is the ordinary delimiter-collision problem. The
[GNU find manual](https://www.gnu.org/software/findutils/manual/html_node/find_html/Print-File-Name.html)
warns that newline-delimited names are ambiguous whenever a name may contain a
newline. [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259) defines JSON strings
that preserve such control characters through escapes, and
[JSON Lines](https://jsonlines.org/) places one valid JSON value on each
physical line. [RFC 7464](https://www.rfc-editor.org/rfc/rfc7464) provides a
different record-separator-based JSON sequence for streaming contexts.

## Alternatives and reuse decision

| Approach | Maintenance, license, dependency, platform, and migration cost | Decision |
| --- | --- | --- |
| Keep raw newline-delimited ids | Zero cost and backward compatible for ordinary ids | Rejected for ids containing line boundaries. It caused the observed unrecoverable record split. |
| Replace embedded breaks with the two characters `\\n` | Zero dependency, but collides with an id that already contains a literal backslash plus `n` unless every consumer adopts a new escaping grammar | Rejected. Silent bespoke escaping is not lossless interoperability. |
| Reject line breaks during import | Small standard-library check, but prevents valid analysis and lossless JSON output even when no reduced list is requested | Rejected. The constraint belongs to the selected output format. |
| Add a NUL-delimited mode like `find -print0` | Zero dependency and robust for newlines, but NUL itself can occur in EvalInt's string model and Windows/editor/JSON tooling is less convenient | Not selected. It moves the delimiter limit rather than representing every string. |
| Write one-column CSV | Python standard library and RFC-style quoting, but a logical record containing a newline still spans physical lines and line-oriented consumers remain easy to misuse | Not selected. |
| Add JSON Lines through `jsonlines` 4.0.0 | BSD-3-Clause, Python 3.8+, one `attrs` dependency; latest release observed from 2023 and repository activity from 2024 | Rejected as unnecessary dependency and maintenance surface for serializing strings. |
| Add `orjson` 3.11.9 | Active; PyPI declares `MPL-2.0 AND (Apache-2.0 OR MIT)`; no Python dependency, but compiled wheels, Python 3.10+, and a narrower platform/support envelope | Rejected. It would drop Python 3.9 for a tiny serialization path. |
| Use standard-library `json.dumps` for an explicit JSONL mode | Python 3.9+, zero runtime dependencies, linear local cost, no account/service/network or existing-data migration | Selected. Each id becomes one JSON string per LF-delimited physical record, so quotes, backslashes, controls, NUL, and Unicode round-trip. |

Package versions, requirements, licenses, and repository activity were checked
through public PyPI metadata and the GitHub API on the research date. No
alternative code is copied or linked into EvalInt. GitHub's repository
security-advisory endpoints returned no published advisories for `jsonlines`
or `orjson`; that absence is not proof that either package has no security
defects. The selected standard-library path avoids adding their supply-chain
and compiled-platform surface but does not make a broader security claim.

## Resulting contract and limits

- `--save-reduced FILE` keeps the established plain one-id-per-line format for
  ordinary ids.
- Before creating a temporary output, plain mode refuses every boundary that
  Python `splitlines()` recognizes: CR, LF, vertical tab, form feed, file/group/
  record separators, next-line, and Unicode line/paragraph separators. An
  existing destination remains unchanged and the CLI exits `1` without a
  partial report or traceback.
- `--save-reduced-format jsonl` writes each kept id as one JSON string followed
  by LF. Parsing each physical line with an RFC 8259 JSON parser recovers the
  exact original string, including embedded breaks and NUL.
- The format is explicit rather than inferred from the filename. Existing
  scripts receive unchanged plain text unless they opt into JSONL.

Plain mode can conservatively refuse Unicode line separators even when one
particular consumer would not split them; JSONL is the lossless escape hatch.
Conversely, a consumer that splits plain output on arbitrary whitespace rather
than lines can still mishandle spaces or tabs inside an id. That is outside the
documented format.

A successful write proves only that the selected serialization represented the
kept strings without record collision. It does not prove that ids are unique in
another system, still resolve against a changed dataset, came from the claimed
producer, or that the statistical reduction itself is appropriate for a new
use case. JSONL must be parsed as JSON data, never evaluated as code.
