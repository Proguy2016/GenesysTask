"""The guided, menu-driven front end.

Runs when the tool is started with no arguments. It asks what to document, how
to identify it, and which outputs to produce, then hands a fully-populated
argument namespace to exactly the same code the flag-driven CLI uses -- so the
interactive and scripted paths cannot drift apart.

Every question has a sensible default, and the run is summarised for
confirmation before a single API call is made.
"""

from __future__ import annotations

import argparse
import glob
import os

from . import fetch, pdf, prompt
from .client import GenesysClient, GenesysError
from .config import KNOWN_REGIONS, normalise_region, settings_from_env
from .prompt import Cancelled

UNICODE_BANNER = """
  ┌────────────────────────────────────────────────────────────┐
  │  GENESYS CLOUD  ·  call flow documentation generator       │
  └────────────────────────────────────────────────────────────┘"""

ASCII_BANNER = """
  +------------------------------------------------------------+
  |  GENESYS CLOUD  -  call flow documentation generator        |
  +------------------------------------------------------------+"""


def _banner() -> str:
    return UNICODE_BANNER if prompt._UNICODE else ASCII_BANNER


def _defaults() -> argparse.Namespace:
    """A namespace matching the flag parser's defaults, filled in as we go."""
    return argparse.Namespace(
        url=None, url_flag=None, ivr=None, flow=None, all_ivrs=False, list_only=False,
        region=None, out="out", only=None, offline=None, no_resolve=False,
        format="both", pdf=False, narrate=False, verbose=False, interactive=True,
    )


# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------

def _choose_region(args: argparse.Namespace) -> None:
    current = os.environ.get("GENESYS_REGION", "mypurecloud.ie")
    if prompt.confirm(f"Use region {current}?", default=True):
        args.region = current
        return
    prompt.note("  Known regions: " + ", ".join(KNOWN_REGIONS))
    args.region = prompt.ask(
        "Region domain", default=current,
        validate=lambda v: None if _region_ok(v) else "That is not a valid region domain.")


def _region_ok(value: str) -> bool:
    try:
        normalise_region(value)
        return True
    except SystemExit:
        return False


def _connect(args: argparse.Namespace) -> GenesysClient:
    settings = settings_from_env(args.region)
    prompt.note(f"  Connecting to api.{settings.region} ...")
    client = GenesysClient(settings)
    client._auth_header()          # fail fast on bad credentials, before any menus
    prompt.good("  Connected.")
    return client


def _choose_target(args: argparse.Namespace, client_factory) -> GenesysClient | None:
    """Work out what to document. Returns a live client if one was needed."""
    how = prompt.menu(
        "How would you like to identify it?",
        [
            ("browse", "Pick from a list of the organisation's call routes",
             "fetches the list for you"),
            ("url", "Paste a Genesys Cloud admin URL", "region is read from the URL"),
            ("ivr", "Enter a call route (IVR) ID", "a GUID"),
            ("flow", "Enter an Architect flow ID", "a GUID"),
        ],
        default="browse",
    )

    if how == "url":
        args.url = prompt.ask(
            "Paste the URL",
            validate=lambda v: None if "http" in v else "That does not look like a URL.")
        return None

    if how == "ivr":
        _choose_region(args)
        args.ivr = prompt.ask("Call route (IVR) ID", validate=_guid_check)
        return None

    if how == "flow":
        _choose_region(args)
        args.flow = prompt.ask("Architect flow ID", validate=_guid_check)
        return None

    # browse
    _choose_region(args)
    client = client_factory(args)
    prompt.note("  Fetching call routes ...")
    ivrs = fetch.list_ivrs(client)
    if not ivrs:
        prompt.warn("  This organisation has no call routes.")
        raise Cancelled
    items = []
    for entry in ivrs:
        flows = fetch.flows_from_ivr(entry)
        numbers = ", ".join(str(d) for d in (entry.get("dnis") or [])) or "no numbers"
        detail = f"{len(flows)} flow(s), {numbers}"
        items.append((entry["id"], f"{entry.get('name', '(unnamed)'):<42} {detail}"))
    args.ivr = prompt.pick("Select a call route", items,
                           subtitle=f"{len(items)} call routes in this organisation")
    return client


def _guid_check(value: str) -> str | None:
    cleaned = value.strip()
    if len(cleaned) == 36 and cleaned.count("-") == 4:
        return None
    return "That does not look like a GUID (8-4-4-4-12 hex characters)."


def _choose_which_flows(args: argparse.Namespace) -> None:
    args.only = prompt.menu(
        "Which of the call route's flows?",
        [
            ("all", "All of them", "open, closed and holiday hours"),
            ("open", "Open hours only", ""),
            ("closed", "Closed hours only", ""),
            ("holiday", "Holiday hours only", ""),
        ],
        default="all",
    )
    if args.only == "all":
        args.only = None


def _choose_outputs(args: argparse.Namespace, offline: bool = False) -> None:
    prompt.rule("Output options")
    args.format = prompt.menu(
        "Which documents should be written?",
        [
            ("both", "HTML and Markdown", "HTML to hand over, Markdown for wikis"),
            ("html", "HTML only", "self-contained, print-ready"),
            ("md", "Markdown only", "for Confluence, git diffs"),
        ],
        default="both",
    )

    if args.format in ("html", "both"):
        renderer = pdf.find_browser()
        if renderer:
            args.pdf = prompt.confirm(
                f"Also produce PDFs? (using {os.path.basename(renderer)})", default=True)
        else:
            prompt.note("  PDF export needs Chrome or Edge installed; skipping that option.")

    args.out = prompt.ask("Output directory", default=args.out)

    prompt.rule("Detail options")
    if offline:
        # Nothing to look up: a saved configuration is all there is.
        args.no_resolve = True
    else:
        args.no_resolve = not prompt.confirm(
            "Look up prompt wording and opening hours? (slower, but the documents "
            "quote what callers actually hear)", default=True)

    if os.environ.get("ANTHROPIC_API_KEY"):
        args.narrate = prompt.confirm(
            "Add an AI-written executive summary to each business document?", default=False)

    args.verbose = prompt.confirm("Show detailed progress?", default=False)


def _offline_flow(args: argparse.Namespace) -> argparse.Namespace | None:
    saved = sorted(glob.glob(os.path.join(args.out, "*.raw.json")))
    if saved:
        items = [(path, os.path.basename(path).replace(".raw.json", "")) for path in saved]
        items.insert(0, ("__typed__", "Enter a different path..."))
        chosen = prompt.pick("Which saved configuration?", items,
                             subtitle=f"found in {os.path.abspath(args.out)}")
        args.offline = (prompt.ask("Path to the .raw.json file")
                        if chosen == "__typed__" else chosen)
    else:
        prompt.note(f"  No saved configurations found in {os.path.abspath(args.out)}.")
        args.offline = prompt.ask(
            "Path to a .raw.json file",
            validate=lambda v: None if os.path.isfile(v) else "No file at that path.")
    _choose_outputs(args, offline=True)
    return args


def _pdf_only_flow(args: argparse.Namespace) -> None:
    """Convert already-generated HTML reports without touching the API."""
    directory = prompt.ask("Directory containing the HTML reports", default=args.out)
    reports = sorted(glob.glob(os.path.join(directory, "*.html")))
    if not reports:
        prompt.warn(f"  No .html files in {os.path.abspath(directory)}.")
        return

    scope = prompt.menu(
        f"{len(reports)} report(s) found. Convert which?",
        [("all", "All of them", ""),
         ("one", "Just one", "pick from the list")],
        default="all",
    )
    targets = reports
    if scope == "one":
        items = [(path, os.path.basename(path)) for path in reports]
        targets = [prompt.pick("Which report?", items)]

    renderer = pdf.find_browser()
    prompt.note(f"  Rendering with {os.path.basename(renderer) if renderer else 'the available engine'} ...")
    written = pdf.convert_all(targets)
    for path in written:
        print(f"  wrote {path}")
    prompt.good(f"\n  {len(written)} of {len(targets)} converted.")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def _confirm_run(args: argparse.Namespace) -> bool:
    rows: list[tuple[str, str]] = []
    if args.offline:
        rows.append(("Source", f"saved file {args.offline}"))
    elif args.all_ivrs:
        rows.append(("Source", "every call route in the organisation"))
    elif args.ivr:
        rows.append(("Source", f"call route {args.ivr}"))
    elif args.flow:
        rows.append(("Source", f"flow {args.flow}"))
    elif args.url:
        rows.append(("Source", args.url))
    if args.region:
        rows.append(("Region", args.region))
    if args.only:
        rows.append(("Flows", f"{args.only} hours only"))
    rows.append(("Documents", {"both": "HTML + Markdown", "html": "HTML",
                               "md": "Markdown"}[args.format]))
    rows.append(("PDF", "yes" if args.pdf else "no"))
    rows.append(("Output", os.path.abspath(args.out)))
    rows.append(("Prompt lookups", "no" if args.no_resolve else "yes"))
    if args.narrate:
        rows.append(("AI summary", "yes"))

    prompt.summary("About to run", rows)
    return prompt.confirm("Go ahead?", default=True)


def session() -> argparse.Namespace | None:
    """Run the guided flow. Returns args to execute, or None if the user quit."""
    print(prompt.ACCENT + _banner() + prompt.RESET)
    prompt.note("  Read-only: this tool never modifies anything in Genesys Cloud.")

    args = _defaults()
    client: GenesysClient | None = None

    while True:
        action = prompt.menu(
            "What would you like to do?",
            [
                ("all", "Document every call route in the organisation",
                 "one document set per flow, plus a contents page"),
                ("one", "Document a single call route or flow", ""),
                ("list", "Browse the organisation's call routes", "just show them, no files"),
                ("offline", "Rebuild documents from a saved configuration",
                 "no API calls, no credentials needed"),
                ("pdf", "Convert existing HTML reports to PDF", "no API calls"),
                ("quit", "Quit", ""),
            ],
            default="one",
        )

        if action == "quit":
            return None

        if action == "pdf":
            _pdf_only_flow(args)
            continue

        if action == "offline":
            return _offline_flow(args)

        if action == "list":
            _choose_region(args)
            args.list_only = True
            return args

        if action == "all":
            args.all_ivrs = True
            _choose_region(args)
            _choose_which_flows(args)
            _choose_outputs(args)
            if _confirm_run(args):
                return args
            args = _defaults()
            continue

        # single call route or flow
        client = _choose_target(args, _connect)
        if args.ivr or args.url:
            _choose_which_flows(args)
        _choose_outputs(args)
        if _confirm_run(args):
            args._client = client        # reuse the connection we already opened
            return args
        args = _defaults()


def main() -> int:
    """Wrapper that turns cancellation and credential problems into clean exits."""
    from .cli import run

    try:
        args = session()
    except Cancelled:
        print("\nCancelled.")
        return 130
    if args is None:
        print("\nNothing to do.")
        return 0

    import logging
    logging.getLogger("genesys_flow_doc").setLevel(
        logging.INFO if args.verbose else logging.WARNING)

    try:
        return run(args)
    except GenesysError as exc:
        prompt.warn(f"\nGenesys API error: {exc}")
        return 1
    except Cancelled:
        print("\nCancelled.")
        return 130
