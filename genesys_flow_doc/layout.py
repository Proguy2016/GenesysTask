"""Where each generated file goes.

A whole-organisation run produces several hundred files. Flat, that is
unusable, so the output mirrors the way the configuration is actually
organised -- a call route owns flows, and a flow owns its documents:

    out/
      index.html                                  every route, grouped
      routes/
        testt-call/                               the call route
          customer-care-ivr-by-claude/            a flow it points at
            html/      <flow>.business.html, <flow>.technical.html
            pdf/       <flow>.business.pdf,  <flow>.technical.pdf
            markdown/  <flow>.business.md,   <flow>.technical.md
            diagram/   <flow>.flow.mmd
            raw/       <flow>.raw.json
      flows/
        some-flow/                                documented via --flow,
          html/ ...                               so it has no route context

Files keep the flow name in them even though the folder already carries it:
a PDF is usually detached from its folder the moment someone emails it, and
`business.pdf` on its own says nothing.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

#: Sub-directory per artefact type.
HTML = "html"
PDF = "pdf"
MARKDOWN = "markdown"
DIAGRAM = "diagram"
RAW = "raw"

KINDS = (HTML, PDF, MARKDOWN, DIAGRAM, RAW)

ROUTES_DIR = "routes"
FLOWS_DIR = "flows"


def slugify(name: str, fallback: str = "unnamed") -> str:
    """A filesystem-safe, lowercase name that cannot escape its directory."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(name)).strip("-").lower()
    slug = slug.strip(". ")
    # Windows reserves these regardless of extension.
    if slug.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                        *(f"LPT{i}" for i in range(1, 10))}:
        slug = f"{slug}-flow"
    return slug[:80] or fallback


@dataclass(frozen=True)
class Destination:
    """The folder tree for one flow, optionally beneath a call route."""

    root: str
    flow_slug: str
    route_slug: str | None = None

    @classmethod
    def for_flow(cls, root: str, flow_name: str, route_name: str | None = None
                 ) -> "Destination":
        return cls(
            root=root,
            flow_slug=slugify(flow_name, "flow"),
            route_slug=slugify(route_name, "route") if route_name else None,
        )

    @property
    def base(self) -> str:
        if self.route_slug:
            return os.path.join(self.root, ROUTES_DIR, self.route_slug, self.flow_slug)
        return os.path.join(self.root, FLOWS_DIR, self.flow_slug)

    def dir_for(self, kind: str) -> str:
        return os.path.join(self.base, kind)

    def path_for(self, kind: str, suffix: str) -> str:
        """e.g. path_for(HTML, 'business.html') -> .../html/<flow>.business.html"""
        return os.path.join(self.dir_for(kind), f"{self.flow_slug}.{suffix}")

    def relative_to_root(self, kind: str, suffix: str) -> str:
        """The same path as a POSIX-style link from the index page."""
        return os.path.relpath(self.path_for(kind, suffix), self.root).replace(os.sep, "/")

    def ensure(self, kinds: list[str]) -> None:
        for kind in kinds:
            os.makedirs(self.dir_for(kind), exist_ok=True)
