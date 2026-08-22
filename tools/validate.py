"""Validate parser coverage across every configuration saved in an output dir.

Run:  python tools/validate.py out
"""

from __future__ import annotations

import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesys_flow_doc import parse, taxonomy


def main(out_dir: str) -> int:
    files = sorted(glob.glob(os.path.join(out_dir, "*.raw.json")))
    if not files:
        print(f"No *.raw.json under {out_dir}")
        return 1

    unknown = collections.Counter()
    kinds = collections.Counter()
    empty_flows: list[str] = []
    no_speech: list[str] = []
    anomalies: list[str] = []
    totals = collections.Counter()

    for path in files:
        name = os.path.basename(path).replace(".raw.json", "")
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
        doc = parse.parse_flow(config)

        nodes = list(doc.all_nodes())
        speech = doc.all_speech()
        totals["flows"] += 1
        totals["containers"] += len(doc.containers)
        totals["nodes"] += len(nodes)
        totals["speech"] += len(speech)
        totals["variables"] += len(doc.variables)

        for node in nodes:
            kinds[node.kind] += 1
            if not taxonomy.is_known(node.kind):
                unknown[node.kind] += 1

        if not doc.containers:
            empty_flows.append(f"{name}: no tasks/menus/states found")
        elif not nodes:
            empty_flows.append(f"{name}: {len(doc.containers)} container(s) but no actions")
        if not speech:
            no_speech.append(name)

        # Things that would indicate the parser mis-read the payload.
        if doc.name in ("", "Unnamed flow"):
            anomalies.append(f"{name}: flow name not found")
        unnamed = sum(1 for n in nodes if not n.name)
        if unnamed:
            anomalies.append(f"{name}: {unnamed} action(s) with no name")
        starts = sum(1 for c in doc.containers if c.is_start)
        if doc.containers and starts != 1:
            anomalies.append(f"{name}: {starts} entry points marked (expected 1)")

    print(f"Flows parsed              : {totals['flows']}")
    print(f"Containers (tasks/menus)  : {totals['containers']}")
    print(f"Actions                   : {totals['nodes']}")
    print(f"Pieces of caller audio    : {totals['speech']}")
    print(f"Variables                 : {totals['variables']}")
    print(f"Distinct action types     : {len(kinds)}")
    recognised = sum(c for k, c in kinds.items() if taxonomy.is_known(k))
    pct = 100 * recognised / max(1, totals["nodes"])
    print(f"Actions recognised        : {recognised}/{totals['nodes']}  ({pct:.1f}%)")

    print("\nMost common action types:")
    for kind, count in kinds.most_common(15):
        mark = " " if taxonomy.is_known(kind) else "*"
        print(f"  {mark} {kind:<34} {count}")

    if unknown:
        print(f"\nUnrecognised action types ({len(unknown)} types, "
              f"{sum(unknown.values())} occurrences):")
        for kind, count in unknown.most_common():
            print(f"    {kind:<34} {count}")

    if empty_flows:
        print(f"\nFlows with nothing parsed ({len(empty_flows)}):")
        for line in empty_flows:
            print(f"    {line}")

    if no_speech:
        print(f"\nFlows with no caller audio ({len(no_speech)}): "
              + ", ".join(no_speech[:12]) + ("..." if len(no_speech) > 12 else ""))

    if anomalies:
        print(f"\nAnomalies ({len(anomalies)}):")
        for line in anomalies[:40]:
            print(f"    {line}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "out"))
