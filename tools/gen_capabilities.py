#!/usr/bin/env python3
"""Generate deterministic capability views from Canonical/capabilities.json.

Reads Canonical/capabilities.json (264 records sorted by Capability ID)
plus Canonical/v4.2-preservation.csv (264 rows). Writes
Canonical/generated/: by-category.md, by-route.md,
preservation-matrix.csv, SHA256SUMS.txt.

Byte-deterministic: explicit sorting everywhere, LF newlines, UTF-8, no
timestamps, no locale dependence. Exit nonzero on any error.
"""

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Canonical" / "capabilities.json"
MATRIX = ROOT / "Canonical" / "v4.2-preservation.csv"
OUTDIR = ROOT / "Canonical" / "generated"

HEADER = (
    "<!-- Generated from Canonical/capabilities.json; do not edit. -->\n"
)


def load_records():
    try:
        text = SOURCE.read_text(encoding="utf-8")
    except OSError as exc:
        print("gen_capabilities: cannot read %s: %s" % (SOURCE, exc))
        return None
    try:
        records = json.loads(text)
    except ValueError as exc:
        print("gen_capabilities: unparseable %s: %s" % (SOURCE, exc))
        return None
    if not isinstance(records, list):
        print("gen_capabilities: %s is not a list" % SOURCE)
        return None
    return records


def route_key(record):
    """Deterministic route bucket: Category + first Normative Home token."""
    category = (record.get("Category") or "").strip()
    home = (record.get("Normative Home") or "").strip()
    first = home.split(" and ")[0].split(",")[0].strip()
    return "%s :: %s" % (category, first)


def render_category(records):
    lines = [HEADER, "# Capabilities by Category", ""]
    groups = {}
    for record in records:
        groups.setdefault(
            (record.get("Category") or "").strip(), []).append(record)
    for category in sorted(groups):
        members = sorted(groups[category],
                         key=lambda r: r.get("Capability ID", ""))
        lines.append("## %s (%d)" % (category, len(members)))
        lines.append("")
        for member in members:
            lines.append(
                "- %s — %s"
                % (member.get("Capability ID", "?"),
                   member.get("Capability", "?")))
        lines.append("")
    return "\n".join(lines)


def render_route(records):
    lines = [HEADER, "# Capabilities by Route", ""]
    groups = {}
    for record in records:
        groups.setdefault(route_key(record), []).append(record)
    for route in sorted(groups):
        members = sorted(groups[route],
                         key=lambda r: r.get("Capability ID", ""))
        lines.append("## %s (%d)" % (route, len(members)))
        lines.append("")
        for member in members:
            lines.append("- %s" % member.get("Capability ID", "?"))
        lines.append("")
    return "\n".join(lines)


def load_matrix():
    try:
        with open(MATRIX, encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        print("gen_capabilities: cannot read %s: %s" % (MATRIX, exc))
        return None


def render_matrix(records, rows):
    present = {
        row["Capability ID"]
        for row in rows
        if row.get("v4.2 Status", "").strip().upper().startswith("PRESENT")
    }
    by_id = {r.get("Capability ID", ""): r for r in records}
    ordered = sorted(set(list(by_id) + [r["Capability ID"] for r in rows]))
    lines = ["Capability ID,Capability,v5 Category,Preserved-v4.2"]
    for cid in ordered:
        record = by_id.get(cid, {})
        lines.append(
            "%s,%s,%s,%s"
            % (cid, record.get("Capability", ""),
               record.get("Category", ""),
               "yes" if cid in present else "no"))
    return "\n".join(lines) + "\n"


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main():
    records = load_records()
    if records is None:
        return 1
    rows = load_matrix()
    if rows is None:
        return 1
    by_category = render_category(records)
    by_route = render_route(records)
    matrix = render_matrix(records, rows)
    write_text(OUTDIR / "by-category.md", by_category)
    write_text(OUTDIR / "by-route.md", by_route)
    write_text(OUTDIR / "preservation-matrix.csv", matrix)
    sums = []
    for name in ("by-category.md", "by-route.md",
                 "preservation-matrix.csv"):
        digest = hashlib.sha256(
            (OUTDIR / name).read_bytes()).hexdigest()
        sums.append("%s  %s" % (digest, name))
    write_text(OUTDIR / "SHA256SUMS.txt", "\n".join(sums) + "\n")
    print("gen_capabilities: wrote 4 file(s) to %s" % OUTDIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
