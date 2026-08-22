"""Business document: what a caller experiences and what the business rules are.

Deliberately free of Architect jargon, GUIDs and expression syntax. Anything a
non-technical reader cannot act on belongs in the technical document instead.
"""

from __future__ import annotations

import re

from . import taxonomy
from .model import FlowDoc, Node, Speech
from .speech import dedupe

MAX_QUOTE = 400
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

#: Strips the trailing `` (`guid`) `` from a sibling-flow label.
_STRIP_ID = re.compile(r"\s*`[^`]+`")


def _quote(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    if len(text) > MAX_QUOTE:
        text = text[: MAX_QUOTE - 1].rstrip() + "…"
    return text


def _cell(text: object) -> str:
    if text is None:
        return "—"
    return str(text).replace("|", "\\|").replace("\n", " ").strip() or "—"


def _prop(node: Node, *hints: str) -> str | None:
    """The configured value for the first matching property path.

    Exact matches win over partial ones, so asking for `transferTarget` does not
    accidentally return `transferTargetType`. A trailing list index is ignored,
    so `queues` matches `queues[0]`.
    """
    candidates = [(re.sub(r"\[\d+\]$", "", path).lower(), value) for path, value in node.props]

    def usable(value: str) -> str | None:
        clean = value.lstrip("= ").strip().strip('"')
        return clean if clean and clean != "(not set)" else None

    for hint in hints:
        for path, value in candidates:
            if path == hint and usable(value):
                return usable(value)
    for hint in hints:
        for path, value in candidates:
            if hint in path and usable(value):
                return usable(value)
    return None


def _friendly(value: str | None, names: dict[str, str] | None) -> str | None:
    """Turn 'Queue.Sales' or a bare GUID into something a reader recognises."""
    if not value:
        return None
    value = re.sub(r"^(Queue|Group|User|Skill|Flow|Prompt)\.", "", value).strip()
    if GUID.match(value):
        return (names or {}).get(value)      # None when the name is unknown
    return value


def hearing(item: Speech) -> str:
    """How to present one piece of audio to a business reader."""
    if item.resolved:
        return f'The caller hears: *"{_quote(item.resolved)}"*'
    if item.kind == "prompt":
        return (f"The caller hears the recorded prompt **{item.value}** "
                f"*(wording not stored as text — listen to it in Architect)*")
    if item.kind == "system-prompt":
        return f"The caller hears the standard Genesys prompt **{item.value}**"
    if item.kind in ("dynamic", "pause"):
        return f"The caller hears {item.value.strip('()')}"
    return f'The caller hears: *"{_quote(item.value)}"*'


def _count(node: Node, prefix: str) -> int:
    seen = {path.split("[")[0] + path[path.find("["):path.find("]") + 1]
            for path, _ in node.props if path.startswith(prefix) and "[" in path}
    return len(seen)


def describe(node: Node, names: dict[str, str] | None = None) -> str:
    """One sentence describing this step from the caller's point of view."""
    kind = node.kind

    if kind in ("TransferPureMatchAction", "TransferAcdAction"):
        queue = _friendly(_prop(node, "queues"), names)
        return (f"The call is placed in the **{queue}** queue to be answered by an agent."
                if queue else "The call is placed in a queue to be answered by an agent.")
    if kind == "TransferUserAction":
        user = _friendly(_prop(node, "user", "transfertarget"), names)
        return (f"The call is transferred to **{user}**." if user
                else "The call is transferred to a named person.")
    if kind == "TransferGroupAction":
        group = _friendly(_prop(node, "transfertargetgroup", "group"), names)
        return (f"The call is transferred to the **{group}** group." if group
                else "The call is transferred to a group.")
    if kind == "TransferExternalAction":
        number = _prop(node, "externalnumber", "number", "address")
        return (f"The call is transferred to the external number **{number}**." if number
                else "The call is transferred to an external number.")
    if kind in ("TransferVoicemailAction", "TransferAcdVoicemailAction"):
        target = (_friendly(_prop(node, "transfertargetqueue"), names)
                  or _friendly(_prop(node, "transfertargetgroup"), names)
                  or _friendly(_prop(node, "transfertarget"), names))
        return (f"The caller is sent to voicemail for **{target}** to leave a message."
                if target else "The caller is sent to voicemail to leave a message.")
    if kind in ("TransferFlowAction", "TransferFlowSecureAction"):
        flow = _friendly(_prop(node, "flowname"), names)
        secure = " secure" if "Secure" in kind else ""
        return (f"The call is handed to the **{flow}**{secure} call flow." if flow
                else f"The call is handed to another{secure} call flow.")
    if kind == "DisconnectAction":
        return "The call ends."
    if kind in ("EndTaskAction", "EndStateAction", "EndWorkflowAction"):
        return "This stage of the call finishes."

    if kind == "DecisionAction":
        condition = _prop(node, "expression")
        return (f"A check is made: `{condition}`." if condition
                else "A check is made and the call takes one of two paths.")
    if kind == "SwitchAction":
        cases = len(node.branches) or _count(node, "cases")
        return (f"The call takes one of {cases} paths depending on a value." if cases
                else "The call takes one of several paths depending on a value.")
    if kind == "EvaluateScheduleAction":
        schedule = _prop(node, "schedule")
        return (f"The call is checked against the **{schedule}** opening-hours schedule."
                if schedule else "The call is checked against an opening-hours schedule.")
    if kind == "EvaluateScheduleGroupAction":
        group = _prop(node, "schedulegroup")
        return (f"The **{group}** schedule decides whether the business is open, closed or on holiday."
                if group else "The opening-hours schedule decides whether the business is open.")
    if kind == "LoopAction":
        count = _prop(node, "loopcount")
        return f"The following steps repeat up to {count} times." if count \
            else "The following steps repeat."
    if kind in ("ExitLoopAction", "NextLoopAction"):
        return taxonomy.business_for(kind)

    if kind == "DataAction":
        action = _prop(node, "actionname")
        return (f"The **{action}** integration is called to look information up in an "
                f"external system." if action
                else "An external system is called to look information up.")
    if kind == "DataTableLookupAction":
        table = _prop(node, "datatablename")
        return (f"A value is looked up in the **{table}** data table." if table
                else "A value is looked up in a data table.")
    if kind == "SetAttributesAction":
        count = _count(node, "attributes") or _count(node, "inputs")
        return (f"{count} piece(s) of information are attached to the call so agents and "
                f"reports can see them." if count
                else "Information is attached to the call so agents and reports can see it.")
    if kind == "UpdateVariableAction":
        count = _count(node, "statements") or _count(node, "updateStatements")
        return (f"{count} value(s) used later in the flow are set." if count
                else "Values used later in the flow are set.")
    if kind == "GetAttributesAction":
        return "Information already attached to the call is read back."
    if kind == "CollectInputAction":
        target = _prop(node, "resultdata")
        digits = _prop(node, "numberofdigitsmax")
        detail = f" (up to {digits} digit(s))" if digits else ""
        return (f"The caller is asked to key in a value{detail}, stored as `{target}`."
                if target else f"The caller is asked to key in a value{detail}.")
    if kind == "SetLocaleAction":
        language = _prop(node, "languagecode")
        return (f"Prompts switch to **{language}** from here on." if language
                else "The language used for prompts is switched.")
    if kind == "ScreenPopAction":
        script = _prop(node, "screenpopname")
        return (f"The **{script}** script is prepared for the agent's screen when they answer."
                if script else "Information is prepared for the agent's screen.")
    if kind == "SetWrapupCodeAction":
        code = _prop(node, "wrapupcode")
        return (f"The wrap-up code **{code}** is recorded against the call." if code
                else "A wrap-up code is recorded against the call.")
    if kind == "SetPostFlowAction":
        survey = _prop(node, "voicesurveyflowname", "flowname")
        return (f"After the call, the **{survey}** survey runs." if survey
                else "A follow-up flow is arranged for after the call.")
    if kind in ("GetSIPHeadersAction", "GetRawSIPHeadersAction"):
        return "Technical details supplied by the phone carrier are read."
    if kind == "TranscriptionAction":
        on = _prop(node, "enabletranscription")
        return f"Call transcription is turned {'on' if on == 'yes' else 'off'}."
    if kind == "AudioMonitoringAction":
        on = _prop(node, "enablemonitoring")
        return f"Audio monitoring is turned {'on' if on == 'yes' else 'off'}."
    if kind == "SetExternalTagAction":
        return "The call is tagged with an external reference for reporting."
    if kind == "FindSkillAction":
        skill = _prop(node, "findname")
        return f"The agent skill {skill} is looked up." if skill else "An agent skill is looked up."
    if kind == "FindQueueAction":
        return "A queue is looked up by name."

    if kind in ("CallBotFlowAction", "CallBotAction", "CallDigitalBotFlowAction",
                "CallDialogEngineBotAction", "CallLexBotAction", "CallLexV2BotAction"):
        bot = _prop(node, "flowname", "botname")
        return (f"The caller is handed to the **{bot}** automated assistant." if bot
                else "The caller is handed to an automated assistant.")
    if kind == "CallAudioConnectorAction":
        connector = _prop(node, "integrationname")
        return (f"The call audio is streamed to **{connector}** for an external voice bot."
                if connector else "The call audio is streamed to an external voice bot.")

    if kind in ("TaskAction", "TransferTaskAction", "TransferMenuAction", "MenuAction"):
        target = node.jumps[0] if node.jumps else _prop(node, "taskname", "menuname")
        word = "menu" if "Menu" in kind else "stage"
        return (f"The call continues at the **{target}** {word}." if target
                else f"The call continues at another {word}.")
    if kind == "PreviousMenuAction":
        return "The caller is taken back to the previous menu."

    return taxonomy.business_for(kind)


def _narrate(node: Node, out: list[str], names: dict[str, str], indent: int = 0) -> None:
    pad = "  " * indent
    out.append(f"{pad}- **{node.name}** — {describe(node, names)}")
    for item in dedupe(node.speech):
        out.append(f"{pad}  - {hearing(item)}")
    for branch in node.branches:
        if not branch.nodes:
            continue
        label = f"After the caller presses {node.dtmf}" if node.dtmf else branch.label
        out.append(f"{pad}  - *{label}:*")
        for child in branch.nodes:
            _narrate(child, out, names, indent + 2)


def _endpoints(doc: FlowDoc) -> list[str]:
    """Every way a call can leave this flow, in plain English."""
    seen: dict[str, None] = {}
    for node in doc.all_nodes():
        if taxonomy.category_for(node.kind) in ("routing", "terminal"):
            seen.setdefault(describe(node, doc.name_by_id), None)
    return list(seen)


def _menu_options(doc: FlowDoc) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for container in doc.containers:
        for node in container.walk():
            if node.dtmf:
                rows.append((node.dtmf, container.name, node.name,
                             describe(node, doc.name_by_id)))
    return sorted(rows, key=lambda r: (not r[0].isdigit(), r[0]))


def render(doc: FlowDoc) -> str:
    names = doc.name_by_id
    out: list[str] = []
    out.append(f"# How the “{doc.name}” call flow works")
    out.append("")
    out.append("*A plain-English description of what callers experience and what the "
               "business rules are. For configuration detail, see the accompanying "
               "technical specification.*")
    out.append("")
    out.append(f"*Taken from the live Genesys Cloud configuration on {doc.fetched_at or 'unknown date'}.*")

    # ------------------------------------------------------------ at a glance
    out.append("")
    out.append("## At a glance")
    out.append("")
    out.append("| | |")
    out.append("| --- | --- |")
    out.append(f"| **What it is** | {_cell(doc.description or taxonomy.prettify(doc.flow_type) + ' flow')} |")
    if doc.dnis:
        out.append(f"| **Numbers callers dial** | {_cell(', '.join(doc.dnis))} |")
    if doc.ivr:
        out.append(f"| **Call route** | {_cell(doc.ivr.get('name'))} |")
    for role, target in doc.sibling_flows.items():
        # Computed outside the f-string: a backslash inside an f-string
        # expression is a syntax error before Python 3.12.
        without_id = _STRIP_ID.sub("", target)
        out.append(f"| **{role}** | {_cell(without_id)} |")
    out.append(f"| **Language** | {_cell(doc.default_language)} |")
    out.append(f"| **Menus and stages** | {len(doc.containers)} |")
    out.append(f"| **Steps in total** | {sum(1 for _ in doc.all_nodes())} |")

    if doc.schedule_summary:
        out.append("")
        out.append("### When this flow runs")
        out.append("")
        out.extend(doc.schedule_summary)

    # -------------------------------------------------------- where calls go
    endpoints = _endpoints(doc)
    out.append("")
    out.append("## Where calls end up")
    out.append("")
    if endpoints:
        for line in endpoints:
            out.append(f"- {line}")
    else:
        out.append("This flow does not transfer or end calls directly.")

    # --------------------------------------------------------- menu options
    options = _menu_options(doc)
    if options:
        out.append("")
        out.append("## Menu options offered to callers")
        out.append("")
        out.append("| Caller presses | Menu | Option | What happens |")
        out.append("| --- | --- | --- | --- |")
        for key, menu, name, what in options:
            out.append(f"| **{_cell(key)}** | {_cell(menu)} | {_cell(name)} | {_cell(what)} |")

    # ------------------------------------------------------------- journey
    out.append("")
    out.append("## The caller's journey, step by step")
    out.append("")
    for container in doc.containers:
        marker = " *(this is where every call starts)*" if container.is_start else ""
        out.append("")
        out.append(f"### {container.name}{marker}")
        out.append("")
        for item in dedupe(container.speech):
            out.append(f"- {hearing(item)}")
        if not container.nodes:
            out.append("- No steps are configured here.")
        for node in container.nodes:
            _narrate(node, out, names)

    # -------------------------------------------------------------- script
    speech = dedupe(doc.all_speech())
    spoken = [s for s in speech if s.resolved or s.kind in ("tts", "text")]
    out.append("")
    out.append("## Everything the caller hears, word for word")
    out.append("")
    if spoken:
        out.append("Use this section to review wording, translations or brand tone. Each line "
                   "is exactly what is played or spoken.")
        out.append("")
        for item in spoken:
            out.append(f'- *"{_quote(item.resolved or item.value)}"*')
    else:
        out.append("No caller-facing wording could be read from this flow.")

    unspoken = [s for s in speech if s not in spoken]
    if unspoken:
        out.append("")
        out.append("Audio whose wording is not stored as text in the flow:")
        out.append("")
        for item in unspoken:
            if item.kind in ("dynamic", "pause"):
                out.append(f"- {_cell(item.value.strip('()').capitalize())}")
            else:
                kind = {"prompt": "recorded prompt",
                        "system-prompt": "standard Genesys prompt"}.get(item.kind, item.kind)
                out.append(f"- **{item.value}** ({kind})")

    # --------------------------------------------------------- dependencies
    business_refs = {k: v for k, v in doc.references.items()
                     if k in ("Queues", "Data actions", "Data tables", "Other flows",
                              "External numbers", "Groups", "Schedule groups", "Skills")}
    out.append("")
    out.append("## What this flow relies on")
    out.append("")
    if business_refs:
        for label, values in business_refs.items():
            cleaned = [re.sub(r"\s*`[0-9a-fA-F-]{36}`", "", value).strip() for value in values]
            out.append(f"- **{label}:** " + ", ".join(sorted(set(cleaned))))
    else:
        out.append("No external queues, systems or data sources were detected "
                   "(dependency lookup is skipped in offline mode and with `--no-resolve`).")

    # ------------------------------------------------------- things to check
    unresolved = [s for s in speech if s.kind in ("prompt", "system-prompt") and not s.resolved]
    out.append("")
    out.append("## Points to confirm with the flow owner")
    out.append("")
    checks: list[str] = []
    if unresolved:
        listed = ", ".join(sorted({s.value for s in unresolved}))
        checks.append(f"These prompts are recorded audio with no stored text, so their wording "
                      f"should be confirmed by listening to them: {listed}.")
    if doc.unmapped_kinds:
        checks.append("Some steps use Architect features this summary describes only "
                      "generically — see section 7 of the technical specification.")
    if doc.ivr and not doc.dnis:
        checks.append("No phone numbers are currently attached to this call route.")
    if not checks:
        checks.append("Nothing outstanding — every step, prompt and destination was resolved.")
    for check in checks:
        out.append(f"- {check}")

    return "\n".join(out) + "\n"
