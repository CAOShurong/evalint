# Native schema version: selecting a reader is not accepting a version

Research snapshot: 2026-08-12.

## The failure users hit

EvalInt's native JSON format names itself with
`"schema": "evalint/matrix-v1"`. Public EvalInt v0.2.18 used that value for
automatic detection but did not validate it in the native reader itself. This
created a contradictory recovery path:

1. a file with a missing, null, or future `evalint/matrix-v2` marker failed
   automatic detection and told the user to pass `--format`;
2. `--format matrix` on the same file exited `0`, reported two items and two
   systems, and silently interpreted the unknown document with v1 semantics.

The fixtures are synthetic. They demonstrate that an explicit format flag
bypassed the only version check; they do not show that a v2 producer exists or
that users have already lost data.

Version markers are established semantic boundaries. JSON Schema recommends a
root dialect declaration so a reader knows which keywords and meanings apply,
and its `const` keyword expresses one exact supported value. Kubernetes defines
`apiVersion` as the versioned representation schema and permits rejection of
unrecognized values. SARIF requires a version property and GitHub code scanning
supports one declared version. CycloneDX likewise requires `specVersion` to say
which specification a BOM follows.

Practitioner work shows both sides of the compatibility trade-off. A current
Shift clipboard request explicitly requires future versions to be rejected at
the external-data boundary. An OpenAPI tools report documents that refusing a
future 3.3 document is a defensible safe default, while also making clear that
real support requires a new parser rather than relabeling it as an older
version. npm takes the opposite, intentionally permissive approach for
lockfiles, but it documents known version semantics and may fetch missing data
from the registry. EvalInt has no matrix-v2 compatibility map or recovery
source, so permissive fallback would only guess.

Sources:

- [JSON Schema dialect declarations](https://json-schema.org/understanding-json-schema/reference/schema)
- [JSON Schema exact constants](https://json-schema.org/understanding-json-schema/reference/const)
- [Kubernetes API versioned representations](https://kubernetes.io/docs/reference/kubernetes-api/definitions/api-resource-v1-meta/)
- [OASIS SARIF 2.1.0 version property](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html#def_version_property)
- [GitHub code scanning supports SARIF 2.1.0](https://docs.github.com/en/code-security/concepts/code-scanning/sarif-files)
- [CycloneDX 1.7 JSON `specVersion`](https://cyclonedx.org/docs/1.7/json/#specVersion)
- [Shift issue 137: reject unsupported future clipboard versions](https://github.com/shift-editor/shift/issues/137)
- [oastools issue 459: future-version refusal versus real parser support](https://github.com/erraggy/oastools/issues/459)
- [npm package-lock version compatibility and recovery](https://docs.npmjs.com/cli/v8/configuring-npm/package-lock-json/#lockfileversion)

## Maintained alternatives considered

| Approach | Maintenance, license, security, dependency and migration cost | Decision |
| --- | --- | --- |
| Treat `--format matrix` as permission to ignore the marker | Zero dependency and migration cost | Rejected. It produced the demonstrated exit-`0` interpretation of a future version. |
| Accept any `evalint/matrix-v*` marker as the newest known version | Zero dependencies | Rejected. No v2 contract or compatibility proof exists, so the prefix cannot establish field semantics. |
| npm-style best-effort recovery | Useful when known lockfile versions and a registry can supply omitted data; adds network and compatibility policy | Rejected. EvalInt is offline and has no authoritative source from which to reconstruct unknown native semantics. |
| `jsonschema` 4.26.0 with a required `const` | Active, MIT, Python 3.10+, 21 requirement entries including extras; local with no service cost | Rejected. It drops Python 3.9 and adds a general validator for one discriminator check. |
| Pydantic 2.13.4 literal/discriminated models | Active, MIT, Python 3.9+, six requirement entries including a compiled core; local with no service cost | Rejected. A model migration is heavier than dispatching the one existing native version. |
| One shared constant checked by detection, writer and reader | Python 3.9+, constant time, zero dependencies, accounts, network or operating cost | Selected. A new format version can later add an explicit reader before its marker is accepted. |

Package and repository metadata were checked through public PyPI and GitHub
APIs on the research date. Requirement-entry counts include conditional and
optional entries and are dependency-surface signals, not exact installed
package counts. Public GitHub advisory endpoint counts are not security audits
and do not prove that a dependency or this manual check is secure. No
third-party code is copied or linked into EvalInt.

## Resulting contract

- `Matrix.as_dict()`, automatic detection, and `Matrix.from_dict()` use one
  `NATIVE_SCHEMA` value: `evalint/matrix-v1`.
- The native reader requires the `schema` property and requires that exact
  string. Missing, null, numeric, and unknown/future values fail.
- `--format matrix` chooses the native reader when detection is impossible; it
  does not override the reader's version contract.
- Errors distinguish a missing marker from an unsupported one, state the one
  supported marker, and do not echo the supplied value or any score, prompt,
  answer, system name, or item id.
- The CLI exits `1` with empty stdout and no Python traceback. A valid v1 file
  and every `Matrix.as_dict()` round trip remain accepted.

## False positives, false negatives and remaining boundary

Hand-authored native JSON that omitted `schema` now fails even if every other
field looks like v1. Migration is to add the exact marker. Files that used a
private marker while relying on v1 behavior must either convert to the public
v1 contract or use their own importer; EvalInt cannot infer compatibility from
shape alone.

The exact marker does not prove that the producer followed v1, that the file is
complete, or that its scores and repeat counts came from real runs. Additional
top-level and item properties remain allowed for forward-compatible metadata.
This change does not implement v2, migrate old versions, authenticate a file,
or validate provenance. Supporting a future version requires defining its
semantics, adding an explicit reader and tests, and only then accepting its
marker; changing a string is not a migration.
