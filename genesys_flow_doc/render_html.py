"""Client-ready HTML reports -- one self-contained file per document.

Two audiences, two documents, one visual language:

  business.html   what callers experience, in plain English
  technical.html  every step with its full Architect configuration

Each page is a single file with the stylesheet inlined, so it can be emailed,
opened offline, or printed straight to PDF.
"""

from __future__ import annotations

import html
import re
from typing import Iterable

from . import diagram, taxonomy
from .model import Container, FlowDoc, Node, Speech
from .render_business import describe
from .speech import dedupe
from .theme import CSS, FONTS

CATEGORY_LABEL = {
    "audio": "Audio",
    "input": "Caller input",
    "logic": "Logic",
    "routing": "Routing",
    "data": "Data",
    "bot": "Bot",
    "terminal": "Ends call",
    "container": "Stage",
    "other": "Step",
}


def e(text: object) -> str:
    """Escape for HTML text content."""
    return html.escape("" if text is None else str(text), quote=True)


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_TICK = re.compile(r"`(.+?)`")


def phrase(text: str) -> str:
    """Escape a plain-English sentence, then render its ** ** and ` ` markers.

    `describe()` returns light Markdown containing values taken straight from
    the flow configuration (queue names, phone numbers, conditions). Escaping
    first and adding markup second means a queue called `<script>` is shown as
    text and can never become markup.
    """
    safe = e(text)
    safe = _BOLD.sub(r"<strong>\1</strong>", safe)
    safe = _TICK.sub(r"<code>\1</code>", safe)
    return safe


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "section"


def _cat(kind: str) -> str:
    return taxonomy.category_for(kind)


def _tint(kind: str) -> str:
    return f"--cat: var(--cat-{_cat(kind)})"


# --------------------------------------------------------------------------
# page shell
# --------------------------------------------------------------------------

#: When true, pages are emitted without the outer html/head/body skeleton, for
#: hosts that supply their own (such as publishing the report as a web page).
FRAGMENT = False


def _document(title: str, body: str) -> str:
    head = f"<title>{e(title)}</title>\n{FONTS}\n<style>{CSS}</style>"
    if FRAGMENT:
        return f"{head}\n{body}\n"
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{head}\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def _masthead(kicker: str, heading: str, subtitle: str, meta: Iterable[str]) -> str:
    meta_html = "".join(f"<span>{m}</span>" for m in meta if m)
    return f"""<header class="masthead">
  <div class="masthead__kicker"><span class="masthead__rule"></span><span class="eyebrow">{e(kicker)}</span></div>
  <h1>{e(heading)}</h1>
  <p class="masthead__sub">{subtitle}</p>
  <div class="masthead__meta">{meta_html}</div>
</header>"""


def _rail(sections: list[tuple[str, str]]) -> str:
    items = "".join(f'<li><a href="#{_slug(anchor)}">{e(label)}</a></li>'
                    for anchor, label in sections)
    return (f'<nav class="rail" aria-label="Contents">'
            f'<div class="eyebrow rail__title">Contents</div><ol>{items}</ol></nav>')


def _panel(anchor: str, title: str, body: str, intro: str = "") -> str:
    intro_html = f'<p class="panel__intro">{intro}</p>' if intro else ""
    return (f'<section class="panel" id="{_slug(anchor)}">'
            f"<h2>{e(title)}</h2>{intro_html}{body}</section>")


def _facts(entries: list[tuple[str, str, bool]]) -> str:
    cards = []
    for label, value, small in entries:
        cls = "fact__value fact__value--sm" if small else "fact__value"
        cards.append(f'<div class="fact"><span class="eyebrow">{e(label)}</span>'
                     f'<span class="{cls}">{value}</span></div>')
    return f'<div class="facts">{"".join(cards)}</div>'


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
                   for row in rows)
    return (f'<div class="scroller"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>")


def _chipset(groups: dict[str, list[str]], accent: set[str] = frozenset()) -> str:
    rows = []
    for label, values in groups.items():
        chips = "".join(
            f'<span class="chip{" chip--accent" if label in accent else ""}">{e(v)}</span>'
            for v in values)
        rows.append(f'<div class="chipset__row"><span class="chipset__label">{e(label)}</span>'
                    f"<span>{chips}</span></div>")
    return f'<div class="chipset">{"".join(rows)}</div>'


def _footer(doc: FlowDoc, note: str) -> str:
    return (f'<footer class="footer"><span>{e(doc.name)}</span>'
            f'<span>Flow ID <code>{e(doc.flow_id or "n/a")}</code></span>'
            f"<span>{e(doc.fetched_at or 'date unknown')}</span>"
            f'<span class="footer__hint">{e(note)}</span></footer>')


# --------------------------------------------------------------------------
# spoken content
# --------------------------------------------------------------------------

def _say(item: Speech) -> str:
    if item.resolved:
        return (f'<blockquote class="say"><span class="say__src">'
                f'{"Recorded prompt " + e(item.value) if item.kind != "tts" else "Spoken"}'
                f"</span>{e(item.resolved)}</blockquote>")
    if item.kind == "tts":
        return f'<blockquote class="say"><span class="say__src">Spoken</span>{e(item.value)}</blockquote>'
    if item.kind == "prompt":
        return (f'<blockquote class="say say--muted"><span class="say__src">Recorded prompt</span>'
                f"{e(item.value)} — wording is not stored as text; listen to it in Architect."
                f"</blockquote>")
    if item.kind == "system-prompt":
        return (f'<blockquote class="say say--muted"><span class="say__src">Built-in prompt</span>'
                f"{e(item.value)}</blockquote>")
    return (f'<blockquote class="say say--muted"><span class="say__src">'
            f'{"Silence" if item.kind == "pause" else "Chosen at runtime"}</span>'
            f'{e(item.value.strip("()"))}</blockquote>')


# --------------------------------------------------------------------------
# the journey track
# --------------------------------------------------------------------------

def _step(node: Node, number: str, names: dict[str, str], technical: bool) -> str:
    category = _cat(node.kind)
    marker = (f'<span class="dtmf step__dtmf{" dtmf--wide" if len(node.dtmf) > 2 else ""}">'
              f"{e(node.dtmf)}</span>") if node.dtmf else '<span class="step__dot"></span>'

    parts = [f'<div class="step__head">'
             f'<span class="step__no">{e(number)}</span>'
             f"<h4>{e(node.name)}</h4>"
             f'<span class="tag">{e(taxonomy.label_for(node.kind))}</span>'
             f"</div>"]
    parts.append(f'<p class="step__what">{phrase(describe(node, names))}</p>')

    if node.unreachable:
        parts.append('<p class="note note--flag">Configured but not reachable from the start '
                     "of this stage — dead configuration unless something jumps to it.</p>")

    for item in dedupe(node.speech):
        parts.append(_say(item))

    for jump in node.jumps:
        parts.append(f'<span class="jump">→ continues at <code>{e(jump)}</code></span>')

    if technical:
        parts.append(_config_table(node))

    for branch in node.branches:
        children = "".join(
            _step(child, f"{number}.{index}", names, technical)
            for index, child in enumerate(branch.nodes, start=1))
        label = f"If the caller presses {node.dtmf}" if node.dtmf else branch.label
        parts.append(f'<div class="branch"><div class="branch__label">{e(label)}</div>'
                     f'<div class="track">{children}</div></div>')

    css_class = "step step--dtmf" if node.dtmf else "step"
    return (f'<div class="{css_class}" style="{_tint(node.kind)}">{marker}'
            f'<div class="step__body">{"".join(parts)}</div></div>')


def _config_table(node: Node) -> str:
    if not node.props:
        return ""
    rows = [[f"<code>{e(path)}</code>", f"<code>{e(value)}</code>"] for path, value in node.props]
    identity = []
    if node.tracking_id:
        identity.append(f"tracking ID {node.tracking_id}")
    identity.append(node.kind)
    summary = f"Configuration — {', '.join(identity)}"
    return (f"<details><summary>{e(summary)}</summary>"
            f"{_table(['Property', 'Value'], rows)}</details>")


def _stage(container: Container, index: int, names: dict[str, str], technical: bool) -> str:
    tags = []
    if container.is_start:
        tags.append('<span class="chip chip--accent">Entry point</span>')
    tags.append(f'<span class="chip">{e(taxonomy.label_for(container.kind))}</span>')
    total = sum(1 for _ in container.walk())
    tags.append(f'<span class="chip">{total} step{"s" if total != 1 else ""}</span>')

    head = (f'<div class="stage__head"><h3 id="{_slug("stage-" + container.name)}">'
            f"{e(container.name)}</h3>{''.join(tags)}</div>")

    body = [_say(item) for item in dedupe(container.speech)]
    if not container.nodes:
        body.append('<p class="step__what">No steps are configured in this stage.</p>')
    body.append('<div class="track">' + "".join(
        _step(node, f"{index}.{i}", names, technical)
        for i, node in enumerate(container.nodes, start=1)) + "</div>")

    return f'<article class="stage">{head}<div class="stage__body">{"".join(body)}</div></article>'


# --------------------------------------------------------------------------
# shared sections
# --------------------------------------------------------------------------

def _menu_rows(doc: FlowDoc) -> list[list[str]]:
    collected: list[tuple[str, str, list[str]]] = []
    for container in doc.containers:
        for node in container.walk():
            if not node.dtmf:
                continue
            wide = " dtmf--wide" if len(node.dtmf) > 2 else ""
            collected.append((container.name, node.dtmf, [
                f'<span class="dtmf{wide}">{e(node.dtmf)}</span>',
                e(container.name),
                e(node.name),
                phrase(describe(node, doc.name_by_id)),
            ]))
    # Group by menu, then by keypad digit, with non-digit choices last.
    collected.sort(key=lambda item: (item[0].lower(), not item[1].isdigit(), item[1]))
    return [row for _, _, row in collected]


def _endpoints(doc: FlowDoc) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for node in doc.all_nodes():
        if _cat(node.kind) in ("routing", "terminal"):
            seen.setdefault(describe(node, doc.name_by_id), node.kind)
    return list(seen.items())


LEGEND = [
    ("audio", "Audio played"),
    ("input", "Caller input"),
    ("logic", "Decision"),
    ("data", "Data / lookup"),
    ("bot", "Automated assistant"),
    ("routing", "Transfer out"),
    ("terminal", "Ends the call"),
]


def _diagrams(doc: FlowDoc) -> str:
    """One SVG per stage, plus a colour legend."""
    panels = []
    for container in doc.containers:
        svg = diagram.render_stage(container)
        if not svg:
            continue
        entry = "  ·  entry point" if container.is_start else ""
        panels.append(
            f'<figure class="diagram">'
            f'<figcaption class="diagram__caption">{e(container.name)}{entry}</figcaption>'
            f"{svg}</figure>"
        )
    if not panels:
        return ""
    legend = "".join(
        f'<span style="--cat: var(--cat-{key})"><i></i>{e(label)}</span>'
        for key, label in LEGEND)
    return f'<div class="legend">{legend}</div>' + "".join(panels)


def _script_lines(doc: FlowDoc) -> list[Speech]:
    return [s for s in dedupe(doc.all_speech()) if s.resolved or s.kind in ("tts", "text")]


def _open_questions(doc: FlowDoc) -> list[str]:
    checks: list[str] = []
    unresolved = sorted({s.value for s in doc.all_speech()
                         if s.kind in ("prompt", "system-prompt") and not s.resolved})
    if unresolved:
        checks.append("Confirm the wording of these prompts by listening to them in Architect, "
                      "because they are recorded audio with no stored text: "
                      + ", ".join(f"<code>{e(n)}</code>" for n in unresolved) + ".")
    orphans = [n.name for n in doc.all_nodes() if n.unreachable]
    if orphans:
        checks.append(f"{len(orphans)} step(s) are configured but cannot be reached "
                      f"({', '.join(e(o) for o in orphans[:6])}). Confirm whether they are "
                      "leftovers that should be removed.")
    if doc.unmapped_kinds:
        checks.append("Some steps use newer Architect features this summary describes only "
                      "generically — see the coverage notes in the technical specification.")
    if doc.ivr and not doc.dnis:
        checks.append("No phone numbers are attached to this call route, so nothing reaches "
                      "this flow by dialling in.")
    return checks


# --------------------------------------------------------------------------
# business document
# --------------------------------------------------------------------------

def render_business(doc: FlowDoc) -> str:
    names = doc.name_by_id
    steps = sum(1 for _ in doc.all_nodes())
    queues = doc.references.get("Queues", [])
    script = _script_lines(doc)

    sections = [("overview", "Overview"), ("destinations", "Where calls end up")]
    blocks = []

    # --- overview
    facts = [
        ("Numbers callers dial", "<br>".join(e(d) for d in doc.dnis) or "None attached", True),
        ("Stages", str(len(doc.containers)), False),
        ("Steps", str(steps), False),
        ("Queues used", str(len(queues)) if queues else "None", False),
        ("Language", e(doc.default_language or "Not set"), True),
    ]
    overview = [_facts(facts)]

    rows = []
    if doc.ivr:
        rows.append(["Call route", e(doc.ivr.get("name"))])
    for role, target in doc.sibling_flows.items():
        rows.append([e(role), e(re.sub(r"\s*\(`[^`]+`\)", "", target))])
    if doc.description:
        rows.append(["Purpose", e(doc.description)])
    if doc.schedule_summary:
        detail = "<br>".join(e(re.sub(r"[*_`]", "", line).lstrip("- "))
                             for line in doc.schedule_summary)
        rows.append(["Opening hours", detail])
    if rows:
        overview.append(_table(["", ""], rows))
    blocks.append(_panel("overview", "Overview", "".join(overview)))

    # --- destinations
    endpoints = _endpoints(doc)
    if endpoints:
        items = "".join(
            f'<li style="{_tint(kind)}"><span class="tag">'
            f'{e(CATEGORY_LABEL.get(_cat(kind), "Step"))}</span>'
            f"<span>{phrase(text)}</span></li>"
            for text, kind in endpoints)
        dest = f'<ul class="outcomes">{items}</ul>' 
    else:
        dest = '<p class="note">This flow neither transfers nor ends calls directly.</p>'
    blocks.append(_panel("destinations", "Where calls end up", dest,
                         "Every way a call can leave this flow."))

    # --- menu options
    menu_rows = _menu_rows(doc)
    if menu_rows:
        sections.append(("menu-options", "Menu options"))
        blocks.append(_panel("menu-options", "Menu options offered to callers",
                             _table(["Press", "Menu", "Option", "What happens"], menu_rows)))

    # --- diagram
    diagrams = _diagrams(doc)
    if diagrams:
        sections.append(("diagram", "Flow diagram"))
        blocks.append(_panel("diagram", "Flow diagram", diagrams,
                             "One picture per stage. Colour shows what kind of step it is; "
                             "labelled arrows are the alternative paths a call can take."))

    # --- journey
    sections.append(("journey", "Caller journey"))
    stages = "".join(_stage(c, i, names, technical=False)
                     for i, c in enumerate(doc.containers, start=1))
    blocks.append(_panel("journey", "The caller's journey, step by step", stages,
                         "Stages run in the order shown. Indented tracks are the alternative "
                         "paths a call can take."))

    # --- script
    if script:
        sections.append(("script", "What callers hear"))
        lines = "".join(
            f'<div class="script__line"><span class="script__no">{i:02d}</span>'
            f'<p class="script__text">“{e(s.resolved or s.value)}”</p></div>'
            for i, s in enumerate(script, start=1))
        blocks.append(_panel("script", "Everything the caller hears, word for word",
                             f'<div class="script">{lines}</div>',
                             "Use this to review wording, tone and translations. Each line is "
                             "exactly what is played or spoken."))

    # --- dependencies
    business_labels = ("Queues", "Users", "Groups", "Skills", "Data actions", "Data tables",
                       "Bot flows", "In-queue flows", "Survey flows", "Agent scripts",
                       "Schedules", "Schedule groups", "Wrap-up codes", "Recorded prompts")
    deps = {k: v for k, v in doc.references.items() if k in business_labels}
    if deps:
        sections.append(("depends-on", "What it relies on"))
        blocks.append(_panel("depends-on", "What this flow relies on",
                             _chipset(deps, accent={"Queues"}),
                             "If any of these are renamed, moved or switched off, this flow "
                             "is affected."))

    # --- open questions
    checks = _open_questions(doc)
    sections.append(("questions", "Points to confirm"))
    if checks:
        body = ('<ul class="checklist">'
                + "".join(f"<li><span>{c}</span></li>" for c in checks) + "</ul>")
    else:
        body = ('<p class="note note--ok">Nothing outstanding — every step, prompt and '
                "destination in this flow was resolved.</p>")
    blocks.append(_panel("questions", "Points to confirm with the flow owner", body))

    subtitle = e(doc.description or "Inbound call flow")
    meta = [f"Generated {e(doc.fetched_at or 'date unknown')}",
            f"{len(doc.containers)} stages", f"{steps} steps"]
    if doc.dnis:
        meta.insert(1, "Dialled on " + e(", ".join(doc.dnis)))

    body = (f'<div class="page">'
            f'{_masthead("Business overview", doc.name, subtitle, meta)}'
            f'<div class="layout">{_rail(sections)}'
            f'<main class="stack">{"".join(blocks)}'
            f'{_footer(doc, "Generated from the live Genesys Cloud configuration.")}'
            f"</main></div></div>")
    return _document(f"{doc.name} — Call Flow", body)


# --------------------------------------------------------------------------
# technical document
# --------------------------------------------------------------------------

def render_technical(doc: FlowDoc, mermaid_source: str = "") -> str:
    names = doc.name_by_id
    steps = sum(1 for _ in doc.all_nodes())
    sections = [("identity", "Flow identity"), ("stages", "Stage index")]
    blocks = []

    # --- identity
    rows = [
        ["Flow name", e(doc.name)],
        ["Flow ID", f"<code>{e(doc.flow_id or 'n/a')}</code>"],
        ["Flow type", e(doc.flow_type)],
        ["Division", e(doc.division or "—")],
        ["Published version", e(doc.published_version or "—")],
        ["Default language", e(doc.default_language or "—")],
        ["Supported languages", e(", ".join(doc.supported_languages) or "—")],
        ["Entry point", f"<code>{e(doc.start_ref or '—')}</code>"],
    ]
    if doc.ivr:
        rows.append(["Call route", f"{e(doc.ivr.get('name'))} "
                                   f"<code>{e(doc.ivr.get('id'))}</code>"])
        rows.append(["Numbers (DNIS)", e(", ".join(doc.dnis) or "none")])
        for role, target in doc.sibling_flows.items():
            rows.append([e(role), e(re.sub(r"[`]", "", target))])
    identity = _facts([
        ("Stages", str(len(doc.containers)), False),
        ("Actions", str(steps), False),
        ("Variables", str(len(doc.variables)), False),
        ("Action types", str(len({n.kind for n in doc.all_nodes()})), False),
    ]) + _table(["Field", "Value"], rows)
    blocks.append(_panel("identity", "Flow identity", identity))

    # --- stage index
    index_rows = []
    for i, container in enumerate(doc.containers, start=1):
        total = sum(1 for _ in container.walk())
        index_rows.append([
            f'<a href="#{_slug("stage-" + container.name)}">{e(container.name)}</a>',
            e(taxonomy.label_for(container.kind)),
            '<span class="chip chip--accent">entry</span>' if container.is_start else "—",
            f'<span class="num">{total}</span>',
            f"<code>{e(container.ref or '')}</code>",
        ])
    blocks.append(_panel("stages", "Stage index",
                         _table(["Stage", "Type", "", "Actions", "Identifier"], index_rows)))

    # --- variables
    if doc.variables:
        sections.append(("variables", "Variables"))
        var_rows = [[f"<code>{e(v['name'])}</code>", e(v["type"]), e(v.get("scope") or "—"),
                     f"<code>{e(v['initial'])}</code>" if v["initial"] else "—",
                     "yes" if v["input"] else "—", "yes" if v["output"] else "—"]
                    for v in doc.variables]
        blocks.append(_panel("variables", "Variables",
                             _table(["Name", "Type", "Scope", "Initial", "In", "Out"], var_rows)))

    # --- specification
    sections.append(("specification", "Node specification"))
    stages = "".join(_stage(c, i, names, technical=True)
                     for i, c in enumerate(doc.containers, start=1))
    blocks.append(_panel("specification", "Node-by-node specification", stages,
                         "Every action in execution order. Expand any step to see its full "
                         "configuration exactly as stored in Architect."))

    # --- dependencies
    if doc.references:
        sections.append(("dependencies", "Dependencies"))
        blocks.append(_panel("dependencies", "External dependencies",
                             _chipset(doc.references),
                             "Taken from the flow's own manifest, so this is everything "
                             "Architect records the flow as depending on."))

    # --- audio inventory
    speech = dedupe(doc.all_speech())
    if speech:
        sections.append(("audio", "Audio inventory"))
        audio_rows = []
        for item in speech:
            source = {"tts": "Inline text-to-speech",
                      "prompt": f"User prompt <code>{e(item.value)}</code>",
                      "system-prompt": f"System prompt <code>{e(item.value)}</code>",
                      "dynamic": "Runtime expression",
                      "pause": "Silence"}.get(item.kind, e(item.kind))
            audio_rows.append([source, e(item.resolved or item.value),
                               f"<code>{e(item.where)}</code>"])
        blocks.append(_panel("audio", "Audio and prompt inventory",
                             _table(["Source", "Content", "Property"], audio_rows)))

    # --- diagram
    diagrams = _diagrams(doc)
    if diagrams or mermaid_source:
        sections.append(("diagram", "Flow diagram"))
        body = diagrams
        if mermaid_source:
            body += ("<details><summary>Mermaid source</summary>"
                     f'<pre>{e(mermaid_source)}</pre></details>')
        blocks.append(_panel("diagram", "Flow diagram", body,
                             "One diagram per stage, drawn from the parsed flow. The Mermaid "
                             "source below is the same graph for pasting into GitHub, GitLab "
                             "or another Markdown viewer; it is also saved as a .mmd file."))

    # --- coverage + provenance
    sections.append(("coverage", "Coverage & provenance"))
    coverage = []
    if doc.unmapped_kinds:
        listed = ", ".join(f"<code>{e(k)}</code>" for k in doc.unmapped_kinds)
        coverage.append(f'<p class="note"><strong>Unrecognised action types.</strong> '
                        f"{listed} are not in this generator's vocabulary. They are documented "
                        f"above from their raw configuration, but their plain-English "
                        f"description is derived from the type name only.</p>")
    else:
        coverage.append('<p class="note note--ok"><strong>Full coverage.</strong> Every action '
                        "type in this flow was recognised and described.</p>")
    orphans = [n for n in doc.all_nodes() if n.unreachable]
    if orphans:
        coverage.append(f'<p class="note note--flag"><strong>{len(orphans)} unreachable '
                        f"action(s).</strong> "
                        + ", ".join(f"<code>{e(n.name)}</code>" for n in orphans)
                        + " cannot be reached from the start of their stage.</p>")

    provenance = [
        ["Flow metadata", f"<code>GET /api/v2/flows/{e(doc.flow_id)}</code>"],
        ["Flow configuration",
         f"<code>GET /api/v2/flows/{e(doc.flow_id)}/latestconfiguration</code>"],
        ["Prompt wording", "<code>GET /api/v2/architect/prompts</code>, "
                           "<code>GET /api/v2/architect/systemprompts</code>"],
        ["Dependencies", "the flow configuration's own <code>manifest</code>"],
    ]
    if doc.ivr:
        provenance.insert(0, ["Call route",
                              f"<code>GET /api/v2/architect/ivrs/{e(doc.ivr.get('id'))}</code>"])
    coverage.append(_table(["Source", "Endpoint"], provenance))
    blocks.append(_panel("coverage", "Coverage and provenance", "".join(coverage)))

    meta = [f"Generated {e(doc.fetched_at or 'date unknown')}",
            f"{len(doc.containers)} stages", f"{steps} actions",
            f"{len(doc.variables)} variables"]
    body = (f'<div class="page">'
            f'{_masthead("Technical specification", doc.name, e(doc.description or doc.flow_type), meta)}'
            f'<div class="layout">{_rail(sections)}'
            f'<main class="stack">{"".join(blocks)}'
            f'{_footer(doc, "The unmodified configuration is saved alongside as .raw.json.")}'
            f"</main></div></div>")
    return _document(f"{doc.name} — Technical Spec", body)


# --------------------------------------------------------------------------
# index across a bulk run
# --------------------------------------------------------------------------

def render_index(entries: list[dict], region: str) -> str:
    cards = []
    for entry in sorted(entries, key=lambda x: x["name"].lower()):
        numbers = ", ".join(entry["dnis"]) if entry["dnis"] else "No numbers attached"
        route = entry.get("route") or "—"
        cards.append(f"""<article class="card">
  <span class="eyebrow">{e(route)}</span>
  <h3><a href="{e(entry['business'])}">{e(entry['name'])}</a></h3>
  <p class="step__what">{e(numbers)}</p>
  <p class="step__what">{entry['stages']} stages · {entry['steps']} steps · {entry['audio']} audio prompts</p>
  <div class="card__links">
    <a href="{e(entry['business'])}">Business</a>
    <a href="{e(entry['technical'])}">Technical</a>
  </div>
</article>""")

    facts = _facts([
        ("Flows documented", str(len(entries)), False),
        ("Steps described", str(sum(x["steps"] for x in entries)), False),
        ("Audio prompts", str(sum(x["audio"] for x in entries)), False),
        ("Region", e(region), True),
    ])
    grid = '<div class="cards">' + "".join(cards) + "</div>"
    subtitle = ("Every Architect call flow attached to a call route in this Genesys Cloud "
                "organisation, documented for business and technical readers.")
    body = (f'<div class="page">'
            f'{_masthead("Call flow documentation", "Flow Library", subtitle, [f"{len(entries)} flows", e(region)])}'
            f'<main class="stack">'
            f'{_panel("overview", "At a glance", facts)}'
            f'{_panel("flows", "Flows", grid)}'
            f"</main></div>")
    return _document("Flow Library", body)
