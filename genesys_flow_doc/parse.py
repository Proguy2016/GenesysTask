"""Turn the Architect flow configuration JSON into the normalised model.

The published configuration is a **graph**, not a tree:

    flowSequenceItemList[]           the stages -- Task and Menu objects
      Task:  startAction, actionList[], paths[]
      Menu:  menuChoiceList[], prompts, defaultMenuChoice

    action:  { __type, id, name, trackingId,
               nextAction: <id>,                     sequential successor
               paths: [{nextActionId, label}],       labelled branches
               <property>: {config, text, type} }    a value object

So an action's successors are found by following `nextAction` and every
`paths[].nextActionId`. This module walks that graph from each stage's start
action into an ordered tree, marking repeat visits as jumps rather than
expanding them again (flows contain loops and shared error handlers), and
reports any action that is unreachable from the start.

Value objects carry a `text` field holding the human-readable expression, so
queue names, phone numbers and conditions come through directly.
"""

from __future__ import annotations

import re
from typing import Any

from . import taxonomy
from .model import Branch, Container, FlowDoc, Node, Speech
from .speech import from_audio_value

# Keys that describe structure rather than configuration.
STRUCTURAL = {
    "id", "__type", "trackingId", "uiMetaData", "metaData", "version",
    "paths", "path", "nextAction", "name", "startAction", "actionList",
    "menuChoiceList", "variables", "defaultMenuChoice", "errorBindings",
    "outOfService", "config",
}

# Property values that add noise without adding meaning.
BORING_VALUES = {"", "true", "false", "0", "-1", "[]", "{}"}

# Architect writes an empty communication wrapper when nothing is configured.
EMPTY_EXPRESSION = re.compile(r'^\s*\w+\(\s*""?\s*\)\s*$', re.DOTALL)


# --------------------------------------------------------------------------
# value objects
# --------------------------------------------------------------------------

def is_value_object(obj: Any) -> bool:
    return isinstance(obj, dict) and "text" in obj and "type" in obj


def is_audio_block(obj: Any) -> bool:
    """`{bargeInExpression, flushExpression, defaultAudio, cases}`."""
    return isinstance(obj, dict) and "defaultAudio" in obj


def _entity_id(value: dict) -> str | None:
    """The GUID behind a literal entity reference, e.g. a queue or user."""
    literal = ((value.get("config") or {}).get("lit")) or {}
    candidate = literal.get("val")
    if isinstance(candidate, str) and len(candidate) == 36 and candidate.count("-") == 4:
        return candidate
    return None


# --------------------------------------------------------------------------
# property + speech extraction
# --------------------------------------------------------------------------

class _Extractor:
    def __init__(self) -> None:
        self.props: list[tuple[str, str]] = []
        self.speech: list[Speech] = []
        self.entities: dict[str, str] = {}     # GUID -> the name Architect shows

    def add_prop(self, path: str, value: str) -> None:
        text = str(value).strip()
        if not text or text in BORING_VALUES:
            return
        if EMPTY_EXPRESSION.match(text.replace("\n", " ")):
            return
        self.props.append((path, text))

    def walk(self, obj: Any, path: str) -> None:
        if is_audio_block(obj):
            default = obj.get("defaultAudio")
            if isinstance(default, dict):
                self.speech.extend(from_audio_value(default, path))
                self.add_prop(path, default.get("text") or "")
            for index, case in enumerate(obj.get("cases") or []):
                if not isinstance(case, dict) or case.get("disabled"):
                    continue
                expression = case.get("audioExpression")
                if isinstance(expression, dict) and (expression.get("text") or "").strip():
                    language = case.get("langCode") or f"case {index + 1}"
                    for item in from_audio_value(expression, f"{path}.cases[{language}]"):
                        item.value = f"{item.value}  [{language}]"
                        self.speech.append(item)
            return

        if is_value_object(obj):
            text = str(obj.get("text") or "").strip()
            if obj.get("type") == "aud":
                self.speech.extend(from_audio_value(obj, path))
            guid = _entity_id(obj)
            if guid and text:
                self.entities[guid] = text
            self.add_prop(path, text)
            return

        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in STRUCTURAL:
                    continue
                self.walk(value, f"{path}.{key}" if path else key)
            return

        if isinstance(obj, list):
            for index, item in enumerate(obj):
                self.walk(item, f"{path}[{index}]")
            return

        if isinstance(obj, bool):
            self.add_prop(path, "yes" if obj else "no")
        elif obj is not None:
            self.add_prop(path, str(obj))


# --------------------------------------------------------------------------
# graph walking
# --------------------------------------------------------------------------

class _FlowGraph:
    """Indexes every action in the flow so successors can be resolved."""

    def __init__(self, sequences: list[dict]):
        self.actions: dict[str, dict] = {}
        self.owner: dict[str, str] = {}          # action id -> stage name
        self.stage_of: dict[str, str] = {}
        self.sequence_names: dict[str, str] = {}  # stage id -> stage name
        self.unknown: set[str] = set()

        for sequence in sequences:
            stage_id = str(sequence.get("id") or "")
            stage_name = str(sequence.get("name") or "Unnamed")
            self.sequence_names[stage_id] = stage_name
            for action in sequence.get("actionList") or []:
                self._index(action, stage_name)
            for choice in sequence.get("menuChoiceList") or []:
                action = choice.get("action")
                if isinstance(action, dict):
                    self._index(action, stage_name)
            default_choice = sequence.get("defaultMenuChoice")
            if isinstance(default_choice, dict) and isinstance(default_choice.get("action"), dict):
                self._index(default_choice["action"], stage_name)

    def _index(self, action: dict, stage_name: str) -> None:
        action_id = str(action.get("id") or "")
        if action_id:
            self.actions[action_id] = action
            self.owner[action_id] = stage_name

    def successors(self, action: dict) -> list[tuple[str, str]]:
        """[(label, target action id)] -- branches first, then the plain successor."""
        out: list[tuple[str, str]] = []
        paths = action.get("paths")
        if isinstance(paths, dict):
            paths = [paths]
        for path in paths or []:
            if not isinstance(path, dict):
                continue
            target = path.get("nextActionId")
            if target:
                out.append((str(path.get("label") or "Next"), str(target)))
        single = action.get("path")
        if isinstance(single, dict) and single.get("nextActionId"):
            out.append((str(single.get("label") or "Loop"), str(single["nextActionId"])))
        return out

    def describe(self, action_id: str) -> str:
        action = self.actions.get(action_id)
        if not action:
            return "an action outside this flow"
        stage = self.owner.get(action_id, "")
        name = action.get("name") or taxonomy.label_for(str(action.get("__type")))
        return f"{name} (in {stage})" if stage else str(name)


class _Walker:
    def __init__(self, graph: _FlowGraph):
        self.graph = graph
        self.visited: set[str] = set()
        self.entities: dict[str, str] = {}
        self.unknown: set[str] = set()

    def build_node(self, action: dict, stage: str, dtmf: str | None = None) -> Node:
        kind = str(action.get("__type") or "Action")
        if not taxonomy.is_known(kind):
            self.unknown.add(kind)

        extractor = _Extractor()
        extractor.walk(action, "")
        self.entities.update(extractor.entities)

        # A jump stores the target stage's id; turn it into the stage's name.
        jumps: list[str] = []
        lookup = dict(extractor.props)
        for key in ("taskReference", "menuReference"):
            target = self.graph.sequence_names.get(lookup.get(key, ""))
            if target:
                jumps.append(target)
                extractor.props.append((key.replace("Reference", ""), target))
        for key in ("taskName", "menuName"):
            name = lookup.get(key)
            if name and name not in jumps and name in self.graph.sequence_names.values():
                jumps.append(name)

        return Node(
            jumps=jumps,
            kind=kind,
            name=str(action.get("name") or taxonomy.label_for(kind)),
            tracking_id=(str(action["trackingId"]) if action.get("trackingId") is not None else None),
            path=str(action.get("id") or ""),
            props=extractor.props,
            speech=extractor.speech,
            dtmf=dtmf,
            raw=action,
        )

    def chain(self, start_id: str | None, stage: str) -> list[Node]:
        """Follow `nextAction` from `start_id`, expanding branches as children."""
        nodes: list[Node] = []
        current = start_id

        while current:
            if current in self.visited:
                if nodes:
                    nodes[-1].jumps.append(self.graph.describe(current))
                break
            action = self.graph.actions.get(current)
            if action is None:
                break

            self.visited.add(current)
            node = self.build_node(action, stage)

            for label, target in self.graph.successors(action):
                if target in self.visited:
                    node.jumps.append(f"{label} → {self.graph.describe(target)}")
                    continue
                if self.graph.owner.get(target) not in (stage, None):
                    node.jumps.append(f"{label} → {self.graph.describe(target)}")
                    continue
                children = self.chain(target, stage)
                if children:
                    node.branches.append(Branch(label=label, nodes=children))

            nodes.append(node)
            nxt = action.get("nextAction")
            current = str(nxt) if nxt else None

        return nodes


# --------------------------------------------------------------------------
# containers
# --------------------------------------------------------------------------

def _stage_speech(sequence: dict) -> tuple[list[Speech], list[tuple[str, str]]]:
    extractor = _Extractor()
    for key in ("prompts", "initialPrompts", "audio"):
        block = sequence.get(key)
        if isinstance(block, dict):
            extractor.walk(block, key)
    return extractor.speech, extractor.props


def _parse_variables(items: list, scope: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("__type") or "")
        extractor = _Extractor()
        extractor.walk(item, "")
        initial = next((v for p, v in extractor.props
                        if p in ("defaultValue", "initialValue", "value")), None)
        description = next((v for p, v in extractor.props if p == "description"), "")
        out.append({
            "name": item.get("name") or "(unnamed)",
            "type": taxonomy.VARIABLE_TYPES.get(kind, taxonomy.prettify(kind)),
            "initial": initial,
            "input": bool(item.get("isInput")),
            "output": bool(item.get("isOutput")),
            "scope": scope,
            "description": description,
        })
    return out


# --------------------------------------------------------------------------
# flow
# --------------------------------------------------------------------------

def _languages(config: dict) -> list[str]:
    langs = config.get("supportedLanguages")
    out: list[str] = []
    if isinstance(langs, list):
        for item in langs:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                out.append(str(item.get("language") or item.get("langCode")
                               or item.get("id") or item.get("name") or item))
    elif isinstance(langs, dict):
        out = sorted(langs.keys())
    return [l for l in out if l]


def manifest_references(config: dict) -> dict[str, list[str]]:
    """Architect ships a manifest of everything the flow depends on, by name."""
    labels = {
        "queue": "Queues", "user": "Users", "group": "Groups",
        "acdSkill": "Skills", "acdLanguage": "Language skills",
        "acdWrapupCode": "Wrap-up codes", "dataAction": "Data actions",
        "dataTable": "Data tables", "schedule": "Schedules",
        "scheduleGroup": "Schedule groups", "emergencyGroup": "Emergency groups",
        "userPrompt": "Recorded prompts", "systemPrompt": "Built-in prompts",
        "botFlow": "Bot flows", "inqueueCallFlow": "In-queue flows",
        "inboundCallFlow": "Inbound flows", "secureCallFlow": "Secure flows",
        "voiceSurveyFlow": "Survey flows", "composerScript": "Agent scripts",
        "audioConnectorBot": "Audio connector bots", "ttsEngine": "Text-to-speech engine",
        "ttsVoice": "Text-to-speech voice", "language": "Languages",
    }
    out: dict[str, list[str]] = {}
    for key, entries in (config.get("manifest") or {}).items():
        if not isinstance(entries, list) or not entries:
            continue
        label = labels.get(key, taxonomy.prettify(key))
        names = []
        for entry in entries:
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("id")
                if name:
                    names.append(str(name))
        if names:
            out.setdefault(label, []).extend(sorted(set(names)))
    return {k: sorted(set(v)) for k, v in sorted(out.items())}


def manifest_names(config: dict) -> dict[str, str]:
    """GUID -> friendly name, straight from the manifest (no API calls needed)."""
    out: dict[str, str] = {}
    for entries in (config.get("manifest") or {}).values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("id") and entry.get("name"):
                out[str(entry["id"])] = str(entry["name"])
    return out


def parse_flow(config: dict, meta: dict | None = None) -> FlowDoc:
    meta = meta or {}
    sequences = [s for s in (config.get("flowSequenceItemList") or []) if isinstance(s, dict)]
    graph = _FlowGraph(sequences)
    walker = _Walker(graph)

    start_stage_id = str(config.get("initialSequence") or "")
    containers: list[Container] = []
    variables: list[dict[str, Any]] = _parse_variables(config.get("variables"), "Flow")

    for sequence in sequences:
        kind = str(sequence.get("__type") or "Task")
        name = str(sequence.get("name") or "Unnamed")
        stage_id = str(sequence.get("id") or "")
        speech, props = _stage_speech(sequence)
        variables.extend(_parse_variables(sequence.get("variables"), name))

        nodes: list[Node] = []
        if kind == "Menu":
            for choice in sequence.get("menuChoiceList") or []:
                action = choice.get("action") if isinstance(choice, dict) else None
                if not isinstance(action, dict):
                    continue
                action_id = str(action.get("id") or "")
                walker.visited.add(action_id)
                node = walker.build_node(action, name, dtmf=str(choice.get("digit") or "") or None)
                node.name = str(choice.get("name") or node.name)
                for label, target in graph.successors(action):
                    if target in walker.visited or graph.owner.get(target) != name:
                        node.jumps.append(f"{label} → {graph.describe(target)}")
                    else:
                        children = walker.chain(target, name)
                        if children:
                            node.branches.append(Branch(label=label, nodes=children))
                nodes.append(node)

            default_choice = sequence.get("defaultMenuChoice")
            if isinstance(default_choice, dict) and isinstance(default_choice.get("action"), dict):
                action = default_choice["action"]
                walker.visited.add(str(action.get("id") or ""))
                node = walker.build_node(action, name, dtmf="(no valid choice)")
                node.name = str(default_choice.get("name") or node.name)
                nodes.append(node)
        else:
            nodes = walker.chain(str(sequence.get("startAction") or "") or None, name)

        # Anything in the stage that the start action cannot reach.
        for action in sequence.get("actionList") or []:
            action_id = str(action.get("id") or "")
            if action_id and action_id not in walker.visited:
                walker.visited.add(action_id)
                orphan = walker.build_node(action, name)
                orphan.unreachable = True
                nodes.append(orphan)

        containers.append(Container(
            kind=kind,
            name=name,
            tracking_id=(str(sequence["trackingId"]) if sequence.get("trackingId") is not None else None),
            ref=stage_id,
            is_start=bool(stage_id and stage_id == start_stage_id),
            props=props,
            speech=speech,
            nodes=nodes,
        ))

    containers.sort(key=lambda c: (not c.is_start,))

    division = meta.get("division")
    if isinstance(division, dict):
        division = division.get("name") or division.get("id")
    published = meta.get("publishedVersion") or {}
    if isinstance(published, dict):
        published = published.get("name") or published.get("id") or ""

    names = manifest_names(config)
    names.update(walker.entities)

    doc = FlowDoc(
        flow_id=str(meta.get("id") or config.get("id") or ""),
        name=str(meta.get("name") or config.get("name") or "Unnamed flow"),
        flow_type=str(meta.get("type") or config.get("type") or "unknown"),
        description=meta.get("description") or config.get("description"),
        division=division,
        published_version=str(published or ""),
        default_language=config.get("defaultLanguage"),
        supported_languages=_languages(config),
        variables=variables,
        containers=containers,
        start_ref=graph.sequence_names.get(start_stage_id),
        references=manifest_references(config),
        name_by_id=names,
        unmapped_kinds=sorted(walker.unknown),
        raw=config,
    )
    return doc
