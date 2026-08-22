# genesys-flow-doc

[![CI](https://github.com/Proguy2016/GenesysTask/actions/workflows/ci.yml/badge.svg)](https://github.com/Proguy2016/GenesysTask/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Read-only](https://img.shields.io/badge/Genesys%20API-read--only-0b6e62.svg)](SECURITY.md)

Reads Genesys Cloud Architect call flows through the Platform API and writes
documentation for two audiences: a plain-English business document and a full
technical specification.

**It is strictly read-only.** Every Platform API call is a `GET`. See
[Security](#security) for how that is enforced rather than merely intended.

---

## Contents

- [What it produces](#what-it-produces)
- [Setup](#setup)
- [Running it](#running-it)
- [Every API endpoint used, and why](#every-api-endpoint-used-and-why)
- [Security](#security)
- [How the code is organised](#how-the-code-is-organised)
- [How a run flows through the code](#how-a-run-flows-through-the-code)
- [How the parser works](#how-the-parser-works)
- [Validated against a real organisation](#validated-against-a-real-organisation)
- [Tests and CI](#tests-and-ci)
- [Licence](#licence)

---

## What it produces

| File | Audience | Contains |
| --- | --- | --- |
| `<flow>.business.html` | Operations, CX, QA, training, clients | What callers experience, menu options, where calls end up, every word spoken, what the flow relies on, points to confirm |
| `<flow>.technical.html` | Architect admins, developers | Every stage and action in execution order with its full configuration, variables, dependencies, audio inventory, coverage notes, provenance |
| *(both reports)* | | An inline SVG diagram per stage, drawn by the tool itself — no JavaScript, scales, prints |
| `<flow>.business.pdf` / `<flow>.technical.pdf` | Anyone | The same reports as PDF, rendered locally |
| `index.html` | Everyone | Contents page across a whole-organisation run |
| `<flow>.business.md` / `<flow>.technical.md` | Confluence, wikis, git diffs | The same content as Markdown |
| `<flow>.flow.mmd` | Developers | Mermaid source for the same graph, for pasting into GitHub or GitLab |
| `<flow>.raw.json` | Both | Unmodified flow configuration, so documents can be rebuilt with no API access |

The HTML reports are single self-contained files — inlined stylesheet, no build
step, no assets folder.

---

## Setup

```bash
pip install -r requirements.txt      # requests; anthropic only for the AI summary
cp .env.example .env                 # then fill in your OAuth client id and secret
```

PDF export uses a locally installed Google Chrome or Microsoft Edge. Nothing is
uploaded: the HTML is loaded over `file://` in a headless browser on your own
machine. If neither browser is present, `pip install playwright && playwright
install chromium` also works, and the PDF step is skipped rather than failing
the run.

### The OAuth client

Genesys Cloud → **Admin → Integrations → OAuth → Add Client**, grant type
**Client Credentials**. Give it a role with these **view-only** permissions:

| Permission | Needed for |
| --- | --- |
| `architect:flow:view` | Reading flows and their configuration |
| `architect:userPrompt:view` | Resolving `Prompt.x` references to the words callers hear |
| `architect:systemPrompt:view` | Resolving built-in Genesys prompts |
| `architect:schedule:view`, `architect:scheduleGroup:view` | Opening-hours detail |
| `telephony:plugin:all` *(or `architect:ivr:view`)* | Reading call route (IVR) entities |

Grant nothing else. The tool never needs a write permission, and a missing
*read* permission never stops a run — the affected item is reported as
unavailable and the documents are still produced.

---

## Running it

### Guided mode (the default)

Run with no arguments and it walks you through everything:

```bash
python -m genesys_flow_doc
```

```
  ┌────────────────────────────────────────────────────────────┐
  │  GENESYS CLOUD  ·  call flow documentation generator       │
  └────────────────────────────────────────────────────────────┘
  Read-only: this tool never modifies anything in Genesys Cloud.

What would you like to do?

  1  Document every call route in the organisation
  2  Document a single call route or flow
  3  Browse the organisation's call routes
  4  Rebuild documents from a saved configuration
  5  Convert existing HTML reports to PDF
  6  Quit
```

Choosing **a single call route or flow** then asks how to identify it — pick
from a fetched list of the organisation's call routes, paste a console URL,
or type an IVR or flow GUID — followed by which of its flows (all / open /
closed / holiday), which document formats, whether to produce PDFs, the output
directory, whether to resolve prompt wording, and whether to add an AI executive
summary. Everything has a default, and the whole run is summarised for
confirmation **before the first API call is made**.

Options 4 and 5 need no credentials and make no API calls at all.

### Scripted mode

Any flag switches off the menus, so the tool is safe in CI and scheduled jobs:

```bash
# Every call route in the organisation, with a contents page and PDFs
python -m genesys_flow_doc --all-ivrs --pdf

# Straight from the browser URL — the region is read from the host
python -m genesys_flow_doc "https://apps.mypurecloud.ie/directory/#/admin/routing/ivrs/<guid>"

# By ID
python -m genesys_flow_doc --ivr <guid> --region mypurecloud.ie
python -m genesys_flow_doc --flow <guid> --only open

# Just list what is there
python -m genesys_flow_doc --list

# Rebuild documents from a saved configuration — no API calls, no credentials
python -m genesys_flow_doc --offline out/lab-ivr-flow.raw.json
```

| Flag | Effect |
| --- | --- |
| `--all-ivrs` | Document every call route in the organisation |
| `--ivr <guid>` / `--flow <guid>` / `<url>` | Document one call route or flow |
| `--list` | Print the call routes and their flows, then exit |
| `--only open\|closed\|holiday` | For a call route, document just one of its flows |
| `--offline <file>` | Rebuild documents from a saved `.raw.json` |
| `--format html\|md\|both` | Which documents to write (default `both`) |
| `--pdf` | Also render each HTML report to PDF |
| `--out DIR` | Output directory (default `./out`) |
| `--region <domain>` | e.g. `mypurecloud.ie`; defaults to `$GENESYS_REGION` |
| `--no-resolve` | Skip prompt-wording and schedule lookups (fewer API calls) |
| `--narrate` | Add a Claude-written executive summary to the business document |
| `-i` / `--interactive` | Force the guided menu |
| `-v` | Detailed progress |

### Which console URLs are accepted

Paste any of these; the region is read from the host and the right ID is picked
out of the path:

| URL shape | Treated as |
| --- | --- |
| `/directory/#/admin/routing/ivrs/<id>` | a call route |
| `/architect/#/inboundcall/flows/<id>/latest` | a flow |
| `/architect/#/inboundcall/flows/<id>/latest/menu/<nodeId>` | a flow (the node ID is ignored) |
| `/architect/#/workflow/flows/<id>/...` | a flow |

The ID is taken from the segment that follows `ivrs/` or `flows/`, not from the
end of the URL — an Architect deep-link appends the GUID of whichever menu, task
or state is open in the editor, and that is not the flow.

### A call-route URL is not the same as a flow URL

`/admin/routing/ivrs/<id>` is an IVR entity: phone numbers, a schedule group,
and up to three flows (open hours, closed hours, holiday hours). Given that URL
the tool documents **every flow the call route uses**, stamping each with the
route's numbers, schedule and sibling flows. A flow shared by several routes is
documented once per run.

---

## Every API endpoint used, and why

Ten endpoints in total. **Nine are `GET`** against the Platform API. The tenth
is the OAuth token exchange, which is a `POST` because
[RFC 6749 §3.2](https://datatracker.ietf.org/doc/html/rfc6749#section-3.2)
requires the token endpoint to be one; it goes to the **login** host, never the
API host. There are no PUT, PATCH or DELETE calls anywhere in the tool.

| # | Method & endpoint | What it returns | Why it is called | Called from |
| --- | --- | --- | --- | --- |
| 1 | `POST https://login.<region>/oauth/token` | A bearer token, valid ~24h | The client-credentials grant. Sends the client id and secret as HTTP Basic and `grant_type=client_credentials`. The only non-GET request in the tool, and the only place credentials are ever sent. | `client.GenesysClient._authenticate` |
| 2 | `GET /api/v2/architect/ivrs` | Paged list of every call route | Powers `--list`, `--all-ivrs` and the interactive "pick from a list" browser. Each entry already carries its DNIS numbers, schedule group and flow references, so no follow-up call is needed per route. | `fetch.list_ivrs` |
| 3 | `GET /api/v2/architect/ivrs/{ivrId}` | One call route | Resolves a single IVR given by URL, `--ivr`, or the interactive picker. Supplies the phone numbers callers dial, the schedule group, and the open/closed/holiday flow IDs that become the run's work list. | `fetch.fetch_ivr` |
| 4 | `GET /api/v2/flows/{flowId}` | Flow metadata | Name, type, description, division and published version — the identity block at the top of both documents. Kept separate from the configuration because the configuration payload does not carry the division or the published version. | `fetch.fetch_flow` |
| 5 | `GET /api/v2/flows/{flowId}/latestconfiguration` | The full published flow definition | **The core call.** Returns the action graph — every stage, action, branch, expression, audio expression, variable and the dependency manifest. Everything in the node-by-node specification comes from here. Saved verbatim as `<flow>.raw.json`. | `fetch.fetch_flow` |
| 6 | `GET /api/v2/architect/prompts` | Paged list of user prompts with their resources | Turns a `Prompt.mainGreeting` reference into the words the caller actually hears. Fetched **once per run** and indexed by name, not once per flow. Skipped entirely under `--no-resolve`. | `fetch.PromptResolver.user` |
| 7 | `GET /api/v2/architect/systemprompts?name=<name>` | The built-in prompt matching a name | Same purpose for Genesys' own prompts (`PromptSystem.voicemail_greeting` and friends). Queried lazily, only for prompts a flow actually references, and cached for the run. | `fetch.PromptResolver.system` |
| 8 | `GET /api/v2/architect/systemprompts/{promptId}/resources` | Per-language text and audio for a system prompt | The listing in #7 does not include resource text, so the wording needs this second call. Only reached for prompts a flow references. | `fetch.PromptResolver.system` |
| 9 | `GET /api/v2/architect/schedulegroups/{scheduleGroupId}` | Which schedules a call route treats as open, closed and holiday | The first half of the "when this flow runs" section. Cached per schedule group across a run, since routes commonly share one. | `fetch.summarise_schedule_group` |
| 10 | `GET /api/v2/architect/schedules/{scheduleId}` | One schedule's start, end and recurrence rule | The second half — the actual opening times behind each schedule named in #9. | `fetch.summarise_schedule_group` |

One conditional extra: if `/latestconfiguration` ever returns a pointer
(`configurationUri`) instead of the configuration itself, `client.download()`
issues a plain `GET` to that pre-signed URL. It is still a read, it carries no
credentials, and the URL is checked against a Genesys-owned host allowlist
first.

**Endpoints deliberately *not* called.** Queue, user, group, skill, data-action,
data-table, bot-flow and script names all arrive inside the flow configuration's
own `manifest` (#5), complete with names and IDs. Resolving them individually
would mean hundreds of extra requests for information already in hand, so the
per-GUID lookups were removed.

**Rate limiting.** `client.GenesysClient.get` retries `408`, `429`, `500`,
`502`, `503` and `504`, honouring the `Retry-After` header and otherwise backing
off exponentially, up to five attempts. A `401` triggers exactly one silent
re-authentication.

---

## Security

The tool's entire job is to read a configuration and write files locally. The
following properties are enforced in code and asserted by `tests/test_security.py`,
so a later change cannot quietly weaken them.

| Property | How it is enforced | Test |
| --- | --- | --- |
| **No writes to Genesys** | `GenesysClient` exposes only `get`, `get_optional`, `paged` and `download`. There is no method that can issue a PUT, POST, PATCH or DELETE against the API. | A test greps every source file for `.post(`/`.put(`/`.patch(`/`.delete(` and fails unless there is exactly one hit — the OAuth token exchange — and that it targets `login_base`, not `api_base`. |
| **Requests cannot leave the configured host** | `_resolve()` rejects any URL that is not HTTPS on `api.<region>`, including another Genesys region. | Four tests covering another host, another region, plain HTTP, and the normal case. |
| **A manipulated API response cannot redirect a fetch** | `download()` (used for pre-signed configuration URLs) accepts only HTTPS on an allowlist of Genesys-owned and AWS hostnames. | Rejection tests for an arbitrary host, plain HTTP and `file://`. |
| **The region cannot be used to redirect traffic** | The region is concatenated into every request URL, so `normalise_region()` requires it to look like a bare hostname. Anything with a slash, port, userinfo or whitespace is rejected outright rather than "cleaned up". | Accepts the four normal spellings; rejects seven malformed ones. |
| **Credentials never leak** | The client id and secret are read from the environment, held in memory, and sent only to the token endpoint. No log statement touches them or the bearer token. `.env` is git-ignored. | A test asserts no logging line in `client.py` mentions a secret or token, and that no other module references `client_secret`. |
| **Untrusted configuration text cannot become markup** | Queue names, phone numbers, conditions and prompt text are attacker-influenced input. Every value is HTML-escaped *first*, and only then are the `**bold**` markers turned into tags. | A hostile `<img src=x onerror=...>` queue name is pushed through both HTML renderers, and a `</title><script>` flow name through the page title. |
| **Output paths cannot escape the output directory** | `slugify()` reduces a flow name to `[a-z0-9-]` before it is used as a filename. | Traversal attempts (`../../etc/passwd`, `..\\..\\windows`, `C:\\evil`) all reduce to a safe slug. |

Two further notes:

- **The generated documents contain real configuration** — phone numbers, queue
  names, prompt wording, integration names. `out/`, `artifact/` and `*.pdf` are
  git-ignored for that reason. Treat the reports with the same care as the
  Genesys org itself.
- **PDF rendering is entirely local.** The headless browser opens a `file://`
  URL. The only outbound request a report makes is the Google Fonts stylesheet
  it links, and with no network the report falls back to local fonts and still
  renders.

---

## How the code is organised

```
genesys_flow_doc/
  __main__.py          entry point for `python -m genesys_flow_doc`
  cli.py               flag parsing, the run pipeline, file writing
  interactive.py       the guided menu; builds the same args the flags produce
  prompt.py            terminal prompt helpers (menus, pickers, encoding safety)
  config.py            region handling, .env loading, console-URL parsing
  client.py            read-only HTTP client: auth, retries, paging, host checks
  fetch.py             call route -> flows, prompt wording, schedule summaries
  parse.py             Architect action graph -> normalised model
  model.py             FlowDoc / Container / Node / Branch / Speech dataclasses
  speech.py            extracts spoken words from Architect audio expressions
  taxonomy.py          plain-English meaning of each Architect action type
  theme.py             the report stylesheet (light + dark, print rules)
  render_html.py       business, technical and index HTML
  render_business.py   business Markdown, and the shared `describe()` sentences
  render_technical.py  technical Markdown
  diagram.py           lays out and draws the inline SVG flow diagrams
  mermaid.py           Mermaid source for the same graph
  narrate.py           optional Claude-written executive summary
  pdf.py               HTML -> PDF via a local headless browser
samples/example-flow.json   synthetic flow in the real Architect schema
tests/test_parse.py         25 tests over that sample
tests/test_security.py      16 tests asserting the guarantees above
tools/validate.py           coverage report over a directory of raw configs
```

### What each module is responsible for

- **`cli.py`** owns the pipeline. `main()` decides between guided and scripted
  mode; `run()` turns arguments into a work list; `generate()` executes it;
  `write_outputs()` writes one flow's files; `write_index()` writes the contents
  page; `_maybe_pdf()` handles `--pdf`.
- **`interactive.py`** only *collects answers*. It builds an
  `argparse.Namespace` identical in shape to the one the flag parser produces
  and hands it to `cli.run()`, so the two front ends cannot drift apart.
- **`client.py`** is the only module that touches the network, and the only one
  that sees credentials.
- **`fetch.py`** knows which endpoints answer which question. It holds no
  parsing logic.
- **`parse.py`** knows Architect's JSON shape. It makes no network calls, so it
  runs offline against a saved `.raw.json`.
- **`taxonomy.py`** is the vocabulary — the one file to extend when Genesys adds
  an action type.
- **`render_*.py`**, **`diagram.py`** and **`theme.py`** know nothing about
  Genesys; they render the normalised model.
- **`pdf.py`** shells out to a local headless browser. It opens every
  `<details>` in a temporary copy first, so a printed technical specification
  keeps the configuration tables that are collapsed on screen.

---

## How a run flows through the code

```
python -m genesys_flow_doc [args]
        │
        ▼
cli.main()  ── no args or -i ─▶ interactive.session()   asks the questions,
        │                              │                returns an args Namespace
        │◀─────────────────────────────┘
        ▼
cli.run(args)
        │
        ├─ --offline ─▶ parse.parse_flow(saved json) ────────────┐   (no network)
        │                                                        │
        ├─ --list / --all-ivrs ─▶ client.GenesysClient           │
        │        └─ fetch.list_ivrs()          GET /architect/ivrs
        │                 └─ cli.jobs_for_ivr()  one job per (role, flow)
        │                                                        │
        └─ url / --ivr / --flow ─▶ config.parse_console_url()    │
                 └─ fetch.fetch_ivr()          GET /architect/ivrs/{id}
                          └─ cli.jobs_for_ivr()                  │
                                                                 │
                              ▼                                  │
                    cli.generate(client, jobs, args)             │
                              │                                  │
        for each job ─────────┤                                  │
                              ├─ fetch.fetch_flow()   GET /flows/{id}
                              │                       GET /flows/{id}/latestconfiguration
                              ├─ parse.parse_flow()   graph walk -> FlowDoc
                              │      ├─ speech.from_audio_value()   what is spoken
                              │      ├─ taxonomy.label_for()        what each step means
                              │      └─ parse.manifest_references() dependencies
                              ├─ fetch.enrich()       prompt wording, opening hours
                              │                       (shared caches across the run)
                              └─ cli.write_outputs() ◀────────────┘
                                     ├─ render_html.render_business()   .business.html
                                     ├─ render_html.render_technical()  .technical.html
                                     ├─ render_business.render()        .business.md
                                     ├─ render_technical.render()       .technical.md
                                     ├─ diagram.render_stage()  inline SVG, in both
                                     ├─ mermaid.render()                .flow.mmd
                                     └─ json.dumps(doc.raw)             .raw.json
                              │
                    cli.write_index()   index.html across the run
                    cli._maybe_pdf()    pdf.html_to_pdf() per report
```

The important property: **everything after `parse.parse_flow()` is pure.** The
model, the renderers and the PDF step never touch the network, which is why
`--offline` can rebuild every document from a saved `.raw.json` with no
credentials at all.

---

## How the parser works

A published flow is a **graph**, not a tree:

```
flowSequenceItemList[]        the stages
  Task:  startAction, actionList[], paths[]
  Menu:  menuChoiceList[], prompts, defaultMenuChoice

action: { __type, id, name, trackingId,
          nextAction: <id>,                  sequential successor
          paths: [{nextActionId, label}],    labelled branches
          <property>: {config, text, type} } a value object
```

`parse.py` walks that graph from each stage's start action into an ordered tree.
Because flows contain loops and shared error handlers, a repeat visit is
recorded as a jump rather than expanded again, so every action is documented
exactly once — and anything in a stage the start action cannot reach is flagged
**unreachable** rather than quietly dropped.

Value objects carry a `text` field holding the human-readable expression, so
queue names, phone numbers and conditions come through directly. Spoken content
comes from `uiMetaData.sequenceItems`, Architect's own structured breakdown of
each audio expression, which distinguishes literal text-to-speech from prompt
references, values read aloud, runtime expressions and pauses; the raw
expression is parsed as a fallback when that breakdown is absent.

**The one caveat.** Architect's configuration schema is not published and grows
with each release. An action type the generator has not seen is still documented
in full from its raw configuration; only its one-line plain-English description
falls back to a prettified type name, and every such type is listed under
*Coverage and provenance* in the technical document. Extend `taxonomy.py` to
improve the wording.

---

## Validated against a real organisation

Run across all **60 call routes** in an ie-region organisation:

| | |
| --- | --- |
| Flows documented | 57 (three routes share flows with others) |
| Stages parsed | 169 tasks and menus |
| Actions parsed | 722 |
| Action types recognised | **722 / 722 (100%)** across 40 distinct types |
| Caller-facing audio extracted | 197 pieces |
| Failures | 0 |
| HTML reports generated | 115, all structurally valid |

`python tools/validate.py out` re-runs that check over any output directory and
reports unrecognised action types, unreachable steps and parse anomalies.

---

## Tests and CI

```bash
python -m unittest discover -s tests    # 45 tests, all offline
python tools/validate.py out            # parser coverage over real configs
```

No credentials are needed: the whole suite runs against
`samples/example-flow.json`, a synthetic flow written in the real Architect
schema, so it exercises the same code paths a live flow does.

[GitHub Actions](.github/workflows/ci.yml) runs three jobs on every push:

| Job | What it checks |
| --- | --- |
| `tests` | The suite on Linux and Windows, Python 3.10 and 3.13, then rebuilds the sample documents and runs the coverage report. The generated documents are uploaded as a build artifact. |
| `read-only guarantees` | `tests/test_security.py` on its own, plus a grep that fails the build if more than one mutating HTTP call site exists in the package. |
| `no committed credentials` | Fails if a `.env` file is tracked or a credential-shaped value is committed. |

## Licence

[MIT](LICENSE). See [SECURITY.md](SECURITY.md) for the read-only guarantees and
for guidance on handling generated reports, which contain real configuration.

`tests/test_parse.py` runs against `samples/example-flow.json`, a synthetic flow
written in the real Architect schema, so it exercises the same code paths a live
flow does. `tests/test_security.py` asserts the guarantees in
[Security](#security) against the source itself.
