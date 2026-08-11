# Item identity: one id must mean one eval case

Research snapshot: 2026-08-11.

## The failure users hit

EvalInt merges files by item id so one model or repeated run can live in each
file. Public v0.2.9 trusted that key even when its identifying metadata had
drifted. A reproduced pair used `q1` for France/Paris in one CSV and
Germany/Berlin in another. The CLI exited `0` with empty stderr, preserved the
first prompt and answer, then attached the second file's score to that item and
reported a normal ranking.

That is not a cosmetic metadata issue: the item-by-system cell no longer means
that both systems were measured on the same question. Any ranking, coverage,
broken-item diagnosis, or reduction built on the merged cell can therefore be
plausible but invalid.

Research on data versioning states that the exact versions being aggregated
must be known for compatibility, reproducibility, provenance, and attribution.
MLflow represents an evaluation dataset with a source and digest for the same
reason. A current practitioner discussion describes recurring partner-file
drift and recommends explicit contracts plus fail-fast validation rather than
silent guessing.

Sources:

- [Research Data Alliance paper on exact versions before aggregation](https://datascience.codata.org/articles/10.5334/dsj-2021-012)
- [MLflow dataset source, digest, and evaluation lineage](https://mlflow.org/docs/latest/dataset/)
- [pandas merge cardinality validation](https://pandas.pydata.org/docs/reference/api/pandas.merge.html)
- [Great Expectations uniqueness validation](https://greatexpectations.io/legacy/v1/expectations/expect_column_values_to_be_unique/)
- [Practitioner discussion of recurring source-data drift and fail-fast contracts](https://www.reddit.com/r/dataengineering/comments/1o4f1x3/am_i_the_only_one_who_spends_half_their_life/)

## Maintained alternatives considered

| Approach | Maintenance, license, dependency and migration cost | Decision |
| --- | --- | --- |
| Treat item id as authoritative and ignore metadata differences | Zero dependencies and no migration | Rejected. It produced the demonstrated false merge and clean-looking report. |
| Use pandas merge validation | Active, BSD-3-Clause; PyPI 3.0.5 listed 5 base requirement entries, including NumPy and python-dateutil | Not selected. Cardinality checks reject or permit key repetition; they do not establish that valid repeated per-system rows describe the same eval case. |
| Add Great Expectations | Active, Apache-2.0; PyPI 1.20.0 listed 22 base requirement entries | Not selected. A uniqueness expectation would reject valid long-form repeated item ids, while a custom cross-file identity contract still has to encode EvalInt's semantics. |
| Require MLflow dataset digests | Active, Apache-2.0; PyPI 3.15.1 listed 20 base requirement entries and evaluation datasets require tracking state | Rejected for this boundary. It provides stronger versioned lineage but imposes a platform and migration on a zero-runtime-dependency file CLI. |
| Compare nonempty identifying fields in `Matrix.add_item()` | Standard library only; applies to every reader and direct API builder | Selected. The semantic collision is detected at the one shared normalization boundary. |

Repository and package maintenance metadata were checked through the GitHub
API and public PyPI metadata on the research date. Base requirement-entry
counts include platform markers and are dependency-weight signals, not
installed-package counts.

## Resulting contract and limits

- Repeated rows may share an item id when their nonempty `text` and `expected`
  values agree exactly.
- If either value conflicts, import stops before an audit is produced. A
  cross-file error names the item id, the conflicting source, and where that
  id was first seen, but does not echo prompt or answer contents.
- Missing text, including the reader's item-id display fallback, may be filled
  by a later real prompt. A missing expected answer may be filled similarly.
- Tags are descriptive and are not currently part of the identity check.

Exact comparison intentionally does not normalize case, whitespace, or prompt
wording: those changes can alter model behavior, and EvalInt cannot prove they
are equivalent. Conversely, an id-only export provides no text or answer to
compare, so content drift remains undetectable. EvalInt does not hash or retain
whole datasets; use versioned artifacts or lineage tooling when that stronger
guarantee is required.
