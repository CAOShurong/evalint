# Deep JSON: fail with a bounded import error

Research snapshot: 2026-08-12.

## The failure users hit

EvalInt v0.2.23 passed JSON text directly to Python's standard decoder during
both automatic format detection and the selected JSON reader. A public PyPI
installation was given a valid 120,101-byte JSON array containing 12,000 nested
objects inside an otherwise ordinary result record. Automatic detection and a
forced `--format jsonl` both exited `1` with empty stdout, but stderr contained
a 2,033-character Python traceback ending in `RecursionError`. The same
installed CLI accepted a 1,400-level fixture, demonstrating a runtime boundary
rather than a blanket rejection of nested metadata.

This is a known parser boundary, not an EvalInt-specific JSON grammar rule.
Python's documentation warns that untrusted JSON can consume considerable CPU
and memory, recommends limiting input size, and says the standard decoder has
no nesting limit beyond the interpreter's own limits. CPython previously fixed
a highly nested decode path that could segfault, making a controlled exception
the intended failure rather than proof that arbitrary depth is supported.
Practitioner reports show the same `json.loads` recursion failure on real API
responses and explicitly call out the need for applications to turn it into a
controlled error.

Sources:

- [Python `json` warning and implementation limits](https://docs.python.org/3/library/json.html)
- [CPython issue 12017: highly nested JSON decode could segfault](https://bugs.python.org/issue12017)
- [Stack Overflow: deeply nested API JSON can exceed the decoder's recursion boundary](https://stackoverflow.com/questions/49732069/maximum-recursion-depth-exceeded-requests)
- [Practitioner discussion: applications should convert the recursion failure into a controlled error](https://www.reddit.com/r/Python/comments/17x4dvu/how_to_break_pythons_json/)

## Maintained alternatives considered

The package and repository metadata below was checked on 2026-08-12.

| Approach | Maintenance, license, dependencies, platform and migration cost | Decision |
| --- | --- | --- |
| Raise Python's recursion limit | No dependency, but moves a process-safety boundary, varies by runtime/platform, and can turn a caught exception into a native stack failure | Rejected. EvalInt should not mutate a process-global interpreter limit for one input. |
| [`orjson`](https://github.com/ijl/orjson) 3.11.9 | Actively maintained; MPL-2.0 plus Apache-2.0-or-MIT; no Python runtime dependencies; compiled wheels across major desktop/server platforms; Python >=3.10; rejects nesting at 1,024 levels with `JSONDecodeError` | Rejected here. It drops EvalInt's Python 3.9 support and does not provide the standard decoder's `object_pairs_hook`, which EvalInt uses to reject duplicate members before data loss. |
| [`msgspec`](https://github.com/jcrist/msgspec) 0.21.1 | Actively maintained; BSD-3-Clause; no mandatory runtime dependencies; compiled wheels; Python >=3.10; optimized typed decoding would require revalidating coercion and duplicate-member behavior across every importer | Rejected here. The migration and compatibility loss are disproportionate to an exception-boundary fix. |
| [`ijson`](https://github.com/ICRAR/ijson) 3.5.1 | Actively maintained; BSD-3-Clause and ISC; no runtime dependencies; Python >=3.9; streaming can reduce whole-document memory cost | Deferred. Replacing shape detection and five readers with an event-stream state machine is valuable only as a separately researched large-file feature; it would not be a minimal fix. |
| Catch decoder `RecursionError` at strict decoding and shape probes | Zero dependencies, no account/network/operating cost, preserves Python 3.9 and every existing format and duplicate-member check | Selected. |

## Resulting contract and limits

- Automatic detection, native matrix JSON, generic JSON/JSONL, Promptfoo, and
  OpenAI Evals decoding convert the runtime recursion boundary into exit `1`.
- The error says that JSON nesting is too deep and suggests a flatter export.
  It does not echo object names, values, prompts, labels, or other input data.
- JSON report stdout stays empty and no Python traceback is printed.
- EvalInt does not set a fixed portable depth number. Python versions,
  platforms, interpreter settings, and decoder implementation details can
  reach their safe boundary at different depths.
- A clean parse does **not** prove the file is small, cheap to process,
  complete, correct, trustworthy, or safe. EvalInt still reads each input file
  fully into memory and does not impose a byte-size, object-count, string-size,
  CPU, or memory limit. Use operating-system resource limits for hostile input.
- False positives are possible when a legitimate producer intentionally emits
  extreme nesting that another parser accepts. Flatten the producer export or
  pre-process it outside EvalInt; increasing Python's recursion limit is not a
  supported migration path.
- False negatives remain possible below the runtime boundary: a shallower but
  very large or expensive document can still consume substantial resources,
  and this check does not inspect semantic truth or producer provenance.

This is graceful-failure hardening, not a denial-of-service immunity claim or
a substitute for backups, isolation, input quotas, and producer validation.
