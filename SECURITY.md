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
