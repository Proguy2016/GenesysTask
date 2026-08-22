"""Draw the flow as inline SVG.

Mermaid source is fine for a developer pasting it into GitHub, but it is not a
diagram in a PDF a client reads. This module lays the parsed model out itself
and emits SVG, so the picture is part of the document: it prints, it scales, it
needs no JavaScript, and it is themed with the same tokens as the rest of the
page.

Layout is a deterministic top-down tree, one diagram per stage:

    a chain of steps stacks vertically;
    a step with branches puts its branches side by side beneath it,
    with the branch label on the connector.

No general graph-layout algorithm is involved, so the result is stable, has no
crossing edges, and is laid out the same way every time the document is built.
"""

from __future__ import annotations

import html

from . import taxonomy
from .model import Container, Node

BOX_W = 208
BOX_MIN_H = 46
LINE_H = 15
PAD_Y = 13
GAP_Y = 34          # vertical space between a step and the next
GAP_X = 26          # horizontal space between sibling branches
MARGIN = 16
CHAR_W = 6.35       # approximate advance of the 12.5px label face
MAX_LINES = 3
MAX_COLUMNS = 6     # beyond this, branches are summarised rather than drawn


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _wrap(text: str, width: int = BOX_W - 26) -> list[str]:
    """Greedy wrap using an estimated character advance."""
    limit = max(8, int(width / CHAR_W))
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(word) > limit:
            word = word[: limit - 1] + "…"
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
        if len(lines) == MAX_LINES:
            break
    if current and len(lines) < MAX_LINES:
        lines.append(current)
    if not lines:
        lines = [""]
    if len(lines) == MAX_LINES and len(" ".join(words)) > sum(len(l) for l in lines):
        lines[-1] = lines[-1][: limit - 1].rstrip() + "…"
    return lines


class _Box:
    """One drawn step, with its own measured subtree."""

    def __init__(self, node: Node):
        self.node = node
        self.lines = _wrap(node.name)
        self.height = max(BOX_MIN_H, PAD_Y * 2 + LINE_H * len(self.lines))
        self.children: list[tuple[str, "_Chain"]] = []
        self.width = BOX_W
        self.total_w = BOX_W
        self.total_h = self.height
        self.x = 0.0
        self.y = 0.0


class _Chain:
    """A vertical sequence of steps."""

    def __init__(self, boxes: list[_Box]):
        self.boxes = boxes
        self.total_w = BOX_W
        self.total_h = 0.0
        self.x = 0.0
        self.y = 0.0


# --------------------------------------------------------------------------
# measuring
# --------------------------------------------------------------------------

def _build_chain(nodes: list[Node], depth: int) -> _Chain:
    boxes: list[_Box] = []
    for node in nodes:
        box = _Box(node)
        if depth < 6:
            for branch in node.branches[:MAX_COLUMNS]:
                if branch.nodes:
                    box.children.append((branch.label, _build_chain(branch.nodes, depth + 1)))
            hidden = len(node.branches) - len(box.children)
            if hidden > 0:
                box.lines = _wrap(f"{node.name}  (+{hidden} more paths)")
                box.height = max(BOX_MIN_H, PAD_Y * 2 + LINE_H * len(box.lines))
        boxes.append(box)
    chain = _Chain(boxes)
    _measure_chain(chain)
    return chain


def _measure_box(box: _Box) -> None:
    if not box.children:
        box.total_w = BOX_W
        box.total_h = box.height
        return
    for _, chain in box.children:
        _measure_chain(chain)
    inner_w = sum(c.total_w for _, c in box.children) + GAP_X * (len(box.children) - 1)
    box.total_w = max(BOX_W, inner_w)
    box.total_h = box.height + GAP_Y + max(c.total_h for _, c in box.children)


def _measure_chain(chain: _Chain) -> None:
    total_h = 0.0
    width = BOX_W
    for index, box in enumerate(chain.boxes):
        _measure_box(box)
        width = max(width, box.total_w)
        total_h += box.total_h
        if index < len(chain.boxes) - 1:
            total_h += GAP_Y
    chain.total_w = width
    chain.total_h = total_h


# --------------------------------------------------------------------------
# placing
# --------------------------------------------------------------------------

def _place_chain(chain: _Chain, x: float, y: float) -> None:
    """`x` is the centre line the chain hangs from."""
    chain.x, chain.y = x, y
    cursor = y
    for box in chain.boxes:
        _place_box(box, x, cursor)
        cursor += box.total_h + GAP_Y


def _place_box(box: _Box, centre_x: float, y: float) -> None:
    box.x = centre_x - BOX_W / 2
    box.y = y
    if not box.children:
        return
    inner_w = sum(c.total_w for _, c in box.children) + GAP_X * (len(box.children) - 1)
    cursor = centre_x - inner_w / 2
    child_y = y + box.height + GAP_Y
    for _, chain in box.children:
        _place_chain(chain, cursor + chain.total_w / 2, child_y)
        cursor += chain.total_w + GAP_X


# --------------------------------------------------------------------------
# drawing
# --------------------------------------------------------------------------

def _draw_box(box: _Box, out: list[str]) -> None:
    node = box.node
    colour = f"var(--cat-{taxonomy.category_for(node.kind)})"
    text_y = box.y + PAD_Y + 11

    out.append(
        f'<rect x="{box.x:.1f}" y="{box.y:.1f}" width="{BOX_W}" height="{box.height:.1f}" '
        f'rx="9" style="fill:var(--surface);stroke:{colour};stroke-width:1.4"/>'
    )
    out.append(
        f'<rect x="{box.x:.1f}" y="{box.y:.1f}" width="4.5" height="{box.height:.1f}" '
        f'style="fill:{colour}"/>'
    )

    label_x = box.x + 14
    if node.dtmf:
        badge = node.dtmf if len(node.dtmf) <= 2 else "•"
        out.append(
            f'<rect x="{box.x + 12:.1f}" y="{box.y + 9:.1f}" width="19" height="19" rx="5" '
            f'style="fill:{colour};opacity:.15"/>'
            f'<text x="{box.x + 21.5:.1f}" y="{box.y + 22.5:.1f}" text-anchor="middle" '
            f'style="fill:{colour};font:600 11px ui-monospace,monospace">{_esc(badge)}</text>'
        )
        label_x = box.x + 38

    for index, line in enumerate(box.lines):
        out.append(
            f'<text x="{label_x:.1f}" y="{text_y + index * LINE_H:.1f}" '
            f'style="fill:var(--ink);font:500 12.5px ui-sans-serif,system-ui,sans-serif">'
            f"{_esc(line)}</text>"
        )

    kind_label = taxonomy.label_for(node.kind)
    out.append(
        f'<text x="{box.x + BOX_W - 10:.1f}" y="{box.y + box.height - 8:.1f}" '
        f'text-anchor="end" style="fill:var(--muted);font:400 9px ui-monospace,monospace;'
        f'letter-spacing:.05em">{_esc(kind_label.upper())}</text>'
    )


def _connector(x1: float, y1: float, x2: float, y2: float, label: str,
               out: list[str]) -> None:
    stroke = 'style="stroke:var(--hairline-2);stroke-width:1.4;fill:none"'
    if abs(x1 - x2) < 0.6:
        out.append(f'<path d="M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}" {stroke}/>')
    else:
        mid = y1 + (y2 - y1) / 2
        out.append(
            f'<path d="M {x1:.1f} {y1:.1f} L {x1:.1f} {mid:.1f} '
            f'L {x2:.1f} {mid:.1f} L {x2:.1f} {y2:.1f}" {stroke}/>'
        )
    out.append(
        f'<path d="M {x2 - 4:.1f} {y2 - 5:.1f} L {x2:.1f} {y2:.1f} L {x2 + 4:.1f} {y2 - 5:.1f}" '
        f'style="stroke:var(--hairline-2);stroke-width:1.4;fill:none"/>'
    )
    if label:
        text = label if len(label) <= 18 else label[:17] + "…"
        width = len(text) * 5.6 + 10
        label_y = y1 + (y2 - y1) / 2
        out.append(
            f'<rect x="{x2 - width / 2:.1f}" y="{label_y - 8:.1f}" width="{width:.1f}" '
            f'height="16" rx="4" style="fill:var(--ground)"/>'
            f'<text x="{x2:.1f}" y="{label_y + 3.5:.1f}" text-anchor="middle" '
            f'style="fill:var(--muted);font:600 9.5px ui-sans-serif,sans-serif;'
            f'letter-spacing:.04em">{_esc(text.upper())}</text>'
        )


def _draw_chain(chain: _Chain, out: list[str]) -> None:
    for index, box in enumerate(chain.boxes):
        _draw_box(box, out)
        centre = box.x + BOX_W / 2

        for label, child in box.children:
            first = child.boxes[0]
            _connector(centre, box.y + box.height,
                       first.x + BOX_W / 2, first.y, label, out)
            _draw_chain(child, out)

        if index < len(chain.boxes) - 1:
            nxt = chain.boxes[index + 1]
            # A step with branches flows onward from the branches, not itself.
            if not box.children:
                _connector(centre, box.y + box.height,
                           nxt.x + BOX_W / 2, nxt.y, "", out)
            else:
                for _, child in box.children:
                    tail = child.boxes[-1]
                    if taxonomy.category_for(tail.node.kind) in ("terminal", "routing"):
                        continue
                    _connector(tail.x + BOX_W / 2, tail.y + tail.height,
                               nxt.x + BOX_W / 2, nxt.y, "", out)


def render_stage(container: Container) -> str:
    """One SVG for one task or menu. Returns '' if there is nothing to draw."""
    if not container.nodes:
        return ""

    chain = _build_chain(container.nodes, depth=0)
    _place_chain(chain, chain.total_w / 2 + MARGIN, MARGIN)

    body: list[str] = []
    _draw_chain(chain, body)

    width = chain.total_w + MARGIN * 2
    height = chain.total_h + MARGIN * 2
    return (
        f'<svg class="flowsvg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" '
        f'aria-label="Flow diagram for {_esc(container.name)}" '
        f'xmlns="http://www.w3.org/2000/svg">{"".join(body)}</svg>'
    )
