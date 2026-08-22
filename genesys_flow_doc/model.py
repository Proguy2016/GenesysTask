"""Normalised representation of an Architect flow, independent of Genesys' JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Speech:
    """Something the caller actually hears."""

    kind: str                 # "tts" | "prompt" | "system-prompt" | "text" | "expression"
    value: str                # literal text, or the prompt name being referenced
    where: str                # property path it came from, e.g. "audio.exp"
    resolved: str | None = None   # prompt text pulled back from the API

    def spoken(self) -> str:
        return self.resolved or self.value


@dataclass
class Branch:
    """A named outcome of a node — a menu key, a decision leg, an error path."""

    label: str
    nodes: list["Node"] = field(default_factory=list)


@dataclass
class Node:
    """One Architect action (a box in the flow editor)."""

    kind: str                                   # raw Architect type, e.g. "playAudio"
    name: str
    tracking_id: str | None
    path: str                                   # JSON path, for traceability
    props: list[tuple[str, str]] = field(default_factory=list)
    speech: list[Speech] = field(default_factory=list)
    branches: list[Branch] = field(default_factory=list)
    jumps: list[str] = field(default_factory=list)   # refs to other containers
    dtmf: str | None = None                     # for menu choices: "1", "2", "*"
    unreachable: bool = False                   # present but not reachable from the start
    raw: dict = field(default_factory=dict)

    def walk(self):
        yield self
        for branch in self.branches:
            for child in branch.nodes:
                yield from child.walk()


@dataclass
class Container:
    """A task, menu or state — the top-level groupings inside a flow."""

    kind: str                 # "task" | "menu" | "state" | ...
    name: str
    tracking_id: str | None
    ref: str | None           # e.g. "/menus/menu[Main Menu_10]"
    is_start: bool = False
    props: list[tuple[str, str]] = field(default_factory=list)
    speech: list[Speech] = field(default_factory=list)
    nodes: list[Node] = field(default_factory=list)

    def walk(self):
        for node in self.nodes:
            yield from node.walk()


@dataclass
class FlowDoc:
    """Everything needed to write both documents."""

    flow_id: str
    name: str
    flow_type: str
    description: str | None = None
    division: str | None = None
    published_version: str | None = None
    default_language: str | None = None
    supported_languages: list[str] = field(default_factory=list)
    variables: list[dict[str, Any]] = field(default_factory=list)
    containers: list[Container] = field(default_factory=list)
    start_ref: str | None = None

    # Context assembled around the flow
    ivr: dict[str, Any] | None = None
    dnis: list[str] = field(default_factory=list)
    schedule_summary: list[str] = field(default_factory=list)
    sibling_flows: dict[str, str] = field(default_factory=dict)   # role -> "name (id)"
    references: dict[str, list[str]] = field(default_factory=dict)  # queues, prompts, ...
    name_by_id: dict[str, str] = field(default_factory=dict)        # GUID -> friendly name
    unmapped_kinds: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    fetched_at: str | None = None

    def all_nodes(self):
        for container in self.containers:
            yield from container.walk()

    def all_speech(self) -> list[Speech]:
        out: list[Speech] = []
        for container in self.containers:
            out.extend(container.speech)
            for node in container.walk():
                out.extend(node.speech)
        return out
