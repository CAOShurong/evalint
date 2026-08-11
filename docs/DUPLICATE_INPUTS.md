# Duplicate inputs: one physical result file, one contribution

Research snapshot: 2026-08-11.

## The failure users hit

EvalInt accepts multiple result files because evaluation frameworks commonly
write one file per model or repeated run. Public v0.2.10 did not distinguish a
new file from a second name for one already supplied. In a reproduced Windows
run, one fixture reported 2 runs and 3 measurements. Passing the same path
twice, or the original plus an NTFS hard-link alias, exited `0` and reported 4
runs and 6 measurements while retaining only 3 observed item-system cells.

This is silent double counting. The ranking may stay unchanged, which makes
the error difficult to notice, while the report claims more repeated evidence
than was actually provided. Practitioners describe the same general failure
in batch pipelines: retries or the same source arriving twice produce duplicate
data unless ingestion is idempotent.

Hard links make the path distinction especially important. Two hard-link names
refer to one file, while two independent files can contain identical bytes.
Python exposes the former distinction through device and file identifiers;
`os.path.samefile()` has used the same implementation on Windows since Python
3.4. File tools such as jdupes and fclones likewise avoid treating linked names
as independent replicas by default.

Sources:

- [Python `os.path.samefile()` filesystem identity](https://docs.python.org/3/library/os.path.html#os.path.samefile)
- [GNU Findutils on names that refer to the same inode](https://www.gnu.org/software/findutils/manual/html_node/find_html/Hard-Links.html)
- [jdupes double-traversal and hard-link handling](https://github.com/h2oai/jdupes/blob/master/README.md)
- [fclones linked-file handling](https://github.com/pkolaczk/fclones)
- [Practitioner discussion of duplicate data from pipeline reruns](https://www.reddit.com/r/dataengineering/comments/1stehve/how_do_you_design_idempotent_data_pipelines_in/)

## Maintained alternatives considered

| Approach | Maintenance, license, dependency and operating cost | Decision |
| --- | --- | --- |
| Trust every path argument as a new run | Zero cost | Rejected. It produced the demonstrated false run and measurement counts. |
| Compare normalized or resolved path strings | Standard library only and cheap | Rejected alone. It catches repeated and symbolic-link spellings but not hard links. |
| Hash every input and reject equal bytes | Standard library only, but reads every byte and scales with total input size | Rejected. Independent stochastic runs can legitimately produce identical files, so content equality is not run identity. |
| Require jdupes or fclones as a preflight | Both active, MIT-licensed standalone tools; extra installation and a separate scan step | Not selected. Their linked-file semantics support the decision, but neither is a Python runtime component or eval-run provenance system. |
| Persist a digest manifest or pipeline ledger | Stronger across invocations, but adds state, migration, cleanup, and identity policy | Rejected for this local one-shot boundary. It would still need a rule that permits intentionally repeated equal outputs. |
| Cache `(device, file identifier)` from one metadata read per path | Python standard library, zero runtime dependencies, linear metadata cost, no account or migration | Selected. It identifies repeated paths, symbolic links, and hard links without reading or comparing content. |

Repository maintenance and license metadata were checked through the GitHub
API on the research date. No external code is copied or linked into EvalInt.

## Resulting contract and limits

- `load_many()` checks every caller-supplied path before parsing. If two paths
  identify one physical file, import exits with an error naming both paths.
- The check follows symbolic links and recognizes hard links on filesystems
  that expose stable device and file identifiers.
- Byte-identical independent files remain valid and are represented as repeat
  measurements when their item-system cells collide.
- Unreadable paths fall back to normalized absolute-path comparison so the
  same missing spelling is diagnosed once; the normal read error still handles
  distinct unreadable paths.

The intentional false-negative boundary is content duplication: copying one
export to a new physical file and passing both copies is not detected, because
that is indistinguishable from two legitimate runs with identical output.
Possible false positives or negatives remain on remote, virtual, or unusual
filesystems whose device/file identifiers are missing, reused, or unstable.
There is also a check-to-read race if another process replaces a path.

A successful check proves only that EvalInt did not observe two supplied paths
with the same filesystem identity at check time. It does not prove unique
content, independent run provenance, a complete export set, or the existence
of any backup or retained source artifact.
