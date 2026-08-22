# Security

## What this tool can and cannot do

`genesys-flow-doc` reads a Genesys Cloud configuration and writes files to your
own machine. It has no code path that can change anything in Genesys Cloud.

Every Platform API call is a `GET`. The single non-`GET` request in the project
is the OAuth token exchange, which
[RFC 6749 §3.2](https://datatracker.ietf.org/doc/html/rfc6749#section-3.2)
requires to be a `POST`; it targets the `login.<region>` host and never the API
host.

This is enforced in code and asserted by `tests/test_security.py`, which runs as
its own job in CI:

| Guarantee | Enforcement |
| --- | --- |
| No writes to Genesys | `GenesysClient` exposes only read methods; CI fails if more than one mutating call site exists in the package |
| Requests cannot leave the configured host | `_resolve()` rejects anything that is not HTTPS on `api.<region>` |
| A manipulated API response cannot redirect a fetch | `download()` enforces an allowlist of Genesys-owned hosts |
| The region cannot redirect traffic | `normalise_region()` requires a bare hostname |
| Credentials never leak | Sent only to the token endpoint, never logged, `.env` git-ignored, CI fails on a committed credential |
| Configuration text cannot become markup | Every value is HTML-escaped before any formatting is applied |
| Output paths cannot traverse | Flow names are reduced to `[a-z0-9-]` before use as filenames |

## Recommended OAuth client configuration

Create a **Client Credentials** OAuth client with a role holding only these
view permissions:

- `architect:flow:view`
- `architect:userPrompt:view`
- `architect:systemPrompt:view`
- `architect:schedule:view`, `architect:scheduleGroup:view`
- `telephony:plugin:all` (or `architect:ivr:view`)

Grant no write permission. The tool never needs one, and a missing read
permission degrades a section of the output rather than failing the run.

## Handling the output

**Generated documents contain real configuration** — phone numbers, queue names,
user names, prompt wording, integration names. `out/`, `*.pdf` and `.env` are
git-ignored so they are not committed by accident.

Before sharing a report outside your organisation, or committing one to a public
repository, review it the same way you would review an export of the Genesys org
itself.

## Reporting a vulnerability

Open a
[GitHub issue](https://github.com/Proguy2016/GenesysTask/issues) for
non-sensitive reports. For anything that would expose credentials or
customer data, contact the repository owner directly rather than filing a public
issue.
