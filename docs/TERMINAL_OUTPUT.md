# Terminal output: data must not become commands

Research snapshot: 2026-08-11.

## The observed failure

EvalInt v0.2.13 wrote imported system names and item ids directly into its
human-readable report. A valid JSONL file containing an ESC clear-screen
sequence followed by a cursor-home sequence therefore emitted both raw ESC
bytes even with `--color never`. A terminal could clear the preceding audit
and place attacker-chosen text where a result or error appeared to be.

The same risk applies to source paths and import errors: carriage returns,
newlines, OSC hyperlinks, bidirectional overrides, and other control
characters can change how a human sees a report without changing its bytes.
This is an output-context problem, not evidence that the imported evaluation
data executed Python code.

Relevant primary and independent references:

- [CWE-117](https://cwe.mitre.org/data/definitions/117.html) describes
  untrusted data corrupting or forging interpreted output and recommends
  transforming it for the downstream context.
- [RUSTSEC-2025-0055](https://rustsec.org/advisories/RUSTSEC-2025-0055.html)
  documents a real terminal-output vulnerability in which ANSI sequences from
  user input could clear screens, move cursors, or mislead users.
- [Python `str.isprintable`](https://docs.python.org/3/library/stdtypes.html#str.isprintable)
  defines non-printable Unicode as the characters that `repr()` escapes. That
  makes it a small standard-library building block for this zero-dependency
  CLI; it does not sanitize output by itself.

## Alternatives considered

| Approach | Trade-off | Decision |
| --- | --- | --- |
| Keep writing labels verbatim | Preserves exact display but lets input bytes control an interactive terminal | Rejected. `--color never` must mean no ESC bytes from either the application or its data. |
| Delete ESC bytes only | Stops common ANSI control-sequence introducers but leaves CR/LF, C1 controls, OSC terminators, bidirectional overrides, and ambiguous invisible text | Rejected. A narrow denylist is easy to bypass and loses evidence without showing what changed. |
| Apply `repr()` to the whole report | Makes controls visible but also quotes every label and escapes ordinary Unicode, degrading routine reports | Rejected. The trust boundary is each imported value, not EvalInt's static report text. |
| Add a terminal-sanitizing dependency | Mature packages can cover broader terminal use cases but add supply-chain and maintenance surface to a zero-runtime-dependency tool | Rejected. EvalInt needs no cursor-width calculation or terminal parser; character-wise visible encoding is sufficient. |
| Escape non-printable characters only at text-output sinks | Preserves ordinary Unicode, keeps trusted colour generation separate, and leaves the data model unchanged | Selected. The same helper also escapes all non-ASCII characters when `--ascii` is requested. |

## Resulting contract

- Human-readable source names, system labels, item ids, warnings, and CLI error
  details cannot emit imported control characters. Each becomes a visible
  `\xNN`, `\uNNNN`, or related Python-style spelling.
- Trusted colour codes originate only in `Palette`; escaping a data label does
  not disable `--color always`.
- `--color never` emits no ESC bytes, including when the input contains them.
- `--ascii` produces an ASCII-only report by escaping non-ASCII labels as
  well as control characters.
- JSON output retains the original strings. This keeps the machine-readable
  representation lossless, but any program that later writes those values to
  a terminal must apply its own output-context encoding.

This boundary does not validate the truth, provenance, or intended meaning of
a label. It does not limit label length, make an untrusted file safe against
CPU or memory exhaustion, or establish that every terminal emulator is free
of implementation vulnerabilities. It prevents imported control characters
from reaching EvalInt's human-readable terminal sinks as active commands.
