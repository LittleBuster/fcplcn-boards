"""Export a grouped BOM from KiCad's XML netlist using Python's standard library."""

from pathlib import Path
import argparse
import csv
import re
import xml.etree.ElementTree as ET
from bom_common import component_record, component_key, EXTRA_COLUMNS


def natural_key(reference):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", reference)]


def export_bom(netlist, output):
    groups = {}
    for component in ET.parse(netlist).getroot().findall("components/comp"):
        if component.find("property[@name='exclude_from_bom']") is not None:
            continue
        reference = component.attrib["ref"]
        record = component_record(component)
        entry = groups.setdefault(component_key(record), {"record": record, "refs": [], "footprints": set()})
        entry["refs"].append(reference)
        entry["footprints"].add(record["footprint"])
    rows = []
    for entry in groups.values():
        record = entry["record"].copy()
        references = entry["refs"]
        references.sort(key=natural_key)
        record["refs"] = ", ".join(references)
        record["qty"] = len(references)
        record["cad_footprints"] = "; ".join(sorted(entry["footprints"]))
        record["footprint"] = record["cad_footprints"]
        rows.append(record)
    rows.sort(key=lambda row: natural_key(row["refs"].split(",")[0]))
    with Path(output).open("w", newline="", encoding="utf-8-sig") as stream:
        columns = ["refs", "value", "footprint", "qty", "datasheet", "mpn", "manufacturer", "tolerance", "supplier_part_number", "source_url"] + EXTRA_COLUMNS
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return sum(row["qty"] for row in rows), len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    total, unique = export_bom(args.netlist, args.output)
    print(f"Exported {total} components in {unique} grouped rows to {args.output}")
