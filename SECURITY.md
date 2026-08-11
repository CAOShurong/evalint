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
line and writes only the path explicitly passed to `--save-reduced`.

Input files are still untrusted data. The current importers read a complete
file into memory, so a very large or deliberately hostile file can exhaust
memory or CPU. Run untrusted inputs with operating-system resource limits in a
multi-tenant environment. Files must be valid UTF-8; an optional leading UTF-8
BOM is accepted, while malformed bytes fail closed rather than being replaced
inside identifiers. A successful audit is a statistical diagnostic, not a
security verdict, proof that answer keys are correct, or proof that the
evaluation process is free from data leakage or prompt injection.
