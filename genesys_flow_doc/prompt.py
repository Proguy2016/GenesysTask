"""Small terminal-prompt helpers for the interactive CLI.

Deliberately dependency-free and plain: numbered menus and typed answers work
identically in PowerShell, cmd, Windows Terminal and any POSIX shell, with no
curses, no alternate screen and no assumptions about key handling.

Colour is used only to separate structure from content, and switches itself off
when the output is redirected or when NO_COLOR is set.
"""

from __future__ import annotations

import os
import sys


def make_output_utf8() -> None:
    """Stop Windows' legacy cp1252 console encoding from crashing the run.

    Python picks the ANSI code page for stdout on Windows, which cannot encode
    the box-drawing characters, em dashes and typographic quotes used in the
    menus and in progress output. Switching the stream to UTF-8 fixes it; where
    that is not possible, `errors="replace"` at least keeps the program alive.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


make_output_utf8()


def _can_encode(text: str) -> bool:
    try:
        text.encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


#: Fall back to ASCII where the terminal genuinely cannot render the glyphs.
_UNICODE = _can_encode("─·│┌┐└┘")
LINE = "─" if _UNICODE else "-"
DOT = "·" if _UNICODE else "*"

_ENABLED = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

RESET = "\033[0m" if _ENABLED else ""
BOLD = "\033[1m" if _ENABLED else ""
DIM = "\033[2m" if _ENABLED else ""
ACCENT = "\033[36m" if _ENABLED else ""
WARN = "\033[33m" if _ENABLED else ""
GOOD = "\033[32m" if _ENABLED else ""


class Cancelled(Exception):
    """The user pressed Ctrl-C or Ctrl-D, or chose to go back."""


def _read(prompt_text: str) -> str:
    try:
        return input(prompt_text).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise Cancelled from None


def rule(text: str = "") -> None:
    width = 66
    if text:
        print(f"\n{ACCENT}{'─' * 3} {BOLD}{text}{RESET}{ACCENT} "
              f"{'─' * max(0, width - len(text) - 5)}{RESET}")
    else:
        print(f"{DIM}{'─' * width}{RESET}")


def title(text: str, subtitle: str = "") -> None:
    print(f"\n{BOLD}{text}{RESET}")
    if subtitle:
        print(f"{DIM}{subtitle}{RESET}")


def note(text: str) -> None:
    print(f"{DIM}{text}{RESET}")


def warn(text: str) -> None:
    print(f"{WARN}{text}{RESET}")


def good(text: str) -> None:
    print(f"{GOOD}{text}{RESET}")


def menu(heading: str, options: list[tuple[str, str, str]], default: str | None = None,
         subtitle: str = "") -> str:
    """Show a numbered menu and return the chosen key.

    `options` is a list of (key, label, help text). The user may type the
    number or the key itself.
    """
    title(heading, subtitle)
    print()
    numbered: dict[str, str] = {}
    for index, (key, label, help_text) in enumerate(options, start=1):
        numbered[str(index)] = key
        marker = f"{ACCENT}{index}{RESET}"
        suffix = f"  {DIM}{help_text}{RESET}" if help_text else ""
        star = f" {DIM}(default){RESET}" if key == default else ""
        print(f"  {marker}  {label}{star}{suffix}")
    print()

    valid = {key for key, _, _ in options}
    while True:
        hint = f" [{default}]" if default else ""
        answer = _read(f"  Choose{hint}: ").lower()
        if not answer and default:
            return default
        if answer in numbered:
            return numbered[answer]
        if answer in valid:
            return answer
        warn(f"  '{answer}' is not one of the options. Enter a number from 1 to "
             f"{len(options)}.")


def ask(question: str, default: str = "", validate=None, allow_blank: bool = False) -> str:
    """Ask for a free-text value, re-asking until `validate` accepts it."""
    while True:
        hint = f" {DIM}[{default}]{RESET}" if default else ""
        answer = _read(f"  {question}{hint}: ") or default
        if not answer and not allow_blank:
            warn("  A value is required.")
            continue
        if validate:
            problem = validate(answer)
            if problem:
                warn(f"  {problem}")
                continue
        return answer


def confirm(question: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        answer = _read(f"  {question} [{hint}]: ").lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        warn("  Please answer y or n.")


def pick(heading: str, items: list[tuple[str, str]], page_size: int = 20,
         subtitle: str = "") -> str:
    """Choose one item from a long list, with paging and a text filter.

    `items` is a list of (value, label). Returns the chosen value.
    """
    title(heading, subtitle)
    filtered = items
    page = 0

    while True:
        if not filtered:
            warn("  Nothing matches that filter.")
            filtered = items
            page = 0

        pages = max(1, (len(filtered) + page_size - 1) // page_size)
        page = max(0, min(page, pages - 1))
        window = filtered[page * page_size:(page + 1) * page_size]

        print()
        for index, (_, label) in enumerate(window, start=page * page_size + 1):
            print(f"  {ACCENT}{index:>3}{RESET}  {label}")
        print()
        note(f"  Page {page + 1} of {pages}  {DOT}  {len(filtered)} of {len(items)} shown")

        controls = ["number to select"]
        if pages > 1:
            controls.append("n/p for next/previous page")
        controls.append("/text to filter")
        controls.append("a to show all")
        note("  " + f"  {DOT}  ".join(controls))

        answer = _read("  Choose: ").strip()
        if not answer:
            continue
        lowered = answer.lower()

        if lowered == "n" and pages > 1:
            page += 1
            continue
        if lowered == "p" and pages > 1:
            page -= 1
            continue
        if lowered == "a":
            filtered, page = items, 0
            continue
        if answer.startswith("/"):
            needle = answer[1:].strip().lower()
            filtered = [i for i in items if needle in i[1].lower()] or items
            page = 0
            continue
        if answer.isdigit():
            position = int(answer) - 1
            if 0 <= position < len(filtered):
                return filtered[position][0]
            warn(f"  Pick a number between 1 and {len(filtered)}.")
            continue
        warn("  Unrecognised input.")


def summary(heading: str, rows: list[tuple[str, str]]) -> None:
    rule(heading)
    width = max((len(label) for label, _ in rows), default=0)
    for label, value in rows:
        print(f"  {DIM}{label.rjust(width)}{RESET}  {value}")
    print()
