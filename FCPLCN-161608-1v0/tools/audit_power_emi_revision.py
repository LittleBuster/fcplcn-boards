"""Read-only source audit for the R78 RS485 supply and Lower 12 V RC revision.

Run with KiCad's Python. The previous RS485 revision and its USB exception are
history; this revision must preserve all SIX current USB data/CC copper nets.
This is a source/geometry audit, not an EMC test or final native DRC substitute.
"""
from pathlib import Path
from board_paths import board_file, board_name
import argparse
import collections
import copy
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET

import pcbnew as p

USB_NETS = frozenset({'/USB_DP', '/USB_DP_CPU', '/USB_DN', '/USB_DN_CPU',
                      '/USB_CC1', '/USB_CC2'})
ALLOWED_COPPER = {
    'Upper': frozenset({'/+3V3', '/+3V3_RS485', '/+12V_LOGIC', '/MOD_VBUS',
                        '/GND', '/RS485_DIR', '/RS485_RX_RAW', '/RS485_TX', '/DATA6_CPU',
                        '/USB_VBUS_SENSE', '/ESP_BOOT'}),
    'Lower': frozenset({'/+12V_LOGIC', '/+12V_LOGIC_RAW', '/+12V_SYS', '/GND'}),
}
RAW_PATTERN = {'netclass': 'Board_Power', 'pattern': '/+12V_LOGIC_RAW'}
R78_FP = 'RelayStack:RECOM_R-78K3.3-0.5_SIP3_P2.54mm'
CAP_FP = 'Capacitor_SMD:C_1206_3216Metric'
CAP_MPN = 'C3216X5R1V226M160AC'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    index = 0
    def node():
        nonlocal index
        token = tokens[index]
        index += 1
        if token != '(':
            return token
        value = []
        while tokens[index] != ')':
            value.append(node())
        index += 1
        return value
    result = node()
    assert index == len(tokens), 'Trailing S-expression data'
    return result


def children(tree, names):
    return [x for x in tree if isinstance(x, list) and x[0] in names]


def child(tree, name):
    return next(x for x in tree if isinstance(x, list) and x[0] == name)


def fps_ast(tree):
    return {json.loads(next(z[2] for z in f if isinstance(z, list)
                            and z[:2] == ['property', '"Reference"'])): f
            for f in children(tree, {'footprint'})}


def footprint_equal(left, right):
    # KiCad moves custom properties before path/sheetfile during save. Only
    # sibling order is normalized; every value and nested geometry is retained.
    return (left[:2] == right[:2]
            and collections.Counter(json.dumps(x) for x in left[2:])
            == collections.Counter(json.dumps(x) for x in right[2:]))


def footprint_digest(tree):
    normalized = tree[:2] + sorted(tree[2:], key=lambda x: json.dumps(x))
    return hashlib.sha256(json.dumps(normalized, separators=(',', ':')).encode()).hexdigest()


def footprint_without_pose(tree):
    """Remove only rigid translation/rotation; all local geometry stays exact.

    Layers are retained, so the optional resistor permission cannot flip a part.
    KiCad stores text/pad angles in board coordinates, and local XY coordinates.
    """
    result = copy.deepcopy(tree)
    at = child(result, 'at')
    angle = float(at[3]) if len(at) > 3 else 0.0
    at[:] = ['at', '0', '0', '0']
    for item in children(result, {'property', 'fp_text', 'pad'}):
        local_at = child(item, 'at')
        local_angle = float(local_at[3]) if len(local_at) > 3 else 0.0
        # Native flip/return may keep text upright by a half-turn. Exact actual
        # text geometry is still bound by the approved after-footprint digest.
        period = 360 if item[0] == 'pad' else 180
        local_at[:] = local_at[:3] + [round((local_angle - angle) % period, 6)]
    return result


def native_footprint_ast(footprint):
    formatter = p.STRING_FORMATTER()
    plugin = p.PCB_IO_KICAD_SEXPR()
    plugin.SetOutputFormatter(formatter)
    plugin.Format(footprint)
    result = parse(formatter.GetString())
    # Native clone creates new mandatory-field UUIDs. The manifest already binds
    # all actual UUIDs; ignore only these clone identities in inverse-flip proof.
    def strip_uuid(node):
        return [strip_uuid(x) if isinstance(x, list) else x for x in node
                if not (isinstance(x, list) and x[0] == 'uuid')]
    result = strip_uuid(result)
    for item in children(result, {'property', 'fp_text'}):
        at = child(item, 'at')
        # Flip/keep-upright may turn text by 180 degrees, with identical content.
        at[:] = at[:3] + [round((float(at[3]) if len(at) > 3 else 0.0) % 180, 6)]
    return result


def approved_resistor_poses(manifest, before_sha, old_ast, new_ast, old_fp, new_fp):
    """An explicit manifest binds exact R55/R56 poses and complete FP content."""
    if manifest is None:
        return set()
    required_manifest = {'version', 'before_upper_pcb_sha256', 'footprints'}
    assert required_manifest <= set(manifest) <= required_manifest | {'approved_boot_copper'}
    assert manifest['version'] == 1 and manifest['before_upper_pcb_sha256'] == before_sha, 'Wrong pose-manifest source revision'
    records = manifest['footprints']
    assert isinstance(records, dict) and records and set(records) <= {'R55', 'R56'}, 'Only R55/R56 pose exceptions are permitted'
    for ref, record in records.items():
        required = {'before_pose', 'after_pose', 'before_normalized_ast_sha256', 'after_normalized_ast_sha256'}
        assert required <= set(record) <= required | {'approved_layer_change'}
        assert record['before_pose'] == pose(old_fp[ref]), ref + ' manifest before pose mismatch'
        assert record['after_pose'] == pose(new_fp[ref]), ref + ' unapproved final pose'
        assert record['before_normalized_ast_sha256'] == footprint_digest(old_ast[ref]), ref + ' manifest source footprint mismatch'
        assert record['after_normalized_ast_sha256'] == footprint_digest(new_ast[ref]), ref + ' footprint differs from approved manifest'
        layer_change = record.get('approved_layer_change')
        if layer_change is not None:
            assert ref == 'R56' and layer_change == 'F.Cu->B.Cu', 'Only exact R56 F-to-B change may be approved'
            assert old_fp[ref].GetLayer() == p.F_Cu and new_fp[ref].GetLayer() == p.B_Cu
            restored = p.FOOTPRINT(new_fp[ref])
            restored.Flip(restored.GetPosition(), False)
            restored.SetOrientationDegrees(old_fp[ref].GetOrientationDegrees())
            restored.SetPosition(old_fp[ref].GetPosition())
            assert footprint_equal(native_footprint_ast(old_fp[ref]), native_footprint_ast(restored)), ref + ' changed beyond exact approved flip/pose'
            assert local_pad_geometry(old_fp[ref]) == local_pad_geometry(restored), ref + ' inverse-flip pad geometry changed'
        else:
            assert footprint_equal(footprint_without_pose(old_ast[ref]), footprint_without_pose(new_ast[ref])), ref + ' changed beyond rigid translation/rotation'
            assert local_pad_geometry(old_fp[ref]) == local_pad_geometry(new_fp[ref])
        assert old_fp[ref].GetFPIDAsString() == new_fp[ref].GetFPIDAsString()
        assert old_fp[ref].GetValue() == new_fp[ref].GetValue()
        assert netmap(old_fp[ref]) == netmap(new_fp[ref])
    return set(records)


def netmap(footprint):
    return {pad.GetNumber(): pad.GetNetname() for pad in footprint.Pads()
            if pad.GetNumber()}


def local_pad_geometry(footprint):
    angle = math.radians(footprint.GetOrientationDegrees())
    origin = footprint.GetPosition()
    records = []
    for pad in footprint.Pads():
        point = pad.GetPosition()
        dx, dy = point.x - origin.x, point.y - origin.y
        local = (round(math.cos(angle) * dx - math.sin(angle) * dy),
                 round(math.sin(angle) * dx + math.cos(angle) * dy))
        records.append((pad.GetNumber(), local, pad.GetSizeX(), pad.GetSizeY(),
                        int(pad.GetShape()), int(pad.GetAttribute()),
                        pad.GetDrillSizeX(), pad.GetDrillSizeY(),
                        round((pad.GetOrientationDegrees() - footprint.GetOrientationDegrees()) % 360, 6),
                        tuple(pad.GetLayerSet().Seq())))
    return sorted(records)


def verify_r78_pads(footprint):
    records = local_pad_geometry(footprint)
    assert len(records) == 3
    for record, index in zip(records, (1, 2, 3)):
        number, local, sx, sy, shape, attribute, dx, dy, angle, layers = record
        assert number == str(index) and local == (round((index - 1) * 2540000), 0), 'R78 pitch/pin numbering changed'
        assert sx == sy == 1900000 and dx == dy == 1200000, 'R78 pad/hole geometry changed'
        assert shape == int(p.PAD_SHAPE_RECT if index == 1 else p.PAD_SHAPE_CIRCLE)
        assert attribute == int(p.PAD_ATTRIB_PTH) and p.F_Cu in layers and p.B_Cu in layers


def pose(footprint):
    return [footprint.GetPosition().x / 1e6, footprint.GetPosition().y / 1e6,
            footprint.GetOrientationDegrees(), footprint.GetLayerName()]


def geometry(item):
    if isinstance(item, p.PCB_VIA):
        point = item.GetPosition()
        return ('via', point.x, point.y, item.GetWidth(p.F_Cu),
                item.GetWidth(p.B_Cu), item.GetDrillValue(),
                item.TopLayer(), item.BottomLayer())
    first, last = item.GetStart(), item.GetEnd()
    start, end = sorted(((first.x, first.y), (last.x, last.y)))
    if isinstance(item, p.PCB_ARC):
        mid = item.GetMid()
        return ('arc', *start, mid.x, mid.y, *end, item.GetLayer(), item.GetWidth())
    return ('track', *start, *end, item.GetLayer(), item.GetWidth())


def copper(board):
    return {item.m_Uuid.AsString(): {'net': item.GetNetname(),
                                    'geometry_nm': list(geometry(item))}
            for item in board.GetTracks()}


def geometry_counter(records, net):
    return collections.Counter(tuple(v['geometry_nm']) for v in records.values()
                               if v['net'] == net)


def approved_boot_geometry(manifest, old, new):
    """Bind the small BOOT jog to its approved complete before/after geometry."""
    before = sorted(list(item) for item in geometry_counter(old, '/ESP_BOOT').elements())
    after = sorted(list(item) for item in geometry_counter(new, '/ESP_BOOT').elements())
    approval = (manifest or {}).get('approved_boot_copper')
    if approval is None:
        assert before == after, 'ESP_BOOT changed without an exact copper manifest'
        return {'geometry_exact_from_before': True}
    assert set(approval) == {'net', 'before_geometry_nm', 'after_geometry_nm'}
    assert approval['net'] == '/ESP_BOOT'
    assert approval['before_geometry_nm'] == before, 'ESP_BOOT manifest source geometry mismatch'
    assert approval['after_geometry_nm'] == after, 'ESP_BOOT differs from the exact approved jog'
    return {'exact_approved_geometry': True, 'net': '/ESP_BOOT'}


def copper_delta(old, new, allowed):
    removed = [{'uuid': key, **old[key]} for key in sorted(set(old) - set(new))]
    added = [{'uuid': key, **new[key]} for key in sorted(set(new) - set(old))]
    mutated = [{'uuid': key, 'before': old[key], 'after': new[key]}
               for key in sorted(set(old) & set(new)) if old[key] != new[key]]
    changed_nets = ({v['net'] for v in removed + added}
                    | {v[side]['net'] for v in mutated for side in ('before', 'after')})
    assert changed_nets <= allowed, 'Unapproved copper edits: ' + ', '.join(sorted(changed_nets - allowed))
    nets = sorted({v['net'] for v in old.values()} | {v['net'] for v in new.values()})
    by_net = {net: {'before_items': sum(v['net'] == net for v in old.values()),
                    'after_items': sum(v['net'] == net for v in new.values()),
                    'geometry_exact': geometry_counter(old, net) == geometry_counter(new, net)}
              for net in nets}
    assert all(v['geometry_exact'] for net, v in by_net.items() if net not in allowed)
    return {'allowed_nets': sorted(allowed), 'changed_nets': sorted(changed_nets),
            'removed': removed, 'added': added, 'mutated': mutated,
            'counts': {'removed': len(removed), 'added': len(added), 'mutated': len(mutated)},
            'by_net': by_net, 'all_other_net_geometry_exact': True}


def zone_definitions(tree):
    # Fills are regenerated by KiCad; zone boundaries, net, clearances, priority,
    # island-removal settings and all keepouts remain part of the exact guard.
    return [[x for x in z if not (isinstance(x, list) and x[0] in
                                 {'filled_polygon', 'fill_segments', 'filled_areas_thickness'})]
            for z in children(tree, {'zone'})]


def project_rules(before, after, side):
    old = json.loads(before.with_suffix('.kicad_pro').read_text())
    new = json.loads(after.with_suffix('.kicad_pro').read_text())
    exception = None
    if side == 'Lower' and old != new:
        expected = copy.deepcopy(old)
        patterns = expected['net_settings']['netclass_patterns']
        assert RAW_PATTERN not in patterns, 'RAW net class already present in before'
        patterns.append(RAW_PATTERN)
        assert expected == new, 'Project changed beyond exact RAW→Board_Power pattern'
        exception = RAW_PATTERN
    else:
        assert old == new, side + ' project JSON changed'
    assert before.with_suffix('.kicad_dru').read_bytes() == after.with_suffix('.kicad_dru').read_bytes(), side + ' custom rules changed'
    return {'numeric_rules_and_all_other_project_settings_exact': True,
            'custom_rules_byte_exact': True, 'new_net_class_pattern': exception}


def audit_xml(before, after, side):
    old = ET.parse(before).getroot()
    new = ET.parse(after).getroot()
    components = lambda root: {c.get('ref'): c for c in root.findall('components/comp')}
    pins = lambda root: {(n.get('ref'), n.get('pin')): net.get('name')
                         for net in root.findall('nets/net') for n in net.findall('node')}
    a, b = components(old), components(new)
    oldpins, newpins = pins(old), pins(new)
    expected = dict(oldpins)
    if side == 'Upper':
        assert set(a) == set(b) and len(b) == 131
        allowed = {'U12', 'C37'}
        expected.update({('U12', '1'): '/+12V_LOGIC', ('U12', '2'): '/GND',
                         ('U12', '3'): '/+3V3_RS485', ('C37', '1'): '/+12V_LOGIC'})
        assert len(newpins) == 431
        for ref, value, mpn, footprint in [('U12', 'R-78K3.3-0.5', 'R-78K3.3-0.5', R78_FP),
                                           ('C37', '22uF 35V X5R', CAP_MPN, CAP_FP)]:
            assert b[ref].findtext('value') == value and b[ref].findtext('footprint') == footprint
            assert b[ref].findtext("fields/field[@name='MPN']") == mpn
        assert b['C37'].findtext("fields/field[@name='Tolerance']") == '20%'
    else:
        assert set(b) - set(a) == {'R12', 'C13'} and not set(a) - set(b)
        allowed = {'R12', 'C13'}
        expected.update({('D3', '1'): '/+12V_LOGIC_RAW', ('R12', '1'): '/+12V_LOGIC_RAW',
                         ('R12', '2'): '/+12V_LOGIC', ('C13', '1'): '/+12V_LOGIC', ('C13', '2'): '/GND'})
        assert b['R12'].findtext('value') == '1R / 2W pulse'
        assert b['R12'].findtext('footprint') == 'RelayBoard:R_2512_6332Metric'
        assert b['R12'].findtext("fields/field[@name='MPN']") == 'CRM2512-FX-1R00ELF'
        assert b['C13'].findtext('value') == '100nF / 50V X7R'
        assert b['C13'].findtext('footprint') == 'RelayBoard:C_0805_2012Metric'
    assert expected == newpins, side + ' unexpected XML pin/net map change'
    for ref in set(a) & set(b) - allowed:
        assert ET.tostring(a[ref]) == ET.tostring(b[ref]), side + ' unexpected XML component change: ' + ref
    return {'components': len(b), 'pin_nodes': len(newpins), 'only_approved_pin_changes': True,
            'all_other_component_records_exact': True}


def transform(fp, x, y):
    angle = math.radians(fp.GetOrientationDegrees())
    return [fp.GetPosition().x / 1e6 + math.cos(angle) * x + math.sin(angle) * y,
            fp.GetPosition().y / 1e6 - math.sin(angle) * x + math.cos(angle) * y]


def rectangle(fp, width, depth, x=0, y=0):
    points = [transform(fp, x + dx * width / 2, y + dy * depth / 2)
              for dx in (-1, 1) for dy in (-1, 1)]
    return [min(q[0] for q in points), min(q[1] for q in points),
            max(q[0] for q in points), max(q[1] for q in points)]


def mechanical(upper, lower, mechanics):
    uf = {f.GetReference(): f for f in upper.GetFootprints()}
    lf = {f.GetReference(): f for f in lower.GetFootprints()}
    assert uf['U12'].GetLayer() == p.F_Cu and uf['C37'].GetLayer() == p.B_Cu
    high = []
    for ref in ('C1', 'C11', 'C12', 'C8'):
        c8 = ref == 'C8'
        high.append({'ref': ref, 'circle': transform(lf[ref], 1.75 if c8 else 1.25, 0),
                     'radius': 4.3 if c8 else 3.4, 'height': 13 if c8 else 9})
    for ref in ('J43', 'J44'):
        high.append({'ref': ref, 'rect': rectangle(lf[ref], 5.25, 8.45, 1.27, 2.54), 'height': 8.75})
    high += [{'ref': 'Lower U2 R78E', 'rect': [135.8, 81, 146, 98], 'height': 11.2},
             {'ref': 'Lower relay stripe', 'rect': [45, 39.7, 146, 70.1], 'height': 20}]
    for f in lf.values():
        if 'KF128' in f.GetFPIDAsString():
            count = sum(bool(pad.GetNumber()) for pad in f.Pads())
            high.append({'ref': f.GetReference(), 'rect': rectangle(f, count * 2.54 + .6, 7,
                                                                    (count - 1) * 1.27, .3), 'height': 9.1})
    def distance(box, obstacle):
        if 'circle' in obstacle:
            x, y = obstacle['circle']
            return math.hypot(max(box[0] - x, x - box[2], 0),
                              max(box[1] - y, y - box[3], 0)) - obstacle['radius']
        other = obstacle['rect']
        if box[0] <= other[2] and box[2] >= other[0] and box[1] <= other[3] and box[3] >= other[1]:
            return 0
        return math.hypot(max(box[0] - other[2], other[0] - box[2], 0),
                          max(box[1] - other[3], other[1] - box[3], 0))
    cap_box = rectangle(uf['C37'], 3.4, 1.8)
    cap_floor = mechanics['board_to_board_clearance_mm'] - 1.8
    tail_floor = mechanics['upper_top_above_lower_top_mm'] - 4.6
    checks = []
    for item in high:
        gap = distance(cap_box, item)
        checks.append({'Upper': 'C37', 'Lower': item['ref'], 'xy_gap_mm': round(gap, 4),
                       'z_gap_if_xy_overlap_mm': round(cap_floor - item['height'], 4),
                       'collision': gap <= 0 and cap_floor <= item['height']})
    for pad in uf['U12'].Pads():
        x, y = pad.GetPosition().x / 1e6, pad.GetPosition().y / 1e6
        # Circumscribed radius of maximum0.74mm square lead, conservative at any rotation.
        half = .74 * math.sqrt(2) / 2
        box = [x - half, y - half, x + half, y + half]
        for item in high:
            gap = distance(box, item)
            checks.append({'Upper': 'U12.' + pad.GetNumber(), 'Lower': item['ref'],
                           'xy_gap_mm': round(gap, 4), 'z_gap_if_xy_overlap_mm': round(tail_floor - item['height'], 4),
                           'collision': gap <= 0 and tail_floor <= item['height']})
    assert min(cap_floor - 7, tail_floor - 7) > 0, 'Collision with ordinary Lower7mm allowance'
    assert not any(c['collision'] for c in checks), 'C37/U12 maximum interboard envelope collision'
    return {'C37_pose': pose(uf['C37']), 'C37_max_body_mm': [3.4, 1.8, 1.8],
            'C37_max_body_xy_mm': cap_box, 'C37_ordinary_lower_vertical_clearance_mm': round(cap_floor - 7, 4),
            'U12_pose': pose(uf['U12']), 'U12_tail_max_length_from_upper_F_mm': 4.6,
            'U12_tail_bottom_above_lower_F_mm': tail_floor, 'U12_max_square_lead_mm': .74,
            'checks': checks, 'collision_count': 0,
            'scope': 'Conservative actual-pose envelope calculation with nominal stack height; native DRC/courtyard and assembled sample checks are separate. No EMC certification claim.'}


def audit(root, before, approved_pose_manifest=None):
    root, before = Path(root).resolve(), Path(before).resolve()
    paths = [board_file(base, side, ext)
             for base in (before, root) for side in ('Upper', 'Lower')
             for ext in ('.kicad_pcb', '.kicad_pro', '.kicad_dru', '.kicad_sch', '.xml')]
    paths += [base / 'Stack-mechanics.json' for base in (before, root)]
    pose_manifest = None
    if approved_pose_manifest is not None:
        approved_pose_manifest = Path(approved_pose_manifest).resolve()
        paths.append(approved_pose_manifest)
        pose_manifest = json.loads(approved_pose_manifest.read_text())
    hashes = {str(path): sha(path) for path in paths}
    assert (before / 'Stack-mechanics.json').read_bytes() == (root / 'Stack-mechanics.json').read_bytes()
    boards = {}
    result = {'revision': 'R78 RS485 supply and Lower protected12V RC', 'result': 'PASS',
              'scope': 'Read-only source delta and selected maximum-envelope checks. Final native ERC/DRC, actual copper continuity and conducted/radiated EMC measurements remain separate gates.',
              'source_sha256': hashes, 'Stack_mechanics_byte_exact': True}
    for side in ('Lower', 'Upper'):
        name = board_name(side)
        oldpath, newpath = board_file(before, side, '.kicad_pcb'), board_file(root, side, '.kicad_pcb')
        old, new = p.LoadBoard(str(oldpath)), p.LoadBoard(str(newpath))
        boards[side] = new
        a, b = parse(oldpath.read_text()), parse(newpath.read_text())
        af, bf = fps_ast(a), fps_ast(b)
        of = {f.GetReference(): f for f in old.GetFootprints()}
        nf = {f.GetReference(): f for f in new.GetFootprints()}
        assert old.GetCopperLayerCount() == new.GetCopperLayerCount() == 2
        assert child(a, 'layers') == child(b, 'layers') and child(a, 'setup') == child(b, 'setup'), side + ' PCB layer/setup settings changed'
        edges = lambda tree: [z for z in children(tree, {'gr_line', 'gr_rect', 'gr_arc', 'gr_circle', 'gr_poly'})
                              if ['layer', '"Edge.Cuts"'] in z]
        assert edges(a) == edges(b), side + ' outline changed'
        assert zone_definitions(a) == zone_definitions(b), side + ' zone definition/keepout changed'
        if side == 'Upper':
            assert set(af) == set(bf), 'Upper footprint reference set changed'
            assert of['U12'].GetValue() == 'TLV1117LV33DCYR', 'Wrong before revision'
            assert nf['U12'].GetFPIDAsString() == R78_FP and nf['U12'].GetValue() == 'R-78K3.3-0.5'
            assert netmap(nf['U12']) == {'1': '/+12V_LOGIC', '2': '/GND', '3': '/+3V3_RS485'}
            verify_r78_pads(nf['U12'])
            assert nf['C37'].GetFPIDAsString() == of['C37'].GetFPIDAsString() == CAP_FP
            assert local_pad_geometry(of['C37']) == local_pad_geometry(nf['C37']), 'C37 local pad geometry changed'
            assert nf['C37'].GetValue() == '22uF 35V X5R' and netmap(nf['C37']) == {'1': '/+12V_LOGIC', '2': '/GND'}
            allowed_refs = {'U12', 'C37'}
            allowed_refs |= approved_resistor_poses(pose_manifest, hashes[str(oldpath)], af, bf, of, nf)
            # The static ADC sense route may move; its divider and MCU may not.
            # This permission does not extend to USB VBUS power or USB data/CC.
            for ref in ('R13', 'R14', 'U1'):
                assert footprint_equal(af[ref], bf[ref]), ref + ' ADC divider/MCU footprint changed'
                assert netmap(of[ref]) == netmap(nf[ref]), ref + ' ADC divider/MCU pad net changed'
                assert pose(of[ref]) == pose(nf[ref]), ref + ' ADC divider/MCU placement changed'
            for ref in ('R2', 'SW2', 'U1'):
                assert footprint_equal(af[ref], bf[ref]), ref + ' BOOT component changed'
                assert netmap(of[ref]) == netmap(nf[ref]), ref + ' BOOT component pad net changed'
        else:
            assert set(bf) - set(af) == {'R12', 'C13'} and not set(af) - set(bf)
            expected_d3 = copy.deepcopy(af['D3'])
            for pad in children(expected_d3, {'pad'}):
                if pad[1] == '"1"':
                    net = child(pad, 'net')
                    assert net == ['net', '"/+12V_LOGIC"']
                    net[1] = '"/+12V_LOGIC_RAW"'
            assert footprint_equal(expected_d3, bf['D3']), 'D3 changed beyond cathode net'
            assert nf['R12'].GetValue() == '1R / 2W pulse' and nf['R12'].GetFPIDAsString() == 'RelayBoard:R_2512_6332Metric'
            assert netmap(nf['R12']) == {'1': '/+12V_LOGIC_RAW', '2': '/+12V_LOGIC'}
            assert nf['C13'].GetValue() == '100nF / 50V X7R' and nf['C13'].GetFPIDAsString() == 'RelayBoard:C_0805_2012Metric'
            assert netmap(nf['C13']) == {'1': '/+12V_LOGIC', '2': '/GND'}
            allowed_refs = {'D3'}
        for ref in set(af) & set(bf) - allowed_refs:
            assert footprint_equal(af[ref], bf[ref]), side + ' unapproved footprint mutation: ' + ref
        oldcu, newcu = copper(old), copper(new)
        for net in USB_NETS:
            assert geometry_counter(oldcu, net) == geometry_counter(newcu, net), 'USB geometry changed: ' + net
        if side == 'Upper':
            assert geometry_counter(oldcu, '/USB_VBUS'), 'USB VBUS power source geometry missing'
            assert geometry_counter(oldcu, '/USB_VBUS') == geometry_counter(newcu, '/USB_VBUS'), 'USB VBUS power copper changed'
            assert geometry_counter(oldcu, '/ESP_EN') == geometry_counter(newcu, '/ESP_EN'), 'ESP_EN reset copper changed'
            boot_approval = approved_boot_geometry(pose_manifest, oldcu, newcu)
        result[side] = {'before_pcb_sha256': hashes[str(oldpath)], 'pcb_sha256': hashes[str(newpath)],
                        'footprints': len(nf), 'outline_layers_setup_exact': True, 'zone_definitions_keepouts_exact': True,
                        'allowed_changed_existing_refs': sorted(allowed_refs),
                        'changed_existing_poses': {r: {'before': pose(of[r]), 'after': pose(nf[r])}
                                                   for r in set(of) & set(nf) if pose(of[r]) != pose(nf[r])},
                        'all_other_footprint_normalized_AST_exact': True,
                        'project_rules': project_rules(oldpath, newpath, side),
                        'all_six_USB_data_CC_geometry_exact_from_current_before': True,
                        'copper_delta': copper_delta(oldcu, newcu, ALLOWED_COPPER[side]),
                        'xml': audit_xml(oldpath.with_suffix('.xml'), newpath.with_suffix('.xml'), side)}
        if side == 'Upper':
            result[side]['ESP_BOOT_copper_exception'] = {
                **boot_approval,
                'R2_SW2_U1_full_footprints_and_pad_nets_exact': True,
                'ESP_EN_reset_geometry_exact': True,
            }
            result[side]['USB_VBUS_SENSE_copper_only_exception'] = {
                'net': '/USB_VBUS_SENSE',
                'R13_R14_U1_full_footprints_pad_nets_and_poses_exact': True,
                'USB_VBUS_power_geometry_exact': True,
                'USB_data_and_CC_six_net_geometry_exact': True,
            }
    result['mechanical_envelopes'] = mechanical(boards['Upper'], boards['Lower'], json.loads((root / 'Stack-mechanics.json').read_text()))
    result['approved_resistor_pose_manifest'] = ({'path': str(approved_pose_manifest),
                                                'sha256': hashes[str(approved_pose_manifest)],
                                                'exact_approved_delta': pose_manifest}
                                               if approved_pose_manifest is not None else None)
    assert hashes == {str(path): sha(path) for path in paths}, 'Source files changed during read-only audit'
    result['CAD_files_not_written'] = True
    return result


def main():
    import wx
    app = wx.App(False)
    wx.Log.EnableLogging(False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, required=True)
    parser.add_argument('--before-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--approved-pose-manifest', type=Path,
                        help='Exact R55/R56 placement delta and optional complete BOOT copper geometry; only R56 may flip F-to-B, with all pad fields unchanged')
    args = parser.parse_args()
    assert args.output.suffix == '.json', 'Output must be a JSON report'
    result = audit(args.project_root, args.before_root, args.approved_pose_manifest)
    assert str(args.output.resolve()) not in result['source_sha256'], 'Report cannot overwrite source'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'result': result['result'], **{s: result[s]['copper_delta']['counts'] for s in ('Lower', 'Upper')},
                      'mechanical_collisions': result['mechanical_envelopes']['collision_count']}, indent=2))


if __name__ == '__main__':
    main()
