#!/usr/bin/env bash
# Export the checked-in board schematics for GitHub without rewriting CAD files.
set -euo pipefail

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir="$repo_dir/docs/schematics"
board_dir="$repo_dir/FCPLCN-161608-1v0"

if command -v kicad-cli >/dev/null 2>&1; then
    kicad_cli=$(command -v kicad-cli)
elif [ -x /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli ]; then
    kicad_cli=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
else
    printf '%s\n' 'KiCad CLI is required. Install KiCad or add kicad-cli to PATH.' >&2
    exit 1
fi

if ! command -v pdftoppm >/dev/null 2>&1; then
    printf '%s\n' 'Poppler pdftoppm is required for PNG previews.' >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Python 3 is required to record source checksums.' >&2
    exit 1
fi
if command -v rsvg-convert >/dev/null 2>&1; then
    pcb_renderer=rsvg
elif [ "$(uname -s)" = Darwin ] && command -v swift >/dev/null 2>&1; then
    pcb_renderer=swift
else
    printf '%s\n' 'PCB previews require rsvg-convert (Linux) or Swift/AppKit (macOS).' >&2
    exit 1
fi

mkdir -p "$output_dir"
temporary=$(mktemp -d "${TMPDIR:-/tmp}/fcplcn-schematics.XXXXXX")
trap 'rm -rf "$temporary"' EXIT

export_board() {
    local name="$1" project="$2" source
    source="$board_dir/$project/$project.kicad_sch"
    mkdir -p "$temporary/$name"
    "$kicad_cli" sch export svg --output "$temporary/$name" "$source"
    cp "$temporary/$name/$project.svg" "$output_dir/$name-schematic.svg"
    "$kicad_cli" sch export pdf --exclude-pdf-metadata \
        --exclude-pdf-property-popups --output "$output_dir/$name-schematic.pdf" "$source"
    # A readable full-page preview; the SVG/PDF retain zoomable vector geometry.
    pdftoppm -png -singlefile -scale-to-x 3500 -scale-to-y -1 \
        "$output_dir/$name-schematic.pdf" "$output_dir/$name-schematic"
}

export_board cpu FCPLCN-CPU-08-1v0
export_board relay FCPLCN-RLY-1616-1v0

cpu_pcb="$board_dir/FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb"
"$kicad_cli" pcb export svg --layers F.Cu,F.SilkS,Edge.Cuts \
    --mode-single --page-size-mode 2 --exclude-drawing-sheet \
    --output "$output_dir/cpu-pcb.svg" "$cpu_pcb"
"$kicad_cli" pcb export svg --layers B.Cu,B.SilkS,Edge.Cuts --mirror \
    --mode-single --page-size-mode 2 --exclude-drawing-sheet \
    --output "$output_dir/cpu-pcb-bottom.svg" "$cpu_pcb"
# KiCad omits a background. Keep its light silkscreen readable on GitHub's
# light and dark themes alike, without altering any exported board geometry.
python3 - "$output_dir" <<'PY'
from pathlib import Path
import re
import sys

for name in ("cpu-pcb.svg", "cpu-pcb-bottom.svg"):
    path = Path(sys.argv[1]) / name
    svg = path.read_text()
    svg = re.sub(r'(<svg\b[^>]*>)', r'\1\n<rect width="100%" height="100%" fill="#101b2a"/>', svg, count=1)
    path.write_text(svg)
PY
for name in cpu-pcb cpu-pcb-bottom; do
    if [ "$pcb_renderer" = rsvg ]; then
        rsvg-convert --width 4200 --background-color white \
            --output "$output_dir/$name.png" "$output_dir/$name.svg"
    else
        swift "$board_dir/tools/svg_to_png.swift" \
            "$output_dir/$name.svg" "$output_dir/$name.png"
    fi
done

python3 - "$repo_dir" "$("$kicad_cli" version)" <<'PY'
import hashlib
import json
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
result = {"generator": "KiCad CLI", "version": sys.argv[2], "sources": {}}
output = root / "docs/schematics"

def exported_files(*names):
    return [
        {"file": name, "bytes": (output / name).stat().st_size}
        for name in names
    ]

for name, project in (("cpu", "FCPLCN-CPU-08-1v0"), ("relay", "FCPLCN-RLY-1616-1v0")):
    relative = Path("FCPLCN-161608-1v0") / project / (project + ".kicad_sch")
    source = root / relative
    paper = re.search(r'\(paper "User" ([\d.]+) ([\d.]+)\)', source.read_text())
    result["sources"][name + "-schematic"] = {
        "source": str(relative), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "pageMillimeters": list(map(float, paper.groups())), "pageCount": 1,
        "exports": exported_files(*(name + "-schematic." + ext for ext in ("svg", "pdf", "png"))),
    }
relative = Path("FCPLCN-161608-1v0/FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb")
result["sources"]["cpu-pcb"] = {
    "source": str(relative), "sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest(),
    "frontLayers": ["F.Cu", "F.SilkS", "Edge.Cuts"],
    "bottomLayers": ["B.Cu", "B.SilkS", "Edge.Cuts"], "bottomMirrored": True,
    "exports": exported_files("cpu-pcb.svg", "cpu-pcb.png", "cpu-pcb-bottom.svg", "cpu-pcb-bottom.png"),
}
(output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
PY
printf '%s\n' "Exported current schematics to $output_dir"
