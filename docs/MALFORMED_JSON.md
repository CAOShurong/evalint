# Malformed JSON: stop at the first bad record

Research snapshot: 2026-08-11.

## The failure users hit

EvalInt v0.2.7 sampled only the first five nonblank lines to recognize JSONL.
If those lines were valid but a later line was truncated, format detection
succeeded and the full reader leaked Python's `JSONDecodeError` traceback. A
public installed-CLI reproduction used five valid score records followed by a
sixth record cut off after `"score":`; it exited `1` with empty stdout, but its
stderr was a traceback and did not identify source record line 6 as the user
action point.

OpenAI Evals had the opposite failure: its reader caught `ValueError` and
silently skipped a malformed event line. Skipping is worse than a traceback for
an audit tool because the surviving rows can still produce a plausible score,
coverage figure, and ranking.

The JSON Lines specification requires every line to be an independently valid
JSON value and recommends, but does not require, a final newline. Corrupt or
truncated JSONL is a real operational failure rather than a hypothetical
fixture: current Codex CLI reports describe malformed transcript lines making
sessions disappear and a Windows turn hang after corrupt JSONL persistence.

Sources:

- [JSON Lines format requirements](https://jsonlines.org/)
- [Python `json.JSONDecodeError` location fields](https://docs.python.org/3/library/json.html#json.JSONDecodeError)
- [`jsonlines` invalid-line error and line number](https://jsonlines.readthedocs.io/en/latest/)
- [Codex issue 24425: a malformed JSONL history made a session disappear](https://github.com/openai/codex/issues/24425)
- [Codex issue 29066: malformed persisted JSONL preceded a stuck Windows turn](https://github.com/openai/codex/issues/29066)

## Maintained alternatives considered

| Approach | Maintenance, cost, and failure semantics | Decision |
| --- | --- | --- |
| Silently skip invalid records | Zero dependencies and keeps processing | Rejected. It changes the evaluated item/system population without consent and can make the survivors look clean. |
| Drop or auto-repair only a truncated final line | Convenient for append-only logs, but assumes the producer intended no record there and cannot recover its score or identity safely | Rejected. The audit cannot distinguish an interrupted write from deliberate but malformed data. |
| Add [`jsonlines`](https://github.com/wbolster/jsonlines) 4.0.0 | BSD-3-Clause; purpose-built reader with `InvalidLineError(lineno=...)`; one runtime dependency on `attrs`; repository was not archived and was last pushed in 2024 when checked | Not selected. Its useful error boundary is small enough to implement with the standard library, and EvalInt otherwise has zero runtime dependencies. |
| Enumerate lines and wrap standard-library `JSONDecodeError` | No dependency, account, network, or migration cost; retains Python's exact column and adds the source record number | Selected. |

## Resulting contract and limits

- JSONL records and OpenAI Evals events are decoded one nonblank line at a
  time. The first syntax error exits `1`, names the format, and reports the
  physical line and JSON column without a traceback.
- OpenAI Evals no longer skips malformed event lines.
- A forced `--format promptfoo` syntax error reports its document line and
  column without a traceback.
- No invalid record is repaired, skipped, or converted to a failed score.
- Valid JSONL does not require a trailing newline; blank physical lines remain
  ignored for compatibility, while reported line numbers still count them.

An auto-detected input whose first JSON-looking record is already malformed may
still receive the generic "could not recognise" error because no valid shape
exists to identify it as JSONL. Syntax validity also does not prove schema or
semantic correctness: a valid JSON object can still name the wrong item,
system, or score. Those are separate import and producer-validation boundaries.
