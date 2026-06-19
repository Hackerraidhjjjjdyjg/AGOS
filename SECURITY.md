# Security Policy

AGOS is an agentic operating system composed of a Rust kernel, a Go
orchestrator, and Python agents. Because it runs untrusted agent workloads and
brokers credentials, we take security reports seriously.

## Supported Versions

AGOS is pre-1.0 and under active development. Security fixes are applied to the
latest released minor version and to `main`. Older pre-release versions do not
receive backported fixes.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/Hackerraidhjjjjdyjg/AGOS/security/advisories/new)
(the **"Report a vulnerability"** button under the repository's **Security**
tab). This keeps the report confidential until a fix is available.

When reporting, please include:

- A description of the vulnerability and its impact.
- The affected component (`rust-kernel`, `go-orchestrator`, or `agents`) and
  version or commit SHA.
- Steps to reproduce, including any proof-of-concept code.
- Any suggested remediation, if known.

## What to Expect

- **Acknowledgement** within 3 business days.
- **Triage and severity assessment** within 7 business days, using CVSS to
  classify severity.
- **Status updates** at least every 7 days until the report is resolved.
- **Resolution**: once a fix is ready we will coordinate a release and, with
  your permission, credit you in the advisory. If a report is declined we will
  explain why.

## Scope and Hardening Notes

The orchestrator is designed so that secrets are never hardcoded. Operators
must supply the following via the environment (or a secrets manager / KMS):

- `AGOS_MASTER_KEY` — 64 hex characters (32-byte AES-256 key) used by the
  kernel bridge to encrypt swapped memory regions.
- `AGOS_ADMIN_EMAIL` / `AGOS_ADMIN_PASSWORD_HASH` — admin login credentials.
  The password must be a bcrypt hash; admin login is disabled until both are
  set. There is no default account.
- `AGOS_DB_PASSWORD` (or `POSTGRES_PASSWORD`) — database password.
- `JWT_SECRET` — signing secret for API tokens.

Passwords are hashed with bcrypt, API keys are compared in constant time, and
trace identifiers are generated with `crypto/rand`. Please report any
deviation from these guarantees.
