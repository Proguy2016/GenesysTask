"""Technical document: every node, every property, every branch."""

from __future__ import annotations

from . import mermaid, taxonomy
from .model import Container, FlowDoc, Node
from .speech import dedupe

MAX_PROPS_PER_NODE = 40


def _cell(text: object) -> str:
    if text is None:
        return "—"
    return str(text).replace("|", "\\|").replace("\n", " ").strip() or "—"


def _code(text: object) -> str:
    value = str(text).strip()
    return f"`{value}`" if value else "—"


def _heading_for(node: Node) -> str:
    label = taxonomy.label_for(node.kind)
    if node.dtmf:
        return f"Press {node.dtmf} — {node.name}"
    return node.name if node.name.lower() != label.lower() else label


def _render_node(node: Node, number: str, depth: int, out: list[str]) -> None:
    level = min(depth + 4, 6)
    out.append(f"\n{'#' * level} {number} {_heading_for(node)}")
    out.append("")
    out.append(
        f"- **Action type:** `{node.kind}` ({taxonomy.label_for(node.kind)})"
        + (f" · **Tracking ID:** `{node.tracking_id}`" if node.tracking_id else "")
    )
    out.append(f"- **What it does:** {taxonomy.business_for(node.kind)}")
    if node.dtmf:
        out.append(f"- **Caller presses:** `{node.dtmf}`")
    if not taxonomy.is_known(node.kind):
        out.append("- **Note:** this action type is not in the generator's vocabulary; "
                   "properties below are reported verbatim from the flow configuration.")
    if node.unreachable:
        out.append("- **Note:** this action is configured but cannot be reached from the "
                   "start of this stage. It is dead configuration unless something jumps "
                   "to it that the export does not record.")

    if node.speech:
        out.append("")
        out.append("**Spoken to the caller**")
        out.append("")
        for item in dedupe(node.speech):
            source = {
                "prompt": f"user prompt `{item.value}`",
                "system-prompt": f"system prompt `{item.value}`",
                "dynamic": "runtime expression",
                "pause": "silence",
            }.get(item.kind, "inline text-to-speech")
            out.append(f"- ({source}) > {_cell(item.resolved or item.value)}")

    visible = [(p, v) for p, v in node.props if p]
    if visible:
        out.append("")
        out.append("**Configuration**")
        out.append("")
        out.append("| Property | Value |")
        out.append("| --- | --- |")
        for prop, value in visible[:MAX_PROPS_PER_NODE]:
            out.append(f"| `{_cell(prop)}` | {_cell(value)} |")
        if len(visible) > MAX_PROPS_PER_NODE:
            out.append(f"| … | {len(visible) - MAX_PROPS_PER_NODE} further properties omitted |")

    if node.jumps:
        out.append("")
        out.append("**Continues at:** " + ", ".join(_code(j) for j in node.jumps))

    for branch_index, branch in enumerate(node.branches, start=1):
        out.append("")
        out.append(f"**Branch — {branch.label}** ({len(branch.nodes)} step(s))")
        for child_index, child in enumerate(branch.nodes, start=1):
            _render_node(child, f"{number}.{branch_index}.{child_index}", depth + 1, out)


def _render_container(container: Container, index: int, out: list[str]) -> None:
    marker = "  ⭑ entry point" if container.is_start else ""
    out.append(f"\n### {index}. {taxonomy.label_for(container.kind)}: {container.name}{marker}")
    out.append("")
    out.append(f"- **Reference:** {_code(container.ref)}")
    if container.tracking_id:
        out.append(f"- **Tracking ID:** `{container.tracking_id}`")
    out.append(f"- **Steps:** {len(container.nodes)} top-level, "
               f"{sum(1 for _ in container.walk())} including nested branches")

    if container.speech:
        out.append("")
        out.append("**Spoken at this level**")
        out.append("")
        for item in dedupe(container.speech):
            out.append(f"- > {_cell(item.resolved or item.value)}")

    if container.props:
        out.append("")
        out.append("<details><summary>Container-level configuration</summary>")
        out.append("")
        out.append("| Property | Value |")
        out.append("| --- | --- |")
        for prop, value in container.props[:MAX_PROPS_PER_NODE]:
            out.append(f"| `{_cell(prop)}` | {_cell(value)} |")
        out.append("")
        out.append("</details>")

    for node_index, node in enumerate(container.nodes, start=1):
        _render_node(node, f"{index}.{node_index}", 0, out)


def render(doc: FlowDoc) -> str:
    out: list[str] = []
    out.append(f"# Technical specification — {doc.name}")
    out.append("")
    out.append(f"*Generated from the live Genesys Cloud configuration on {doc.fetched_at or 'unknown date'}.*")
    out.append("")

    # ---------------------------------------------------------------- facts
    out.append("## 1. Flow identity")
    out.append("")
    out.append("| Field | Value |")
    out.append("| --- | --- |")
    rows = [
        ("Flow name", doc.name),
        ("Flow ID", f"`{doc.flow_id}`"),
        ("Flow type", doc.flow_type),
        ("Division", doc.division),
        ("Description", doc.description),
        ("Published version", doc.published_version),
        ("Default language", doc.default_language),
        ("Supported languages", ", ".join(doc.supported_languages)),
        ("Entry point", _code(doc.start_ref)),
        ("Tasks / menus / states", len(doc.containers)),
        ("Total actions", sum(1 for _ in doc.all_nodes())),
    ]
    for label, value in rows:
        out.append(f"| {label} | {_cell(value)} |")

    if doc.ivr:
        out.append("")
        out.append("### Call route (IVR entity) this flow is attached to")
        out.append("")
        out.append("| Field | Value |")
        out.append("| --- | --- |")
        out.append(f"| Name | {_cell(doc.ivr.get('name'))} |")
        out.append(f"| IVR ID | `{doc.ivr.get('id')}` |")
        out.append(f"| Numbers (DNIS) | {_cell(', '.join(doc.dnis) or '—')} |")
        for role, target in doc.sibling_flows.items():
            out.append(f"| {role} | {_cell(target)} |")
        if doc.ivr.get("scheduleGroup"):
            out.append(f"| Schedule group | {_cell((doc.ivr['scheduleGroup'] or {}).get('name'))} |")

    if doc.schedule_summary:
        out.append("")
        out.append("### Operating schedule")
        out.append("")
        out.extend(doc.schedule_summary)

    # ------------------------------------------------------------- diagram
    out.append("")
    out.append("## 2. Flow diagram")
    out.append("")
    out.append("```mermaid")
    out.append(mermaid.render(doc))
    out.append("```")
    out.append("")
    out.append("Shapes: rounded = audio, parallelogram = caller input, hexagon = logic, "
               "double square = routing/transfer, stadium = end of call. "
               "Dashed arrows are jumps to another task or menu.")

    # ------------------------------------------------------------ variables
    out.append("")
    out.append("## 3. Variables")
    out.append("")
    if doc.variables:
        out.append("| Name | Type | Scope | Initial value | Input | Output |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        for variable in doc.variables:
            out.append(
                f"| `{_cell(variable['name'])}` | {_cell(variable['type'])} | "
                f"{_cell(variable.get('scope'))} | {_cell(variable['initial'])} | "
                f"{'yes' if variable['input'] else '—'} | "
                f"{'yes' if variable['output'] else '—'} |"
            )
    else:
        out.append("No flow-level variables are defined.")

    # ------------------------------------------------------------- the flow
    out.append("")
    out.append("## 4. Node-by-node specification")
    out.append("")
    out.append("Every task, menu and state in the flow, in execution order, with each "
               "action's configuration exactly as stored in Architect.")
    for index, container in enumerate(doc.containers, start=1):
        _render_container(container, index, out)

    # ---------------------------------------------------------- dependencies
    out.append("")
    out.append("## 5. External dependencies")
    out.append("")
    if doc.references:
        for label, values in doc.references.items():
            out.append(f"**{label}**")
            out.append("")
            for value in values:
                out.append(f"- {value}")
            out.append("")
    else:
        out.append("No external queues, data actions, data tables or flows were referenced "
                   "(or dependency resolution was disabled with `--no-resolve`).")

    # ------------------------------------------------------------ audio index
    speech = dedupe(doc.all_speech())
    out.append("")
    out.append("## 6. Audio and prompt inventory")
    out.append("")
    if speech:
        out.append("| Source | Content |")
        out.append("| --- | --- |")
        for item in speech:
            label = {
                "tts": "Inline TTS",
                "prompt": f"User prompt `{item.value}`",
                "system-prompt": f"System prompt `{item.value}`",
                "dynamic": "Runtime expression",
                "pause": "Silence",
                "text": "Text",
            }.get(item.kind, item.kind)
            out.append(f"| {label} | {_cell(item.resolved or item.value)} |")
    else:
        out.append("No caller-facing audio was found in this flow.")

    # -------------------------------------------------------------- coverage
    out.append("")
    out.append("## 7. Generator coverage notes")
    out.append("")
    if doc.unmapped_kinds:
        out.append("The following action types are not in this generator's vocabulary. They "
                   "are still documented above from their raw configuration, but their "
                   "plain-English description is derived from the type name only:")
        out.append("")
        for kind in doc.unmapped_kinds:
            out.append(f"- `{kind}`")
    else:
        out.append("Every action type in this flow was recognised.")

    unresolved = [s for s in speech if s.kind in ("prompt", "system-prompt") and not s.resolved]
    if unresolved:
        out.append("")
        out.append("Prompts that could not be resolved to text (missing, or the OAuth client "
                   "lacks read access):")
        out.append("")
        for item in unresolved:
            out.append(f"- `{item.value}` ({item.kind})")

    out.append("")
    out.append("## 8. Provenance")
    out.append("")
    out.append("| Source | Endpoint |")
    out.append("| --- | --- |")
    if doc.ivr:
        out.append(f"| Call route | `GET /api/v2/architect/ivrs/{doc.ivr.get('id')}` |")
    out.append(f"| Flow metadata | `GET /api/v2/flows/{doc.flow_id}` |")
    out.append(f"| Flow configuration | `GET /api/v2/flows/{doc.flow_id}/latestconfiguration` |")
    out.append("| Prompt text | `GET /api/v2/architect/prompts`, `GET /api/v2/architect/systemprompts` |")
    out.append("")
    out.append("The unmodified configuration JSON is saved alongside this document as "
               "`<flow>.raw.json`; re-run with `--offline <that file>` to regenerate the "
               "documents without calling the API again.")

    return "\n".join(out) + "\n"
