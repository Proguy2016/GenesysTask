"""Fetch a flow and everything it depends on, then attach that context."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .client import GenesysClient
from .model import FlowDoc

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# entry points
# --------------------------------------------------------------------------

def fetch_ivr(client: GenesysClient, ivr_id: str) -> dict[str, Any] | None:
    return client.get_optional(f"/api/v2/architect/ivrs/{ivr_id}")


def list_ivrs(client: GenesysClient) -> list[dict[str, Any]]:
    """Every call route in the org, newest listing order preserved."""
    return list(client.paged("/api/v2/architect/ivrs"))


def flows_from_ivr(ivr: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return [(role, flow_id, flow_name)] for every flow the call route uses."""
    roles = [
        ("Open hours", "openHoursFlow"),
        ("Closed hours", "closedHoursFlow"),
        ("Holiday hours", "holidayHoursFlow"),
    ]
    out = []
    for label, key in roles:
        flow = ivr.get(key)
        if isinstance(flow, dict) and flow.get("id"):
            out.append((label, flow["id"], flow.get("name") or flow["id"]))
    return out


def fetch_flow(client: GenesysClient, flow_id: str) -> tuple[dict, dict]:
    """Return (metadata, configuration) for a flow's most recent configuration."""
    meta = client.get_optional(f"/api/v2/flows/{flow_id}") or {"id": flow_id}
    config = client.get(f"/api/v2/flows/{flow_id}/latestconfiguration")

    # Some payloads return a pointer to the configuration rather than the
    # configuration itself.
    if isinstance(config, dict) and "configurationUri" in config and "tasks" not in config:
        config = client.download(config["configurationUri"])
    return meta, config


# --------------------------------------------------------------------------
# prompt resolution -- turning Prompt.foo into the words the caller hears
# --------------------------------------------------------------------------

class PromptResolver:
    def __init__(self, client: GenesysClient, default_language: str | None):
        self.client = client
        self.default_language = (default_language or "en-us").lower()
        self._user_index: dict[str, str] | None = None
        self._system_cache: dict[str, str | None] = {}

    def _pick_resource(self, resources: list[dict]) -> str | None:
        if not resources:
            return None
        ordered = sorted(
            resources,
            key=lambda r: (
                str(r.get("language", "")).lower() != self.default_language,
                not str(r.get("language", "")).lower().startswith("en"),
            ),
        )
        for resource in ordered:
            for field in ("tts", "text"):
                value = (resource.get(field) or "").strip()
                if value:
                    language = resource.get("language") or ""
                    suffix = f"  [{language}]" if language and language.lower() != self.default_language else ""
                    return value + suffix
            if resource.get("filename"):
                return f"(recorded audio: {resource['filename']})"
        return None

    def user(self, name: str) -> str | None:
        if self._user_index is None:
            self._user_index = {}
            log.info("Indexing user prompts...")
            for prompt in self.client.paged("/api/v2/architect/prompts"):
                text = self._pick_resource(prompt.get("resources") or [])
                if prompt.get("name"):
                    self._user_index[prompt["name"]] = text or "(no text or recording found)"
        return self._user_index.get(name)

    def system(self, name: str) -> str | None:
        if name not in self._system_cache:
            payload = self.client.get_optional(
                "/api/v2/architect/systemprompts", {"name": name, "pageSize": 5}
            )
            text = None
            for entity in (payload or {}).get("entities", []):
                if entity.get("name") == name:
                    resources = self.client.get_optional(
                        f"/api/v2/architect/systemprompts/{entity['id']}/resources",
                        {"pageSize": 100},
                    )
                    text = self._pick_resource((resources or {}).get("entities", []))
                    break
            self._system_cache[name] = text
        return self._system_cache[name]

    def resolve(self, doc: FlowDoc) -> None:
        for speech in doc.all_speech():
            if speech.resolved:
                continue
            if speech.kind == "prompt":
                speech.resolved = self.user(speech.value)
            elif speech.kind == "system-prompt":
                speech.resolved = self.system(speech.value)


# --------------------------------------------------------------------------
# schedules
# --------------------------------------------------------------------------

def summarise_schedule_group(client: GenesysClient, group_id: str) -> list[str]:
    group = client.get_optional(f"/api/v2/architect/schedulegroups/{group_id}")
    if not group:
        return []
    lines = [f"Schedule group: **{group.get('name', group_id)}**"]
    for label, key in (("Open", "openSchedules"),
                       ("Closed", "closedSchedules"),
                       ("Holiday", "holidaySchedules")):
        for entry in group.get(key) or []:
            schedule = client.get_optional(f"/api/v2/architect/schedules/{entry['id']}")
            if not schedule:
                lines.append(f"- {label}: {entry.get('name', entry['id'])}")
                continue
            detail = " / ".join(
                str(schedule[f]) for f in ("start", "end", "rrule") if schedule.get(f)
            )
            lines.append(f"- {label}: **{schedule.get('name')}** - {detail or 'no timing detail'}")
    return lines


def enrich(client: GenesysClient, doc: FlowDoc, ivr: dict | None = None,
           siblings: dict[str, str] | None = None, resolve_deps: bool = True,
           prompts: PromptResolver | None = None,
           ref_cache: dict[str, str] | None = None,
           schedule_cache: dict[str, list[str]] | None = None) -> FlowDoc:
    """Attach call-route context and resolve prompt wording.

    Dependencies (queues, data actions, bots, ...) come from the flow's own
    manifest during parsing, so no per-GUID lookups are needed. What still
    requires the API is the *wording* of recorded and built-in prompts, and the
    opening-hours detail behind a call route's schedule group.

    `prompts` and `schedule_cache` are shared across a bulk run: without them a
    60-route org would re-index every prompt in the org once per flow.
    """
    doc.fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc.ivr = ivr
    doc.sibling_flows = siblings or {}

    if ivr:
        doc.dnis = [str(d) for d in (ivr.get("dnis") or [])]
        group_id = (ivr.get("scheduleGroup") or {}).get("id")
        if group_id and resolve_deps:
            if schedule_cache is None:
                doc.schedule_summary = summarise_schedule_group(client, group_id)
            else:
                if group_id not in schedule_cache:
                    schedule_cache[group_id] = summarise_schedule_group(client, group_id)
                doc.schedule_summary = schedule_cache[group_id]

    if resolve_deps:
        resolver = prompts or PromptResolver(client, doc.default_language)
        resolver.resolve(doc)
    return doc
