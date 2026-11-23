#!/usr/bin/env python3
"""Refresh README PNGs from source-verified native KiCad renders."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "FCPLCN-161608-1v0"
GALLERY = PROJECT / "Previews/native-all-views"
DESTINATION = ROOT / "docs/readme"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    images = {}
    sources = {}
    for scene in ("Stack", "FCPLCN-CPU-08-1v0", "FCPLCN-RLY-1616-1v0"):
        report = json.loads((GALLERY / f"{scene}-manifest.json").read_text())
        for name, digest in report["source_sha256"].items():
            if sha(PROJECT / name) != digest:
                raise ValueError(f"Render source changed: {name}; regenerate native views first")
            sources[name] = digest
        for item in report["images"]:
            images[f"Previews/native-all-views/{item['file']}"] = item["sha256"]

    validation = json.loads((PROJECT / "Validation.json").read_text())
    report_path = PROJECT / validation["checks"]["renders"]
    report = json.loads(report_path.read_text())
    cpu = "FCPLCN-CPU-08-1v0"
    if not report["passed"]:
        raise ValueError(f"Render validation has not passed: {report_path.name}")
    report_sources = report.get("source_sha256", {})
    if report_sources:
        for name, digest in report_sources.items():
            if sha(PROJECT / name) != digest:
                raise ValueError(f"Detail render source changed: {name}")
    elif report.get("upper_pcb_sha256") != sha(PROJECT / cpu / f"{cpu}.kicad_pcb"):
        raise ValueError("iButton detail render does not match the current CPU board")
    for item in report["detail_images"]:
        images[item["file"]] = item["sha256"]

    selected = {
        "stack-overview.png": "Previews/native-all-views/Stack-angled-front.png",
        "cpu-top.png": f"Previews/native-all-views/{cpu}-top.png",
        "cpu-angled.png": f"Previews/native-all-views/{cpu}-angled-front.png",
        "cpu-bottom.png": f"Previews/native-all-views/{cpu}-bottom.png",
        "relay-top.png": "Previews/native-all-views/FCPLCN-RLY-1616-1v0-top.png",
        "relay-angled.png": "Previews/native-all-views/FCPLCN-RLY-1616-1v0-angled-front.png",
        "ibutton-output.png": "iButton-front-closeup.png",
    }
    # Check every selected file before replacing any README image.
    for source in selected.values():
        if sha(PROJECT / source) != images[source]:
            raise ValueError(f"Render image changed: {source}")
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, source in selected.items():
        shutil.copy2(PROJECT / source, DESTINATION / name)
    manifest = {
        "renderer": "Native KiCad",
        "sources_relative_to_project": sources,
        "images": {
            name: {"source": source, "sha256": sha(DESTINATION / name)}
            for name, source in selected.items()
        },
    }
    svg = DESTINATION / "power-domains.svg"
    png = DESTINATION / "power-domains.png"
    if svg.exists() and png.exists():
        project_svg = PROJECT / "Previews/power-domains.svg"
        project_png = PROJECT / "Previews/power-domains.png"
        shutil.copy2(svg, project_svg)
        shutil.copy2(png, project_png)
        manifest["power_diagram"] = {
            "source": "docs/readme/power-domains.svg",
            "source_sha256": sha(svg),
            "png_sha256": sha(png),
            "project_svg": str(project_svg.relative_to(PROJECT)),
            "project_png": str(project_png.relative_to(PROJECT)),
        }
    (DESTINATION / "preview-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"Updated {len(selected)} source-verified README previews")


if __name__ == "__main__":
    main()
