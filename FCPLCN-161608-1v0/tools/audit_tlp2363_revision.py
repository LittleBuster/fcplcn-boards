"""Read-only independent audit of the 16-channel TLP2363 lower-board revision.

Run with KiCad's Python. Only --output is written; CAD is never saved. PASS
checks the declared source/topology/placement delta and arithmetic, not native
DRC/ERC, actual filled-copper connectivity, EMC or prototype qualification.
The frozen --before-root is required and every input is bound by SHA256.
"""
from pathlib import Path
import argparse
import collections
import copy
import csv
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET

CPU = "FCPLCN-CPU-08-1v0"
RLY = "FCPLCN-RLY-1616-1v0"
NATIVE_EXTENSIONS = (".kicad_pcb", ".kicad_sch", ".kicad_pro", ".kicad_dru", ".xml")
NEW = ({f"U{i}" for i in range(25, 37)}
       | {f"C{i}" for i in range(121, 137)}
       | {f"R{i}" for i in range(141, 157)})
REPLACED = {f"U{i}" for i in range(21, 25)}
MOVABLE = {f"R{i}" for i in range(121, 137)} | {f"C{i}" for i in range(101, 117)}
WETTING = {f"R{i}" for i in range(101, 117)}
TLP_FP = "RelayBoard:TLP2363_5pin_SO6"
LED_MPN = "CRCW08051K50FKTAHP"
TLP_DATASHEET = "https://toshiba.semicon-storage.com/info/TLP2363_datasheet_en_20251218.pdf?did=67887&prodName=TLP2363"
LED_DATASHEET = "https://www.vishay.com/docs/20115/crcwhp.pdf"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def norm_net(value):
    return value.removeprefix("/").replace("{slash}", "/")


def natural(value):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]


def parse(text):
    """Parse native S-expressions without executing or writing source data."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    cursor = 0
    def node():
        nonlocal cursor
        token = tokens[cursor]
        cursor += 1
        if token != "(":
            return token
        result = []
        while tokens[cursor] != ")":
            result.append(node())
        cursor += 1
        return result
    result = node()
    if cursor != len(tokens):
        raise ValueError("Trailing S-expression tokens")
    return result


def children(node, names):
    return [part for part in node if isinstance(part, list) and part and part[0] in names]


def child(node, name):
    return next((part for part in node if isinstance(part, list) and part and part[0] == name), None)


def ast_fields(node):
    return {json.loads(part[1]): json.loads(part[2])
            for part in children(node, {"property"})}


def ast_without_pad_nets(node):
    result = copy.deepcopy(node)
    for pad in children(result, {"pad"}):
        pad[:] = [part for part in pad
                  if not (isinstance(part, list) and part and part[0] == "net")]
    return result


def unordered_children(node):
    """Normalize only sibling serialization order, retaining every value."""
    return node[:2] + sorted(node[2:], key=lambda part: json.dumps(part))


def normalized_hidden_bomgroup_thickness(node):
    """Normalize only KiCad's equivalent absent/default hidden-field thickness.

    The caller additionally checks the native before/after thickness and hidden
    state. This is not permission to change a value, pose, visible graphic or
    physical pad. No native source is rewritten.
    """
    result = copy.deepcopy(node)
    for prop in children(result, {"property"}):
        if prop[1] != '"BOMGroup"' or child(prop, "hide") != ["hide", "yes"]:
            continue
        if child(prop, "layer") != ["layer", '"F.Fab"']:
            continue
        effects = child(prop, "effects")
        font = child(effects, "font") if effects else None
        if font is not None and child(font, "thickness") is None:
            font.append(["thickness", "0.15"])
    return result


def xml_fields(component):
    return {field.get("name"): field.text or "" for field in component.findall("fields/field")}


def xml_pins(root):
    result = {}
    duplicate = []
    for net in root.findall("nets/net"):
        for pin in net.findall("node"):
            key = (pin.get("ref"), pin.get("pin"))
            if key in result:
                duplicate.append(list(key))
            result[key] = norm_net(net.get("name"))
    return result, duplicate


def field(fp, name):
    try:
        return fp.GetFieldText(name)
    except KeyError:
        return ""


def pin_map(fp):
    return {pad.GetNumber(): norm_net(pad.GetNetname()) for pad in fp.Pads() if pad.GetNumber()}


def pose(fp):
    point = fp.GetPosition()
    return [point.x, point.y, round(fp.GetOrientationDegrees(), 8), fp.GetLayerName()]


def pad_geometry(fp, world=False):
    """Bind physical pad geometry, never integer net codes or generated UUIDs."""
    angle = math.radians(fp.GetOrientationDegrees())
    origin = fp.GetPosition()
    result = []
    for pad in fp.Pads():
        point = pad.GetPosition()
        dx, dy = point.x - origin.x, point.y - origin.y
        xy = ((point.x, point.y) if world else
              (round(math.cos(angle)*dx - math.sin(angle)*dy),
               round(math.sin(angle)*dx + math.cos(angle)*dy)))
        result.append([pad.GetNumber(), list(xy), pad.GetSizeX(), pad.GetSizeY(),
                       int(pad.GetShape()), int(pad.GetAttribute()),
                       pad.GetDrillSizeX(), pad.GetDrillSizeY(),
                       round((pad.GetOrientationDegrees() - (0 if world else fp.GetOrientationDegrees())) % 360, 6),
                       list(pad.GetLayerSet().Seq())])
    return sorted(result, key=lambda row: json.dumps(row))


def footprint_tree_map(tree):
    return {ast_fields(fp)["Reference"]: fp for fp in children(tree, {"footprint"})}


def parse_components(path):
    root = ET.parse(path).getroot()
    components = root.findall("components/comp")
    return root, {component.get("ref"): component for component in components}, len(components)


def purchased(component):
    # Same authoritative KiCad property used by export_bom.py. Bare pads and
    # schematic power flags must never silently become purchased components.
    return component.find("property[@name='exclude_from_bom']") is None


def run(root, before, pcb):
    from bom_common import component_record, component_key
    errors, notes, gates, tracked = [], [], {}, set()
    def require(condition, description):
        gates[description] = bool(condition)
        if not condition:
            errors.append(description)
    def track(path):
        path = Path(path).resolve()
        tracked.add(path)
        return path
    def source(board_name, extension, side=root):
        return track(side / board_name / (board_name + extension))
    def close(actual, expected):
        return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10)
    track(Path(__file__))
    track(root / "tools/bom_common.py")
    for extension in NATIVE_EXTENSIONS:
        old_path = source(CPU, extension, before)
        new_path = source(CPU, extension)
        require(old_path.exists() and new_path.exists() and sha(old_path) == sha(new_path),
                "CPU byte exact " + extension)
    for extension in (".kicad_pro", ".kicad_dru"):
        old_path = source(RLY, extension, before)
        new_path = source(RLY, extension)
        require(old_path.exists() and new_path.exists() and sha(old_path) == sha(new_path),
                "RLY project/rules byte exact " + extension)
    old_mechanics = track(before / "Stack-mechanics.json")
    new_mechanics = track(root / "Stack-mechanics.json")
    require(old_mechanics.exists() and new_mechanics.exists() and sha(old_mechanics) == sha(new_mechanics),
            "Stack mechanical specification byte exact")

    board_data = {}
    metadata_mismatches, pin_mismatches, template_records = [], [], []
    library_root = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
    for board_name, purchase_count, physical_count in ((CPU, 148, 148), (RLY, 200, 203)):
        path = source(board_name, ".kicad_pcb")
        xml_path = source(board_name, ".xml")
        source(board_name, ".kicad_sch")
        board = pcb.LoadBoard(str(path))
        fps_list = list(board.GetFootprints())
        fps = {fp.GetReference(): fp for fp in fps_list}
        xml, components, xml_count = parse_components(xml_path)
        xpins, duplicate_xml = xml_pins(xml)
        ppins, duplicate_pad_conflicts = {}, []
        for ref, fp in fps.items():
            for pad in fp.Pads():
                if not pad.GetNumber():
                    continue
                key = (ref, pad.GetNumber())
                net = norm_net(pad.GetNetname())
                if key in ppins and ppins[key] != net:
                    duplicate_pad_conflicts.append([ref, pad.GetNumber()])
                ppins[key] = net
        require(len(fps_list) == len(fps), board_name + " unique PCB references")
        require(xml_count == len(components), board_name + " unique XML references")
        require(not duplicate_xml, board_name + " XML each pin occurs once")
        require(not duplicate_pad_conflicts, board_name + " duplicate physical pads have consistent nets")
        require(set(fps) == set(components), board_name + " full XML/PCB reference inventory")
        for key in sorted(set(xpins) | set(ppins)):
            if xpins.get(key) != ppins.get(key):
                pin_mismatches.append({"board": board_name, "ref": key[0], "pin": key[1],
                                       "XML": xpins.get(key), "PCB": ppins.get(key)})
        require(xpins == ppins, board_name + " whole XML/PCB pin-net map")
        for ref in sorted(set(fps) & set(components), key=natural):
            fp, component = fps[ref], components[ref]
            comparisons = [("Value", fp.GetValue(), component.findtext("value", "")),
                           ("Footprint", fp.GetFPIDAsString(), component.findtext("footprint", ""))]
            for name, expected in xml_fields(component).items():
                if name in {"Footprint", "Reference", "Value"}:
                    continue
                comparisons.append((name, field(fp, name), expected))
            comparisons.append(("Datasheet", field(fp, "Datasheet"), component.findtext("datasheet", "")))
            for name, actual, expected in comparisons:
                if actual != expected:
                    metadata_mismatches.append({"board": board_name, "ref": ref, "field": name,
                                                "PCB": actual, "XML": expected})
            lib, name = fp.GetFPIDAsString().split(":", 1)
            local = root / board_name / (lib + ".pretty") / (name + ".kicad_mod")
            asset = local if local.exists() else library_root / (lib + ".pretty") / (name + ".kicad_mod")
            track(asset)
            require(asset.exists(), board_name + " " + ref + " footprint library link exists")
        require(not [item for item in metadata_mismatches if item["board"] == board_name],
                board_name + " all XML/PCB technical metadata and values")
        purchases = [component for component in components.values() if purchased(component)]
        excluded = sorted(set(components) - {component.get("ref") for component in purchases}, key=natural)
        require(len(purchases) == purchase_count, board_name + " purchased count " + str(purchase_count))
        require(len(fps) == physical_count, board_name + " physical footprint count " + str(physical_count))
        require(excluded == (["TP5", "TP6", "TP7"] if board_name == RLY else []),
                board_name + " exact excluded bare-pad inventory")
        require(not any(component.get("ref").startswith(("TP", "#")) for component in purchases),
                board_name + " no TP or power flag is purchased")
        groups = collections.Counter(component_key(component_record(component)) for component in purchases)
        bom_path = track(root / board_name / "BOM.csv")
        bom_rows = list(csv.DictReader(bom_path.open(encoding="utf-8-sig")))
        bom_refs = [ref.strip() for row in bom_rows for ref in row["refs"].split(",")]
        require(sum(int(row["qty"]) for row in bom_rows) == purchase_count,
                board_name + " BOM quantity equals XML purchase inventory")
        require(collections.Counter(bom_refs) == collections.Counter(component.get("ref") for component in purchases),
                board_name + " BOM references match purchased XML exactly")
        require(len(bom_rows) == len(groups), board_name + " BOM purchasing groups use bom_common")
        csv_groups = collections.Counter()
        for row in bom_rows:
            csv_groups[component_key(row)] += int(row["qty"])
        require(csv_groups == groups, board_name + " BOM values/rating/ordering groups match XML exactly")
        require(board.GetCopperLayerCount() == 2, board_name + " two copper layers")
        board_data[board_name] = {"board": board, "fps": fps, "xml": xml, "components": components,
                                  "purchased": len(purchases), "physical": len(fps), "excluded": excluded,
                                  "pin_count": len(ppins), "BOM_groups": len(groups)}

    combined = track(root / "BOM-combined.csv")
    combined_rows = list(csv.DictReader(combined.open(encoding="utf-8-sig")))
    require(sum(int(row["total_qty"]) for row in combined_rows) == 348, "Combined BOM purchased quantity 348")
    new = board_data[RLY]["board"]
    new_fp = board_data[RLY]["fps"]
    old_path = source(RLY, ".kicad_pcb", before)
    source(RLY, ".kicad_sch", before)
    source(RLY, ".xml", before)
    track(root / RLY / "RelayBoard.kicad_sym")
    track(root / RLY / "3d/TLP2363_5pin_SO6.wrl")
    track(root / RLY / "3d/TLP2363-provenance.json")
    local_datasheet = track(root / RLY / "datasheets/Toshiba-TLP2363-Rev4.0A.pdf")
    require(local_datasheet.exists() and sha(local_datasheet) == "7d3f2132ae01436d6bc86dfdd95c32b335ba611ed329d1a634650ed9aff75944",
            "Official archived Toshiba TLP2363 Rev4.0A datasheet exact source hash")
    old = pcb.LoadBoard(str(old_path))
    old_fp = {fp.GetReference(): fp for fp in old.GetFootprints()}
    old_tree, new_tree = parse(old_path.read_text()), parse(source(RLY, ".kicad_pcb").read_text())
    old_ast, new_ast = footprint_tree_map(old_tree), footprint_tree_map(new_tree)
    require(len(old_fp) == 159, "Before RLY contains156 purchased plus3 test pads")
    require(set(new_fp) - set(old_fp) == NEW and not (set(old_fp) - set(new_fp)),
            "Exact44 reference additions and no removed reference")
    moved, unrelated_deltas, serialization_equivalences = {}, [], []
    for ref in sorted(set(old_fp) & set(new_fp), key=natural):
        a, b = old_fp[ref], new_fp[ref]
        if pose(a) != pose(b):
            moved[ref] = {"before_pose_nm_deg_layer": pose(a), "after_pose_nm_deg_layer": pose(b)}
        if ref in REPLACED:
            require(a.GetValue() == "LTV-847S" and b.GetValue() == "TLP2363", ref + " authorized quad-to-single identity")
            continue
        expected = pin_map(a)
        if ref in {f"R{i}" for i in range(121, 137)}:
            expected["2"] = f"OPTO{int(ref[1:])-120}_RAW"
        require(pin_map(b) == expected, ref + " existing pin-net map preserved except RAW pull-up")
        if ref not in MOVABLE:
            require(pose(a) == pose(b), ref + " exact preserved placement/rotation/layer")
        else:
            require(a.GetLayer() == b.GetLayer(), ref + " allowed local move retains board side")
        require(pad_geometry(a) == pad_geometry(b), ref + " existing local pad geometry preserved")
        if ref in WETTING:
            # Electrical value/ordering fields are explicitly replaced below;
            # physical pad coordinates and footprint identity stay unchanged.
            require(a.GetFPIDAsString() == b.GetFPIDAsString(), ref + " original wetting footprint preserved")
            continue
        require(a.GetValue() == b.GetValue() and a.GetFPIDAsString() == b.GetFPIDAsString(),
                ref + " existing value/footprint identity preserved")
        if ref not in MOVABLE:
            left = unordered_children(ast_without_pad_nets(old_ast[ref]))
            right = unordered_children(ast_without_pad_nets(new_ast[ref]))
            if ref == "U9" and left != right:
                old_field = next((item for item in a.GetFields() if item.GetName() == "BOMGroup"), None)
                new_field = next((item for item in b.GetFields() if item.GetName() == "BOMGroup"), None)
                native_same = (old_field is not None and new_field is not None
                               and old_field.GetTextThickness() == new_field.GetTextThickness() == 150000
                               and not old_field.IsVisible() and not new_field.IsVisible())
                normalized_left = unordered_children(normalized_hidden_bomgroup_thickness(left))
                normalized_right = unordered_children(normalized_hidden_bomgroup_thickness(right))
                if native_same and normalized_left == normalized_right:
                    left, right = normalized_left, normalized_right
                    serialization_equivalences.append({"ref": "U9", "field": "BOMGroup",
                                                       "native_before_thickness_nm": 150000,
                                                       "native_after_thickness_nm": 150000,
                                                       "visible_before_and_after": False,
                                                       "scope": "Missing vs explicit0.15mm default font thickness only; every other AST value retained."})
            if left != right:
                unrelated_deltas.append(ref)
            require(left == right, ref + " unrelated footprint content exact")
    def graphic_items(tree, layer=None, branding=False):
        result = []
        for item in tree:
            if not isinstance(item, list) or not item or not item[0].startswith("gr_"):
                continue
            item_layer = child(item, "layer")
            if layer and item_layer != ["layer", json.dumps(layer)]:
                continue
            if branding and not (item[0] == "gr_text" and
                                 any(text in item[1] for text in ("FCPLCN-", "Denisov Foundation Ltd."))):
                continue
            result.append(item)
        return sorted(result, key=lambda value: json.dumps(value))
    require(graphic_items(old_tree, "Edge.Cuts") == graphic_items(new_tree, "Edge.Cuts"), "RLY complete outline exact")
    old_brand = graphic_items(old_tree, branding=True)
    require(len(old_brand) >= 2 and old_brand == graphic_items(new_tree, branding=True), "RLY product and Denisov Foundation branding exact")
    for ref in ("J43", "J44", "U9", "C14"):
        require(ref in old_fp and ref in new_fp, ref + " protected stack/FRAM component exists")
        if ref in old_fp and ref in new_fp:
            require(pose(old_fp[ref]) == pose(new_fp[ref]) and pad_geometry(old_fp[ref], True) == pad_geometry(new_fp[ref], True)
                    and pin_map(old_fp[ref]) == pin_map(new_fp[ref]), ref + " stack/FRAM physical pad world coordinates and nets exact")

    channels = []
    template_board = pcb.BOARD()
    for ch in range(1, 17):
        u, wet, reverse, tvs, pull, filtr, series, bypass = (f"U{20+ch}", f"R{100+ch}", f"D{100+ch}", f"D{120+ch}",
                                                           f"R{120+ch}", f"C{100+ch}", f"R{140+ch}", f"C{120+ch}")
        led = f"Net-(D{100+ch}-K)"
        expected = {u: {"1": led, "3": f"DI{ch}", "4": "GND", "5": f"OPTO{ch}_RAW", "6": "+3V3"},
                    wet: {"1": "+12V_SYS", "2": led}, reverse: {"1": led, "2": f"DI{ch}"},
                    tvs: {"1": f"DI{ch}", "2": "GND"}, pull: {"1": "+3V3", "2": f"OPTO{ch}_RAW"},
                    filtr: {"1": f"IN{ch}", "2": "GND"}, series: {"1": f"OPTO{ch}_RAW", "2": f"IN{ch}"},
                    bypass: {"1": "+3V3", "2": "GND"}}
        for ref, pins in expected.items():
            require(ref in new_fp and pin_map(new_fp[ref]) == pins, ref + " exact TLP channel pin topology")
        for ref, value, fp_id in ((u, "TLP2363", TLP_FP), (wet, "1.5k", "RelayBoard:R_0805_Wetting"),
                                  (pull, "10k", "RelayBoard:R_0805_2012Metric"),
                                  (series, "470R", "RelayBoard:R_0805_2012Metric"),
                                  (filtr, "100nF", "RelayBoard:C_0805_2012Metric"),
                                  (bypass, "100nF", "RelayBoard:C_0805_2012Metric")):
            require(ref in new_fp and new_fp[ref].GetValue() == value and new_fp[ref].GetFPIDAsString() == fp_id,
                    ref + " exact channel value/footprint")
        for ref, required_fields in ((u, {"MPN": "TLP2363(TPL,E", "Manufacturer": "Toshiba", "PackageDrawing": "11-4L1S", "Datasheet": TLP_DATASHEET}),
                                     (wet, {"MPN": LED_MPN, "Manufacturer": "Vishay", "Tolerance": "1%", "PowerRating": "0.5 W", "Datasheet": LED_DATASHEET}),
                                     (pull, {"Tolerance": "1%"}),
                                     (series, {"Tolerance": "1%", "PowerRating": "0.125 W"}),
                                     (filtr, {"Tolerance": "10%", "Voltage": "50 V", "Dielectric": "X7R"}),
                                     (bypass, {"Tolerance": "10%", "Voltage": "50 V", "Dielectric": "X7R"})):
            for name, expected_field in required_fields.items():
                require(ref in new_fp and field(new_fp[ref], name) == expected_field, ref + " exact " + name)
        for ref in (u, series, bypass):
            if ref not in new_fp:
                continue
            fp = new_fp[ref]
            lib, name = fp.GetFPIDAsString().split(":", 1)
            libdir = root / RLY / (lib + ".pretty")
            asset = track(libdir / (name + ".kicad_mod"))
            if not asset.exists():
                continue
            template = pcb.FootprintLoad(str(libdir), name)
            template_board.Add(template)
            if fp.GetLayer() == pcb.B_Cu:
                template.Flip(template.GetPosition(), False)
            template.SetOrientationDegrees(fp.GetOrientationDegrees())
            template.SetPosition(fp.GetPosition())
            require(pad_geometry(fp) == pad_geometry(template), ref + " actual physical pads match library asset")
            template_records.append({"ref": ref, "asset": str(asset), "asset_sha256": sha(asset)})
        if u in new_fp and bypass in new_fp:
            pads = {ref: {pad.GetNumber(): pad for pad in new_fp[ref].Pads()} for ref in (u, bypass)}
            def distance(a, b):
                point1, point2 = a.GetPosition(), b.GetPosition()
                return math.hypot(point1.x-point2.x, point1.y-point2.y)/1e6
            distances = [distance(pads[u]["6"], pads[bypass]["1"]), distance(pads[u]["4"], pads[bypass]["2"])]
            require(all(value < 10 for value in distances), u + " bypass pad-distance lower bounds under10mm")
            channels.append({"channel": ch, "opto": u, "expected_pins": expected,
                             "bypass_power_ground_distance_lower_bounds_mm": distances})

    power_path = track(root / "Power-budget.json")
    report_path = track(root / "TLP2363-power-budget.json")
    review_path = track(root / "TLP2363-design-review.md")
    budget, report = json.loads(power_path.read_text()), json.loads(report_path.read_text())
    lower_ma = 25.3 + 16*4
    common_ma = lower_ma + 1000/(5*.76)
    conversion_W = (2.937 + 5*common_ma/1000 + .6633)/.85
    current = (11.2-math.sqrt(11.2**2-4*conversion_W))/2
    voltage = 11.2-current
    DI = 16*(11.6-1.2)/1500
    require(budget["common_5v"]["lower_design_current_ma"] == lower_ma, "Power budget lower3V3 allocation89.3mA")
    require(close(budget["common_5v"]["combined_full_load_design_estimate_ma"], round(common_ma, 3)), "Power budget common5V allocation352.458mA")
    require(close(budget["protected_12v_RC"]["converter_input_power_W_assuming85pct_efficiency"], conversion_W), "Power budget converter input power recomputed")
    require(close(budget["protected_12v_RC"]["self_consistent_current_A"], current), "Power budget filtered12V current recomputed")
    require(close(budget["protected_12v_RC"]["protected_voltage_V"], voltage), "Power budget filtered12V voltage recomputed")
    require(close(budget["input_12v"]["calculation"]["DI_current_a_all16_closed"], DI), "Power budget all16 DI current recomputed")
    require(close(budget["input_12v"]["current_budget_a_minus10percent_coil_resistance"], current + .17185185185185184 + DI), "Power budget fuse current recomputed")
    require(report["counts"]["CPU_purchased"] == 148 and report["counts"]["RLY_purchased"] == 200
            and report["counts"]["combined_purchased"] == 348
            and report["counts"]["RLY_physical_footprints_including3_testpoints"] == 203, "Power report exact current component counts")
    require(budget["main_3v3"]["design_total_ma"] == 890 and budget["isolated_3v3"]["TMR_output_budget_ma"] == 175,
            "Unrelated CPU890mA and TMR175mA power allocations preserved")
    require("GPPU" in review_path.read_text() and "общий GND" in review_path.read_text(), "Review documents pull-up requirement and common-ground isolation limit")
    for rel in ("FRAM-power-budget.json", "SRDA-budget-audit.json", "SRDA-technical-review.json", "RS485-logic-budget.json", RLY + "/F1-current-audit.json"):
        old_report, new_report = before / rel, root / rel
        if old_report.exists() and new_report.exists():
            track(old_report); track(new_report)
            require(sha(old_report) == sha(new_report), "Historical report unchanged " + rel)
    missing = sorted(str(path) for path in tracked if not path.exists())
    require(not missing, "All referenced source and footprint files exist")
    status = "PASS" if not errors else "FAIL"
    return {"status": status, "project_root": str(root), "before_root": str(before),
            "errors": errors, "notes": notes, "gates": gates,
            "constraints": {"CPU_five_native_files_byte_exact": True, "Lower_PRO_DRU_byte_exact": True,
                            "new_refs_exact": sorted(NEW, key=natural), "replaced_refs": sorted(REPLACED, key=natural),
                            "movable_existing_refs_only": sorted(MOVABLE, key=natural),
                            "wetting_resistor_placement_must_remain": sorted(WETTING, key=natural),
                            "retained_diodes_must_not_move": [f"D{i}" for i in list(range(101,117))+list(range(121,137))],
                            "prototype_and_native_copper_checks_separate": True},
            "source_sha256": {str(path): sha(path) for path in sorted(tracked) if path.exists()},
            "missing_sources": missing, "XML_PCB_pin_mismatches": pin_mismatches,
            "XML_PCB_metadata_mismatches": metadata_mismatches,
            "counts": {name: {key: value for key, value in data.items() if key in {"purchased", "physical", "excluded", "pin_count", "BOM_groups"}}
                       for name, data in board_data.items()},
            "existing_moved_components": moved, "unrelated_footprint_deltas": unrelated_deltas,
            "native_serialization_equivalences": serialization_equivalences,
            "channels": channels, "new_footprint_template_checks": template_records,
            "power_recomputed": {"lower3V3_mA": lower_ma, "common5V_mA": common_ma, "converter_input_W": conversion_W,
                                 "logic12V_current_A": current, "protected12V_V": voltage, "R12_power_W": current*current,
                                 "DI_all16_current_A": DI, "fuse_current_lowcoil_A": current + .17185185185185184 + DI},
            "source_only": True, "CAD_files_not_written": True,
            "scope": "Source pin topology, metadata, inventory, footprint links, authorized placement delta and arithmetic only. Pad-distance metrics are geometric lower bounds, not measured routed HF loop lengths. PASS is not native DRC/ERC, connectivity of filled copper, enclosure thermal or EMC qualification."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--before-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import wx
    application = wx.App(False)
    wx.Log.EnableLogging(False)
    import pcbnew
    root, before = args.project_root.resolve(), args.before_root.resolve()
    try:
        result = run(root, before, pcbnew)
    except Exception as exc:
        result = {"status": "FAIL", "errors": [type(exc).__name__ + ": " + str(exc)],
                  "project_root": str(root), "before_root": str(before),
                  "CAD_files_not_written": True, "scope": "Audit could not complete; this is not a passed source check."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "errors": result["errors"], "report": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
