"""Render the parsed flow as a Mermaid diagram.

Mermaid renders natively in GitHub, GitLab, Confluence (with the plugin), VS
Code preview and most Markdown viewers, so the diagram travels with the
document instead of being a separate image asset.

Edge semantics: a step's branches fan out from it, and whatever the branches
end on flows into the next step -- so a decision does not appear to reach the
following action directly, but its legs do. Menu choices fan out from the menu
and never chain into one another, because a caller takes exactly one of them.
"""

from __future__ import annotations

import re

from . import taxonomy
from .model import FlowDoc, Node

SHAPES = {
    "logic": ("{{", "}}"),
    "input": ("[/", "/]"),
    "terminal": ("([", "])"),
    "routing": ("[[", "]]"),
    "audio": ("(", ")"),
}
DEFAULT_SHAPE = ("[", "]")
MAX_NODES = 300


def _escape(text: str, limit: int = 58) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    for bad, good in (('"', "'"), ("[", "("), ("]", ")"), ("{", "("), ("}", ")"), ("|", "/")):
        text = text.replace(bad, good)
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def render(doc: FlowDoc) -> str:
    lines = ["flowchart TD"]
    edges: list[str] = []
    ids: dict[int, str] = {}
    entry_points: dict[str, str] = {}
    counter = 0
    truncated = False

    def new_id() -> str | None:
        nonlocal counter, truncated
        counter += 1
        if counter > MAX_NODES:
            truncated = True
            return None
        return f"n{counter}"

    def emit(node: Node, indent: str) -> tuple[str | None, list[str]]:
        """Draw one node. Returns (its id, the ids that flow onward from it)."""
        nid = new_id()
        if not nid:
            return None, []
        ids[id(node)] = nid

        open_shape, close_shape = SHAPES.get(taxonomy.category_for(node.kind), DEFAULT_SHAPE)
        prefix = f"{node.dtmf}: " if node.dtmf else ""
        lines.append(f'{indent}{nid}{open_shape}"{_escape(prefix + node.name)}"{close_shape}')

        if taxonomy.category_for(node.kind) in ("terminal", "routing"):
            # The call leaves the flow here; nothing continues from it.
            for branch in node.branches:
                first, _ = emit_sequence(branch.nodes, indent, fan_out=False)
                if first:
                    edges.append(f'    {nid} -->|"{_escape(branch.label, 24)}"| {first}')
            return nid, []

        exits: list[str] = []
        for branch in node.branches:
            first, branch_exits = emit_sequence(branch.nodes, indent, fan_out=False)
            if first:
                edges.append(f'    {nid} -->|"{_escape(branch.label, 24)}"| {first}')
                exits.extend(branch_exits)
            else:
                exits.append(nid)      # empty branch: falls straight through
        if not node.branches:
            exits.append(nid)
        return nid, exits

    def emit_sequence(nodes: list[Node], indent: str,
                      fan_out: bool) -> tuple[str | None, list[str]]:
        """Draw sibling nodes. `fan_out` means they are alternatives, not a sequence."""
        first: str | None = None
        pending: list[str] = []
        exits: list[str] = []

        for node in nodes:
            nid, node_exits = emit(node, indent)
            if not nid:
                break
            if first is None:
                first = nid
            if fan_out:
                exits.extend(node_exits)
                continue
            for source in pending:
                edges.append(f"    {source} --> {nid}")
            pending = node_exits

        return first, (exits if fan_out else pending)

    for index, container in enumerate(doc.containers):
        safe = re.sub(r"[^A-Za-z0-9]", "_", container.name) or f"c{index}"
        title = _escape(f"{taxonomy.label_for(container.kind)}: {container.name}")
        lines.append(f'    subgraph sg_{index}_{safe}["{title}"]')

        head = new_id()
        if head:
            lines.append(f'        {head}(["{_escape(container.name)}"])')
            entry_points[container.name] = head
            if container.ref:
                entry_points[container.ref] = head

        # A menu presents alternatives; a task runs its steps in order.
        choices = bool(container.nodes) and all(n.dtmf for n in container.nodes)
        first, _ = emit_sequence(container.nodes, "        ", fan_out=choices)
        if head and first:
            if choices:
                for node in container.nodes:
                    target = ids.get(id(node))
                    if target:
                        label = _escape(f"press {node.dtmf}", 24)
                        edges.append(f'    {head} -->|"{label}"| {target}')
            else:
                edges.append(f"    {head} --> {first}")
        lines.append("    end")

    # Cross-container jumps, dashed so they read differently from ordinary flow.
    for container in doc.containers:
        for node in container.walk():
            source = ids.get(id(node))
            if not source:
                continue
            for jump in node.jumps:
                target = entry_points.get(jump)
                if not target:
                    match = re.search(r"\[(.+?)_\d+\]", jump)
                    if match:
                        target = entry_points.get(match.group(1))
                if target and target != source:
                    edges.append(f"    {source} -.-> {target}")

    lines.extend(sorted(set(edges)))
    if truncated:
        lines.append(f'    truncated["… diagram truncated at {MAX_NODES} nodes"]')
    return "\n".join(lines)
