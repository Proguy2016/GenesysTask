"""Pull the words a caller actually hears out of Architect audio expressions.

Architect stores audio as an expression plus a structured breakdown of it.
The expression looks like:

    AudioPlaybackOptions(ToAudioTTS("Welcome to Acme."), true)
    ToAudioPrompt(Prompt.mainGreeting)
    Append(ToAudioTTS("You are caller number "), ToAudioNumber(Flow.position))

and alongside it Architect stores `uiMetaData.sequenceItems`, which is the same
content already broken into pieces:

    {"type": 0, "parameter": "Welcome to Acme."}                 literal speech
    {"type": 1, "name": "PromptSystem.voicemail_greeting"}       prompt reference
    {"type": 2, "expressionFormat": "ToAudioNumber(%s, ...)"}    a value read out
    {"type": 3, "model": {...}}                                  dynamic expression
    {"type": 4, "parameter": 500}                                a pause, in ms

The structured form is used when present because it is exact; the expression is
parsed as a fallback so nothing is missed when Architect omits the breakdown.
"""

from __future__ import annotations

import re

from .model import Speech

_STRING_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')
_USER_PROMPT = re.compile(r"\bPrompt\.([A-Za-z0-9_]+)")
_SYSTEM_PROMPT = re.compile(r"\bPromptSystem\.([A-Za-z0-9_]+)")

# sequenceItems type codes
TTS_TEXT, PROMPT_REF, VALUE_READOUT, DYNAMIC, PAUSE = 0, 1, 2, 3, 4


def _clean(text: object) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def from_sequence_items(items: list, path: str) -> list[Speech]:
    """Read Architect's own structured breakdown of an audio expression."""
    out: list[Speech] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        code = item.get("type")

        if code == TTS_TEXT:
            text = _clean(item.get("parameter", ""))
            if text:
                out.append(Speech(kind="tts", value=text, where=path))

        elif code == PROMPT_REF:
            name = str(item.get("expressionName") or item.get("name") or "").strip()
            bare = name.split(".")[-1] or name
            kind = "system-prompt" if item.get("isSystem") or name.startswith("PromptSystem.") \
                else "prompt"
            if bare:
                out.append(Speech(kind=kind, value=bare, where=path))

        elif code == VALUE_READOUT:
            fmt = str(item.get("expressionFormat") or "").strip()
            hint = "a number" if "Number" in fmt else "a value from the call"
            out.append(Speech(kind="dynamic", value=f"({hint} read out to the caller)",
                              where=path))

        elif code == DYNAMIC:
            model = item.get("model") or {}
            text = _clean(model.get("text") or "")
            out.append(Speech(kind="dynamic",
                              value=f"(audio chosen at runtime: {text})" if text
                              else "(audio chosen at runtime)",
                              where=path))

        elif code == PAUSE:
            try:
                millis = int(item.get("parameter") or 0)
            except (TypeError, ValueError):
                millis = 0
            if millis:
                out.append(Speech(kind="pause", value=f"(pause of {millis / 1000:g} seconds)",
                                  where=path))
    return out


def from_expression(expression: str, path: str) -> list[Speech]:
    """Fallback: parse the audio expression text itself."""
    out: list[Speech] = []
    if not isinstance(expression, str) or not expression.strip():
        return out

    if "ToAudioTTS" in expression or "ToPhonetic" in expression:
        for literal in _STRING_LITERAL.findall(expression):
            text = _clean(literal.replace('\\"', '"'))
            if text:
                out.append(Speech(kind="tts", value=text, where=path))
    for name in _USER_PROMPT.findall(expression):
        out.append(Speech(kind="prompt", value=name, where=path))
    for name in _SYSTEM_PROMPT.findall(expression):
        out.append(Speech(kind="system-prompt", value=name, where=path))

    if not out:
        out.append(Speech(kind="dynamic", value=f"(audio expression: {_clean(expression)})",
                          where=path))
    return out


def from_audio_value(value: dict, path: str) -> list[Speech]:
    """Extract speech from one Architect audio value object (`type: "aud"`)."""
    if not isinstance(value, dict):
        return []
    items = ((value.get("uiMetaData") or {}).get("sequenceItems")) or []
    if items:
        return from_sequence_items(items, path)
    return from_expression(value.get("text") or "", path)


def dedupe(items: list[Speech]) -> list[Speech]:
    """Collapse repeats while preserving the order they are spoken in."""
    seen: set[tuple[str, str]] = set()
    out: list[Speech] = []
    for item in items:
        key = (item.kind, item.spoken())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def audible(items: list[Speech]) -> list[Speech]:
    """Only the entries that represent actual words, for the verbatim script."""
    return [i for i in items if i.kind in ("tts", "text") or i.resolved]
