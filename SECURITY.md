# Security policy

## Supported versions

Security fixes are provided for the latest released minor version. Upgrade to
the newest release before reporting a problem that may already be fixed.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not put
secrets, exploit details or private evaluation data in a public issue. Public
issues are appropriate for ordinary correctness bugs that do not expose data
or cross a security boundary.

## Runtime boundary

EvalInt is a local, offline analyzer. Its runtime has no third-party
dependencies, makes no network requests, loads no plugins and does not execute
code from an input file. It reads the paths explicitly passed on the command
line and writes only the path explicitly passed to `--save-reduced`. That
output may replace an existing non-input file, but EvalInt refuses lexical,
symbolic-link, and hard-link aliases of every input. A complete sibling
temporary file is flushed before `os.replace`; write failures leave an
existing output intact and return exit `1` without a traceback.

Plain reduced-id output is one logical id per physical line. If a kept id
contains any line boundary recognized by Python, EvalInt refuses the write
before creating a temporary file; it does not split the id or replace an
existing destination. `--save-reduced-format jsonl` losslessly represents
arbitrary string ids as JSON strings, including embedded line breaks and NUL.
Consumers must parse that format as JSON data rather than execute it. A clean
serialization does not prove the ids still resolve in another dataset or that
the reduction is statistically appropriate for a later run.

Input files are still untrusted data. The current importers read a complete
file into memory, so a very large or deliberately hostile file can exhaust
memory or CPU. Run untrusted inputs with operating-system resource limits in a
multi-tenant environment. Files must be valid UTF-8; an optional leading UTF-8
BOM is accepted, while malformed bytes fail closed rather than being replaced
inside identifiers. Scores must be finite numbers in `[0, 1]`; out-of-range,
`NaN`, and infinite values fail before statistics are computed instead of
being silently clamped. Blank and unparseable scores remain missing, but an
item with a recognizable id remains in the coverage denominator even when all
of its scores are missing. An explicitly named system with no usable scores
causes exit `1` rather than disappearing from a plausible subset report. A
successful audit is a statistical diagnostic, not a security verdict, proof
that answer keys are correct, or proof that the evaluation process is free
from data leakage or prompt injection.

CSV detection parses up to five nonblank logical records under the supported
comma, tab, semicolon, and pipe delimiters, so delimiters and newlines inside
double-quoted fields do not split a record. The selected reader then parses the
whole file strictly: unterminated quotes and fields beyond the header width
fail with a bounded import error. Exotic quoting or escape conventions can
still be rejected, and a structurally valid CSV can still contain wrong
headers, omitted rows, duplicated exports, or misleading values. Successful
detection is not a completeness, provenance, or semantic-validity check.

Exact duplicate CSV header names fail before a data row is mapped into a
dictionary, preventing last-column-wins value loss. The error names at most
three duplicated headers and never echoes row values. Case variants, whitespace
variants, and different aliases such as `item_id` and `id` remain distinct
headers; EvalInt does not infer that a producer intended them to be one column.
This check is structural, not a full schema or meaning validator.

Malformed JSONL and OpenAI Evals records fail at the first invalid line with a
bounded line/column error. They are not skipped or auto-repaired, because doing
so could remove scored items or systems and leave a plausible subset report.
Promptfoo JSON syntax errors use the same no-traceback boundary.

All actual JSON readers reject a repeated member name before an ordinary
dictionary can discard the earlier value. This prevents an ambiguous object
from silently replacing a schema marker, score, identifier, or metadata field.
Errors name only the format and, for JSONL, the physical line; they do not echo
the member name or either value. A producer that intentionally relies on
first-wins, last-wins, or multi-value semantics must emit one unambiguous
member instead. This check cannot detect duplicates already collapsed by an
upstream parser, semantic aliases, duplicate records, or false content, and it
does not authenticate the source or prove completeness.

The generic JSON/JSONL flattener also refuses different scalar values that
distinct inspected paths expose under the same recognized item, system, score,
text, or expected-answer name. Matching is case-insensitive, as field lookup
already is, and full flattened paths can conflict with direct fields. The
error names only the record location; it does not echo either path, name, or
value. Exact same-type/same-value repetitions remain accepted, while conflicts
between unconsumed metadata are ignored. This boundary does not infer that two
different aliases are semantically the same, inspect arbitrary depth or arrays,
authenticate a producer, or prove that the selected field is true.

Generic JSON/JSONL and CSV records fail closed when a required item or system
identifier is missing, null, empty, or whitespace-only. EvalInt does not invent
an identity from a row number and does not silently skip the record. Valid
nonblank identifiers retain their exact spelling, so whitespace and alias
variants can still remain distinct. This check does not authenticate names,
prove that records are complete, or establish that two named systems are
independent comparison targets.

The native `evalint/matrix-v1` reader also refuses duplicate, null, blank, or
non-string item and system identities, and refuses score keys that are absent
from its declared system array. This prevents a malformed round-trip artifact
from manufacturing duplicate comparison columns or silently expanding the
comparison set. Repeat metadata must use a declared system that has a score on
the same item, and counts must be positive integer-valued JSON numbers. This
prevents fractional counts from being truncated and unmatched counts from
being silently discarded. Exact spelling variants remain distinct, counts are
not authenticated against source runs, and a valid structure does not prove
statistical independence, completeness, provenance, or correct aggregation.
The root schema marker is required and must exactly name `evalint/matrix-v1`;
an explicit `--format matrix` selects the reader but cannot override this
version gate. This prevents an unknown future format from being silently
interpreted with current semantics. It does not authenticate the marker or
prove that the producer actually followed the named contract.
Native item `text` and `expected` properties must be strings when present, and
`tags` must be an array containing only strings. This prevents JSON null and
other types from being coerced into invented prompt or answer text, and keeps a
single tag string from becoming character labels. Omitted properties keep their
empty defaults. This type check does not prove that metadata is true, complete,
correctly attached, or safe for a different display context; tags are not used
by the current statistical audit.
Native score values must be JSON numbers and must remain finite and within
`[0, 1]`. Booleans, quoted numbers, null, arrays, and objects fail before they
can affect rankings or statistics. Native score errors identify the item
position without echoing the rejected value or labels. Generic third-party
formats retain compatibility coercion because CSV lacks scalar types and some
producers expose boolean pass flags. Numeric type and range validation does not
authenticate the grader, prove the declared scale, prove independence, or show
that any intended observation was supplied.

Human-readable reports and CLI error details encode imported identifiers,
system names, source paths, and other untrusted labels before writing them to
the terminal. Non-printable Unicode and control characters are emitted as
visible Python-style escape spellings, so input data cannot supply an ANSI
clear-screen, cursor movement, hyperlink, injected line, or bidirectional
override. EvalInt's own colour sequences are generated separately from this
data boundary. Machine-readable JSON deliberately retains the original label
strings; consumers that later display those strings must apply the encoding
appropriate to their own output context. This is terminal-output
neutralization, not input authentication or a promise that every terminal
emulator is free of vulnerabilities.

Path and format labels provide diagnostic provenance only. They do not hash,
sign, archive, or authenticate an input, and a successful report does not
prove that the named files are the producer's original exports. Mixed-format
labels are deterministic summaries, not full data-lineage records.

Conflicting nonempty prompt text or expected answers for one item id fail
closed before statistics are computed. The error names the item id and source
paths but does not echo the conflicting content. Id-only exports cannot expose
content drift, and this comparison is not a dataset-version or integrity proof.

Multi-file imports compare filesystem device and file identifiers before
parsing. Repeated paths, symbolic links, and hard links to one physical file
fail instead of inflating represented runs and measurements. The check does
not hash contents: independent copied files remain valid, even if they are an
accidental duplicate export. A clean check therefore does not prove unique
content, independent provenance, or that every intended run was supplied.
Remote, virtual, and unusual filesystems can expose incomplete or unstable
file identifiers; a hostile process can also replace a path after the check.

The alias check and replacement are a local accidental-loss boundary, not a
defence against a hostile process changing filesystem links concurrently.
Filesystem and operating-system crash guarantees also vary; no claim is made
that a successful return replaces backups or storage-level durability.
