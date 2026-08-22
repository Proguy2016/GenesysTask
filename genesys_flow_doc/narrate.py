"""Optional: have Claude write the executive summary for the business document.

Everything else in both documents is generated deterministically from the flow
configuration. This step only adds a narrative summary, and it is given the
already-extracted facts rather than being asked to interpret raw JSON, so it
cannot invent queues, prompts or destinations that are not in the flow.
"""

from __future__ import annotations

import json
import logging
import re

from .model import FlowDoc
from .speech import dedupe

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"

SYSTEM = """You write internal documentation for contact-centre operations teams.

You will be given a structured digest of one Genesys Cloud Architect call flow.
Write an executive summary for a business audience.

Rules:
- Use only facts present in the digest. Never invent a queue, number, prompt,
  opening hour or destination. If something is unknown, say so plainly.
- No Genesys or Architect jargon: no action type names, no GUIDs, no expression
  syntax. Say "the caller is put through to the Sales queue", not "transferToAcd".
- Write in British English, third person, present tense.
- Output Markdown with exactly these sections and nothing else:
  "### In one paragraph" (3-5 sentences on the purpose of this flow and who it
  serves), "### How a typical call goes" (a short numbered list of the main path
  a caller takes), and "### Worth knowing" (3-6 bullets on notable rules,
  fallbacks, edge cases or risks that an operations manager should be aware of).
"""


def _digest(doc: FlowDoc) -> str:
    """A compact, factual summary of the flow for the model to work from."""
    from .render_business import describe

    stages = []
    for container in doc.containers:
        steps = []
        for node in list(container.walk())[:60]:
            steps.append({
                "step": node.name,
                "does": describe(node, doc.name_by_id),
                "press": node.dtmf,
                "says": [s.resolved or s.value for s in dedupe(node.speech)][:4],
            })
        stages.append({
            "stage": container.name,
            "is_entry_point": container.is_start,
            "says": [s.resolved or s.value for s in dedupe(container.speech)][:4],
            "steps": steps,
        })

    return json.dumps({
        "flow_name": doc.name,
        "flow_type": doc.flow_type,
        "description": doc.description,
        "numbers_dialled": doc.dnis,
        "call_route": (doc.ivr or {}).get("name"),
        "related_flows": doc.sibling_flows,
        "opening_hours": doc.schedule_summary,
        "language": doc.default_language,
        "depends_on": doc.references,
        "stages": stages,
    }, indent=1, ensure_ascii=False)[:400_000]


def executive_summary(doc: FlowDoc) -> str | None:
    """Returns Markdown, or None if the SDK or API key is unavailable."""
    try:
        import anthropic
    except ImportError:
        log.warning("--narrate needs the anthropic package: pip install anthropic")
        return None

    client = anthropic.Anthropic()
    prompt = f"Here is the digest of the call flow:\n\n{_digest(doc)}"

    def _run(use_fallbacks: bool):
        kwargs = dict(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )
        if use_fallbacks:
            # Route around a safety refusal automatically rather than failing.
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
            with client.beta.messages.stream(**kwargs) as stream:
                return stream.get_final_message()
        with client.messages.stream(**kwargs) as stream:
            return stream.get_final_message()

    try:
        try:
            message = _run(use_fallbacks=True)
        except TypeError:
            # Older SDK without the fallbacks parameter.
            message = _run(use_fallbacks=False)
    except Exception as exc:                      # noqa: BLE001 - never block the docs
        log.warning("Executive summary skipped: %s", exc)
        return None

    if getattr(message, "stop_reason", None) == "refusal":
        log.warning("Executive summary skipped: the request was declined.")
        return None

    text = "".join(block.text for block in message.content if block.type == "text").strip()
    return text or None


def insert_summary(business_markdown: str, summary: str) -> str:
    """Place the summary directly after the document's preamble."""
    marker = "\n## At a glance"
    if marker in business_markdown:
        head, _, tail = business_markdown.partition(marker)
        return f"{head}\n## Executive summary\n\n{summary}\n{marker}{tail}"
    return f"{business_markdown}\n\n## Executive summary\n\n{summary}\n"


def _summary_to_html(summary: str) -> str:
    """Render the constrained Markdown the model is asked for (h3, lists, bold)."""
    import html as _html

    out: list[str] = []
    list_tag: str | None = None

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    for line in summary.splitlines():
        stripped = line.strip()
        if not stripped:
            close_list()
            continue
        text = _html.escape(stripped)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)

        if stripped.startswith("###"):
            close_list()
            out.append(f"<h3>{text.lstrip('# ').strip()}</h3>")
        elif re.match(r"^\d+[.)]\s", stripped):
            if list_tag != "ol":
                close_list()
                out.append("<ol>")
                list_tag = "ol"
            out.append(f"<li>{re.sub(r'^\d+[.)]\s*', '', text)}</li>")
        elif stripped.startswith(("- ", "* ")):
            if list_tag != "ul":
                close_list()
                out.append("<ul>")
                list_tag = "ul"
            out.append(f"<li>{text[2:]}</li>")
        else:
            close_list()
            out.append(f'<p class="step__what">{text}</p>')
    close_list()
    return "".join(out)


def insert_summary_html(business_html: str, summary: str) -> str:
    """Add the summary as the first panel of the HTML business document."""
    panel = ('<section class="panel" id="executive-summary">'
             "<h2>Executive summary</h2>"
             f'<div class="stack" style="gap:.7rem">{_summary_to_html(summary)}</div>'
             "</section>")
    marker = '<main class="stack">'
    if marker in business_html:
        head, _, tail = business_html.partition(marker)
        body = head + marker + panel + tail
        # Give it a place in the contents rail too.
        return body.replace('<ol><li><a href="#overview">',
                            '<ol><li><a href="#executive-summary">Executive summary</a></li>'
                            '<li><a href="#overview">', 1)
    return business_html
