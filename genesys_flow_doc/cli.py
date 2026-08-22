"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys

from . import (fetch, mermaid, narrate, parse, pdf, render_business, render_html,
               render_technical)
from .client import GenesysClient, GenesysError
from .config import load_dotenv_if_present, parse_console_url, settings_from_env
from .model import FlowDoc

log = logging.getLogger("genesys_flow_doc")


def _formats(args: argparse.Namespace) -> set[str]:
    return {"html", "md"} if args.format == "both" else {args.format}


def slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(name)).strip("-").lower()
    return slug or "flow"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genesys-flow-doc",
        description="Generate business and technical documentation for a Genesys Cloud "
                    "Architect call flow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  # From the URL straight out of the browser (region is inferred from it)
  python -m genesys_flow_doc "https://apps.mypurecloud.ie/directory/#/admin/routing/ivrs/5ffacb01-3ae5-49e9-8e54-58d4f32c76f7"

  # By ID
  python -m genesys_flow_doc --ivr 5ffacb01-3ae5-49e9-8e54-58d4f32c76f7 --region mypurecloud.ie
  python -m genesys_flow_doc --flow 1234abcd-... --narrate

  # Regenerate documents from a previously saved configuration, no API calls
  python -m genesys_flow_doc --offline out/main-ivr.raw.json
""",
    )
    parser.add_argument("url", nargs="?", help="Genesys Cloud admin URL for an IVR or flow")
    parser.add_argument("--url", dest="url_flag", help="same as the positional URL")
    parser.add_argument("--ivr", help="IVR (call route) ID")
    parser.add_argument("--all-ivrs", action="store_true",
                        help="document every call route in the org")
    parser.add_argument("--list", dest="list_only", action="store_true",
                        help="list the org's call routes and exit")
    parser.add_argument("--flow", help="Architect flow ID")
    parser.add_argument("--region", help="e.g. mypurecloud.ie (defaults to $GENESYS_REGION)")
    parser.add_argument("--out", default="out", help="output directory (default: ./out)")
    parser.add_argument("--only", choices=["open", "closed", "holiday"],
                        help="for an IVR, document only one of its flows")
    parser.add_argument("--offline", help="regenerate from a saved .raw.json configuration")
    parser.add_argument("--no-resolve", action="store_true",
                        help="skip queue/data-action/schedule lookups (fewer API calls)")
    parser.add_argument("--format", choices=["html", "md", "both"], default="both",
                        help="which documents to write (default: both)")
    parser.add_argument("--pdf", action="store_true",
                        help="also render each HTML report to PDF (needs Chrome or Edge)")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="force the guided menu (the default when run with no arguments)")
    parser.add_argument("--narrate", action="store_true",
                        help="add a Claude-written executive summary to the business document")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def write_outputs(doc: FlowDoc, out_dir: str, narrate_summary: bool,
                  formats: set[str]) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    slug = slugify(doc.name)
    written: list[str] = []
    diagram = mermaid.render(doc)

    summary = narrate.executive_summary(doc) if narrate_summary else None
    if summary:
        log.info("Added a Claude-written executive summary.")

    targets: dict[str, str] = {}
    if "html" in formats:
        business_html = render_html.render_business(doc)
        if summary:
            business_html = narrate.insert_summary_html(business_html, summary)
        targets[f"{slug}.business.html"] = business_html
        targets[f"{slug}.technical.html"] = render_html.render_technical(doc, diagram)
    if "md" in formats:
        business_md = render_business.render(doc)
        if summary:
            business_md = narrate.insert_summary(business_md, summary)
        targets[f"{slug}.business.md"] = business_md
        targets[f"{slug}.technical.md"] = render_technical.render(doc)
    targets[f"{slug}.flow.mmd"] = diagram
    targets[f"{slug}.raw.json"] = json.dumps(doc.raw, indent=2, ensure_ascii=False)

    for filename, content in targets.items():
        path = os.path.join(out_dir, filename)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        written.append(path)
    return written


def write_index(docs: list[FlowDoc], out_dir: str, region: str) -> str | None:
    """A contents page linking every document produced in this run."""
    if len(docs) < 2:
        return None
    entries = []
    for doc in docs:
        slug = slugify(doc.name)
        entries.append({
            "name": doc.name,
            "route": (doc.ivr or {}).get("name"),
            "dnis": doc.dnis,
            "stages": len(doc.containers),
            "steps": sum(1 for _ in doc.all_nodes()),
            "audio": len(doc.all_speech()),
            "business": f"{slug}.business.html",
            "technical": f"{slug}.technical.html",
        })
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(render_html.render_index(entries, region))
    return path


def _maybe_pdf(written: list[str], args: argparse.Namespace) -> list[str]:
    """Convert any HTML just written to PDF, if the user asked for it."""
    if not getattr(args, "pdf", False):
        return []
    reports = [p for p in written if p.endswith(".html")]
    if not reports:
        return []
    print(f"\nRendering {len(reports)} PDF(s)...")
    pdfs = pdf.convert_all(reports)
    for path in pdfs:
        print(f"  wrote {path}")
    if len(pdfs) < len(reports):
        print(f"  {len(reports) - len(pdfs)} could not be converted "
              f"(run with -v for the reason)")
    return pdfs


Job = tuple  # (role, flow_id, ivr_context, sibling_flows)


def jobs_for_ivr(ivr: dict, only: str | None = None) -> list[Job]:
    flows = fetch.flows_from_ivr(ivr)
    if only:
        wanted = {"open": "Open hours", "closed": "Closed hours",
                  "holiday": "Holiday hours"}[only]
        flows = [f for f in flows if f[0] == wanted]
    siblings = {role: f"{name} (`{fid}`)" for role, fid, name in flows}
    return [(role, fid, ivr, siblings) for role, fid, _name in flows]


def generate(client: GenesysClient, jobs: list[Job], args: argparse.Namespace) -> int:
    """Fetch, parse and write documents for each (role, flow) job."""
    written_total: list[str] = []
    seen_flows: set[str] = set()
    failures: list[tuple[str, str]] = []
    docs: list[FlowDoc] = []

    # Shared across the whole run: the user-prompt index is one full listing,
    # and queue/data-action names repeat heavily between flows.
    prompts = fetch.PromptResolver(client, None)
    ref_cache: dict[str, str] = {}
    schedule_cache: dict[str, list[str]] = {}

    for role, fid, ivr_context, siblings in jobs:
        label = f"{role} flow" if role else "flow"
        if fid in seen_flows:
            log.info("Skipping %s -- already documented in this run", fid)
            continue
        seen_flows.add(fid)
        log.info("Fetching %s %s", label, fid)
        try:
            meta, config = fetch.fetch_flow(client, fid)
            doc = parse.parse_flow(config, meta)
            fetch.enrich(client, doc, ivr=ivr_context, siblings=siblings,
                         resolve_deps=not args.no_resolve, prompts=prompts,
                         ref_cache=ref_cache, schedule_cache=schedule_cache)
            if role:
                doc.description = doc.description or (
                    f"{role} flow for the {(ivr_context or {}).get('name', 'call route')}.")
            written = write_outputs(doc, args.out, args.narrate, _formats(args))
        except Exception as exc:                      # noqa: BLE001 - keep going
            log.warning("Could not document %s (%s): %s", fid, label, exc)
            failures.append((fid, str(exc)))
            continue
        docs.append(doc)
        written_total.extend(written)
        print(f"\n{doc.name} ({label})")
        for path in written:
            print(f"  wrote {path}")

    if "html" in _formats(args):
        index = write_index(docs, args.out, client.settings.region)
        if index:
            written_total.append(index)
            print(f"\n  wrote {index}    <- open this one first")

    written_total.extend(_maybe_pdf(written_total, args))

    print(f"\nDone — {len(written_total)} file(s) in {os.path.abspath(args.out)}")
    if failures:
        print(f"{len(failures)} flow(s) could not be documented:")
        for fid, reason in failures:
            print(f"  {fid}: {reason[:160]}")
    return 0


def generate_for_ivrs(client: GenesysClient, ivrs: list[dict],
                      args: argparse.Namespace) -> int:
    jobs: list[Job] = []
    for entry in ivrs:
        jobs.extend(jobs_for_ivr(entry, args.only))
    print(f"{len(ivrs)} call route(s), {len(jobs)} flow reference(s) to document.")
    return generate(client, jobs, args)


def run(args: argparse.Namespace) -> int:
    load_dotenv_if_present()

    # ---------------------------------------------------------- offline mode
    if args.offline:
        with open(args.offline, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        doc = parse.parse_flow(config)
        doc.fetched_at = "regenerated offline from " + os.path.basename(args.offline)
        written = write_outputs(doc, args.out, args.narrate, _formats(args))
        written.extend(_maybe_pdf(written, args))
        for path in written:
            print(f"wrote {path}")
        return 0

    # --------------------------------------------------- whole-org listings
    if args.list_only or args.all_ivrs:
        client = getattr(args, "_client", None)
        if client is None:
            client = GenesysClient(settings_from_env(args.region))
        settings = client.settings
        ivrs = fetch.list_ivrs(client)
        if args.list_only:
            print(f"{len(ivrs)} call route(s) on {settings.region}\n")
            for entry in ivrs:
                flows = fetch.flows_from_ivr(entry)
                numbers = ", ".join(str(d) for d in (entry.get("dnis") or [])) or "no numbers"
                print(f"- {entry.get('name')}  [{entry.get('id')}]")
                print(f"    numbers: {numbers}")
                for role, fid, fname in flows:
                    print(f"    {role}: {fname}  [{fid}]")
                if not flows:
                    print("    (no flows attached)")
            return 0
        return generate_for_ivrs(client, ivrs, args)

    # ------------------------------------------------------- work out target
    url = args.url_flag or args.url
    target = parse_console_url(url) if url else None
    region = args.region or (target.region if target else None)

    ivr_id = args.ivr or (target.entity_id if target and target.kind == "ivr" else None)
    flow_id = args.flow or (target.entity_id if target and target.kind == "flow" else None)

    if not ivr_id and not flow_id:
        if target and target.entity_id:
            # The URL had an ID but an unrecognised section; try it as an IVR
            # first and fall back to treating it as a flow.
            ivr_id = target.entity_id
        else:
            print("Give a Genesys Cloud URL, or --ivr <id>, or --flow <id>. "
                  "Run with --help for examples.", file=sys.stderr)
            return 2

    client = getattr(args, "_client", None)
    if client is None:
        settings = settings_from_env(region)
        log.info("Region %s (api.%s)", settings.region, settings.region)
        client = GenesysClient(settings)

    jobs: list[Job] = []
    ivr = None

    if ivr_id:
        ivr = fetch.fetch_ivr(client, ivr_id)
        if ivr:
            jobs = jobs_for_ivr(ivr, args.only)
            if not jobs:
                print(f"Call route '{ivr.get('name')}' has no "
                      f"{args.only + '-hours ' if args.only else ''}flow attached.",
                      file=sys.stderr)
                return 1
        else:
            log.info("No IVR with that ID; treating it as a flow ID instead.")
            flow_id = flow_id or ivr_id

    if flow_id and not jobs:
        jobs.append((None, flow_id, None, {}))

    return generate(client, jobs, args)


def main(argv: list[str] | None = None) -> int:
    from .prompt import make_output_utf8

    make_output_utf8()
    supplied = sys.argv[1:] if argv is None else argv
    logging.basicConfig(format="%(levelname)s %(message)s", level=logging.WARNING)

    # No arguments (or an explicit -i) means the guided menu. Anything else is
    # a scripted run and must never stop to ask a question.
    if not supplied or "-i" in supplied or "--interactive" in supplied:
        if not sys.stdin.isatty():
            print("No arguments given and no terminal to ask questions on. "
                  "Run with --help to see the available flags.", file=sys.stderr)
            return 2
        load_dotenv_if_present()
        from . import interactive

        return interactive.main()

    args = build_parser().parse_args(argv)
    logging.getLogger("genesys_flow_doc").setLevel(
        logging.INFO if args.verbose else logging.WARNING)
    try:
        return run(args)
    except GenesysError as exc:
        print(f"\nGenesys API error: {exc}", file=sys.stderr)
        if exc.status in (401, 400):
            print("Check GENESYS_CLIENT_ID / GENESYS_CLIENT_SECRET and that the OAuth "
                  "client uses the Client Credentials grant on this region.", file=sys.stderr)
        if exc.status == 403:
            print("The OAuth client's role needs at least: Architect > Flow > View, "
                  "Architect > UserPrompt > View, Routing > Queue > View, "
                  "Telephony > Plugin > All (for IVR read).", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"\nFile not found: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
