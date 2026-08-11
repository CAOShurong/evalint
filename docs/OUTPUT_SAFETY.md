# Reduced output: never turn an export into data loss

Research snapshot: 2026-08-11.

## The observed failure

EvalInt v0.2.4 passed `--save-reduced` directly to `Path.write_text`. In a
real installed-CLI reproduction, using the input as the output exited `0` and
changed a 229,082-byte CSV into a 1,510-byte list of item ids. The SHA-256
changed from `EA3AE536...44AABE` to `A05CDEBD...B829D3`. Using a directory as
the destination returned exit `1` only because an uncaught exception printed a
traceback.

This is an accidental-loss boundary, not a statistical edge case. Public CLI
reports describe the same class of damage when an overwrite-only operation
silently replaces a journal or other source data. GNU `sort` deliberately
supports an input also being its output, but reads before opening and still
warns that a crash or I/O error can lose data. EvalInt's reduced output is a
different artifact, so in-place behavior has no valid use here.

Sources:

- [GNU sort output-file semantics and data-loss warning](https://www.gnu.org/software/coreutils/sort)
- [Python `os.path.samefile`: device/inode identity and Windows support](https://docs.python.org/3/library/os.path.html#os.path.samefile)
- [Python `NamedTemporaryFile`](https://docs.python.org/3/library/tempfile.html#tempfile.NamedTemporaryFile)
- [Python `os.replace`](https://docs.python.org/3/library/os.html#os.replace)
- [Practitioner report of overwrite-only CLI data loss](https://github.com/google-gemini/gemini-cli/discussions/7432)

## Alternatives considered

Repository and package state were checked on 2026-08-11.

| Approach | Maintenance, dependency, and behavior | Decision |
| --- | --- | --- |
| Direct `Path.write_text` | Standard library, zero dependencies; truncates the destination before the complete output exists | Rejected. It caused the reproduced source overwrite and can damage an existing output on failure. |
| Permit in-place output like GNU `sort -o F F` | Mature behavior for a transformation whose output replaces its input; still has documented crash/I/O risks | Rejected. A reduced id list is not the original result-file format and cannot be a valid in-place transformation. |
| [`atomicwrites` 1.4.1](https://github.com/untitaker/python-atomicwrites) | MIT, but archived and explicitly unmaintained since 2022 | Rejected. Its own maintainer points Python 3 users to `os.replace`; adding an abandoned dependency increases supply-chain surface without needed behavior. |
| [`boltons` 26.1.0](https://github.com/mahmoud/boltons) atomic save | Active broad utility package; adopting it adds unrelated APIs and migration weight | Rejected. EvalInt needs only a small standard-library path. |
| `samefile` guard plus sibling temporary file and `os.replace` | Standard library, zero runtime dependencies; detects existing hard-link/symlink aliases and avoids exposing partial contents | Selected. It preserves the zero-dependency, offline install and fails with an actionable CLI error. |

## Resulting contract and limits

- A `--save-reduced` path that resolves to any input is refused before the
  input is audited or modified.
- Existing hard-link aliases are detected with `os.path.samefile`; lexical and
  existing symbolic aliases are covered by the same identity check, while a
  normalized absolute-path comparison covers lexical aliases.
- The complete UTF-8/LF output is written and flushed in the destination
  directory before `os.replace` is attempted.
- A failed write or replacement removes the temporary file when possible,
  leaves an existing destination unchanged, prints one user-facing error, and
  exits `1` without report output or a traceback.
- A successful save intentionally replaces an existing non-input output.

This does not provide a transaction against hostile concurrent link swaps, and
it does not promise storage-controller or power-loss durability. Python
documents successful `os.replace` as atomic under POSIX; platform and
filesystem guarantees can differ. Keep independent backups of source eval
results and choose a dedicated output path.
