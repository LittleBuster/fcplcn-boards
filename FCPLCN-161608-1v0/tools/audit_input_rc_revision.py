"""Read-only source audit of the sixteen before-TLP input RC filters.

Run with KiCad's Python after PCB freeze. Only --output is written. PASS binds
source inventory, pin nets, metadata, footprint assets and the authorized local
placement delta; it is not a native DRC/ERC or filled-copper/EMC qualification.
The previous TLP2363 auditor and its historical reports are never modified.
"""
from pathlib import Path
import argparse
import collections
import copy
import csv
import json
import math
import sys

from audit_tlp2363_revision import (
    sha, digest, norm_net, natural, parse, children, child, ast_fields,
    ast_without_pad_nets, unordered_children, normalized_hidden_bomgroup_thickness,
    xml_fields, xml_pins, field, pin_map, pose, pad_geometry, footprint_tree_map,
    parse_components, purchased,
)

CPU = 'FCPLCN-CPU-08-1v0'
RLY = 'FCPLCN-RLY-1616-1v0'
NATIVE = ('.kicad_pcb', '.kicad_sch', '.kicad_pro', '.kicad_dru', '.xml')
NEW = {f'R{i}' for i in range(161, 177)} | {f'C{i}' for i in range(141, 157)} | {f'R{i}' for i in range(181,197)}
MOVABLE = ({f'U{i}' for i in range(21, 37)} | {f'R{i}' for i in range(101, 117)}
           | {f'D{i}' for i in range(101, 117)} | {f'D{i}' for i in range(121, 137)}
           | {f'R{i}' for i in range(121, 137)} | {f'C{i}' for i in range(101, 117)}
           | {f'C{i}' for i in range(121, 137)} | {f'R{i}' for i in range(141, 157)})
WETTING = {f'R{i}' for i in range(101, 117)}
TLP_DATASHEET = 'https://toshiba.semicon-storage.com/info/TLP2363_datasheet_en_20251218.pdf?did=67887&prodName=TLP2363'
RES_DATASHEET = 'https://www.vishay.com/docs/20115/crcwhp.pdf'
CAP_DATASHEET = 'https://product.tdk.com/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c2012x7r1h105k125ab.pdf'
CAP_SOURCE = 'https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C2012X7R1H105K125AB'
KNOWN_TECHNICAL_FIELDS = {'MPN', 'Manufacturer', 'Tolerance', 'PowerRating', 'Voltage', 'Dielectric',
                          'Height_Max', 'BOMGroup', 'BOMPackage', 'SupplierPartNumber', 'SourceURL',
                          'ResistorType', 'PackageDrawing', 'Description'}


def graphics(tree, layer=None, branding=False):
    result = []
    for item in tree:
        if not isinstance(item, list) or not item or not item[0].startswith('gr_'):
            continue
        if layer and child(item, 'layer') != ['layer', json.dumps(layer)]:
            continue
        if branding and not (item[0] == 'gr_text' and any(text in item[1] for text in ('FCPLCN-', 'Denisov Foundation Ltd.'))):
            continue
        result.append(item)
    return sorted(result, key=lambda item: json.dumps(item))


def xml_metadata(component):
    return {'value': component.findtext('value', ''), 'footprint': component.findtext('footprint', ''),
            'datasheet': component.findtext('datasheet', ''), 'fields': xml_fields(component)}


def graphic_uuid(node):
    item=child(node,'uuid')
    return item[1] if item else None


def without_graphic_pose(node, text=False):
    result=copy.deepcopy(node)
    result[:]=[p for p in result if not (isinstance(p,list) and p and p[0]=='at')]
    if text:result[1]='"<authorized revision text>"'
    return unordered_children(result)


def run(root, before, pcb):
    from bom_common import component_record, component_key
    from passive_specifications import component_spec
    errors, gates, notes, tracked = [], {}, [], {}
    pin_mismatches, metadata_mismatches, library_mismatches = [], [], []
    schematic_metadata_mismatches = []
    source_changed_during_audit = []
    authorized_silkscreen_deltas = []
    library_checks, channels, serialization_equivalences = [], [], []

    def require(condition, description):
        gates[description] = bool(condition)
        if not condition:
            errors.append(description)

    def track(path):
        path = Path(path).resolve()
        if path not in tracked:
            tracked[path] = sha(path) if path.exists() else None
        return path

    def source(board, ext, side=root):
        return track(side / board / (board + ext))

    track(Path(__file__))
    for name in ('audit_tlp2363_revision.py', 'bom_common.py', 'passive_specifications.py'):
        track(root / 'tools' / name)
    for ext in NATIVE:
        a, b = source(CPU, ext, before), source(CPU, ext)
        require(a.exists() and b.exists() and sha(a) == sha(b), 'CPU native byte exact ' + ext)
    for ext in ('.kicad_pro', '.kicad_dru'):
        a, b = source(RLY, ext, before), source(RLY, ext)
        require(a.exists() and b.exists() and sha(a) == sha(b), 'RLY project/rules byte exact ' + ext)
    a, b = track(before/'Stack-mechanics.json'), track(root/'Stack-mechanics.json')
    require(a.exists() and b.exists() and sha(a) == sha(b), 'Stack mechanical specification byte exact')

    board_data = {}
    template_board = pcb.BOARD()
    library_root = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
    global_groups = collections.Counter()
    global_refs = {'Lower': [], 'Upper': []}
    for board_name, purchase_count, physical_count, side in ((CPU, 148, 148, 'Upper'), (RLY, 248, 251, 'Lower')):
        board = pcb.LoadBoard(str(source(board_name, '.kicad_pcb')))
        schematic_tree = parse(source(board_name, '.kicad_sch').read_text())
        schematic_symbols = children(schematic_tree, {'symbol'})
        schematic_refs = {ast_fields(n)['Reference']: n for n in schematic_symbols}
        require(len(schematic_symbols)==len(schematic_refs), board_name+' unique schematic symbol references')
        xml, components, xml_count = parse_components(source(board_name, '.xml'))
        fps_list = list(board.GetFootprints())
        fps = {fp.GetReference(): fp for fp in fps_list}
        xpins, duplicated_xml = xml_pins(xml)
        ppins, duplicate_pad_conflicts = {}, []
        for ref, fp in fps.items():
            for pad in fp.Pads():
                if not pad.GetNumber():
                    continue
                key, value = (ref, pad.GetNumber()), norm_net(pad.GetNetname())
                if key in ppins and ppins[key] != value:
                    duplicate_pad_conflicts.append([ref, pad.GetNumber()])
                ppins[key] = value
        require(len(fps_list) == len(fps), board_name + ' unique PCB references')
        require(xml_count == len(components), board_name + ' unique XML references')
        require(not duplicated_xml, board_name + ' XML pins occur once')
        require(not duplicate_pad_conflicts, board_name + ' duplicate physical pads have consistent nets')
        require(set(fps) == set(components), board_name + ' exact full XML/PCB inventory')
        schematic_board_refs = {ref for ref,n in schematic_refs.items() if child(n, 'on_board') == ['on_board', 'yes']}
        require(schematic_board_refs == set(components), board_name + ' exact schematic/XML physical reference inventory')
        for ref in sorted(set(components) & set(schematic_refs), key=natural):
            sf, comp = ast_fields(schematic_refs[ref]), components[ref]
            comparisons = [('Value', comp.findtext('value', ''), sf.get('Value', '')),
                           ('Footprint', comp.findtext('footprint', ''), sf.get('Footprint', '')),
                           ('Datasheet', comp.findtext('datasheet', ''), sf.get('Datasheet', ''))]
            comparisons.extend((name,value,sf.get(name,'')) for name,value in xml_fields(comp).items() if name not in {'Reference','Value'})
            for name,actual,expected in comparisons:
                if actual != expected:
                    schematic_metadata_mismatches.append({'board':board_name,'ref':ref,'field':name,'XML':actual,'schematic':expected})
        require(not [m for m in schematic_metadata_mismatches if m['board']==board_name], board_name + ' all schematic/XML values and metadata match')
        for key in sorted(set(xpins) | set(ppins)):
            if xpins.get(key) != ppins.get(key):
                pin_mismatches.append({'board': board_name, 'ref': key[0], 'pin': key[1],
                                       'XML': xpins.get(key), 'PCB': ppins.get(key)})
        require(xpins == ppins, board_name + ' all XML/PCB pin nets match')
        for ref in sorted(set(fps) & set(components), key=natural):
            fp, comp = fps[ref], components[ref]
            xf = xml_fields(comp)
            comparisons = [('Value', fp.GetValue(), comp.findtext('value', '')),
                           ('Footprint', fp.GetFPIDAsString(), comp.findtext('footprint', '')),
                           ('Datasheet', field(fp, 'Datasheet'), comp.findtext('datasheet', ''))]
            for key in sorted((set(xf) | KNOWN_TECHNICAL_FIELDS) - {'Reference', 'Value', 'Footprint', 'Datasheet'}):
                comparisons.append((key, field(fp, key), xf.get(key, '')))
            for key, actual, expected in comparisons:
                if actual != expected:
                    metadata_mismatches.append({'board': board_name, 'ref': ref, 'field': key,
                                                'PCB': actual, 'XML': expected})
            require(fp.GetFPIDAsString().count(':') == 1, board_name + ' ' + ref + ' valid FPID')
            lib, name = fp.GetFPIDAsString().split(':', 1)
            local_dir = root / board_name / (lib + '.pretty')
            asset = local_dir / (name + '.kicad_mod')
            libdir = local_dir if asset.exists() else library_root / (lib + '.pretty')
            asset = track(libdir / (name + '.kicad_mod'))
            require(asset.exists(), board_name + ' ' + ref + ' library footprint exists')
            if asset.exists():
                template = pcb.FootprintLoad(str(libdir), name)
                require(template is not None, board_name + ' ' + ref + ' library footprint loads')
                if template is not None:
                    template_board.Add(template)
                    if fp.GetLayer() == pcb.B_Cu:
                        template.Flip(template.GetPosition(), False)
                    template.SetOrientationDegrees(fp.GetOrientationDegrees())
                    template.SetPosition(fp.GetPosition())
                    actual, expected = pad_geometry(fp), pad_geometry(template)
                    if actual != expected:
                        library_mismatches.append({'board': board_name, 'ref': ref, 'asset': str(asset),
                                                   'actual_pad_geometry': actual, 'asset_pad_geometry': expected})
                    require(actual == expected, board_name + ' ' + ref + ' pad geometry matches library')
                    library_checks.append({'board': board_name, 'ref': ref, 'FPID': fp.GetFPIDAsString(),
                                           'asset': str(asset), 'asset_sha256': sha(asset)})
        require(not [m for m in metadata_mismatches if m['board'] == board_name],
                board_name + ' all technical metadata matches XML')
        purchases = [c for c in components.values() if purchased(c)]
        excluded = sorted(set(components) - {c.get('ref') for c in purchases}, key=natural)
        require(len(purchases) == purchase_count, board_name + ' purchased count ' + str(purchase_count))
        require(len(fps) == physical_count, board_name + ' physical footprint count ' + str(physical_count))
        require(excluded == (['TP5', 'TP6', 'TP7'] if board_name == RLY else []), board_name + ' exact nonpurchased testpad inventory')
        require(not any(c.get('ref').startswith(('TP', '#')) for c in purchases), board_name + ' no testpad or power flag purchased')
        groups = collections.Counter(component_key(component_record(c)) for c in purchases)
        global_groups.update(groups)
        global_refs[side] = [c.get('ref') for c in purchases]
        rows = list(csv.DictReader(track(root/board_name/'BOM.csv').open(encoding='utf-8-sig')))
        refs = [ref.strip() for row in rows for ref in row['refs'].split(',')]
        require(collections.Counter(refs) == collections.Counter(c.get('ref') for c in purchases), board_name + ' BOM refs equal XML purchases')
        require(sum(int(row['qty']) for row in rows) == purchase_count, board_name + ' BOM quantities equal XML purchases')
        csv_groups = collections.Counter()
        for index,row in enumerate(rows,1):
            row_refs=[ref.strip() for ref in row['refs'].split(',') if ref.strip()]
            row_key=component_key(row)
            csv_groups[row_key] += int(row['qty'])
            require(int(row['qty'])==len(row_refs), board_name+' BOM row'+str(index)+' quantity equals its references')
            require(all(ref in components and purchased(components[ref]) and component_key(component_record(components[ref]))==row_key for ref in row_refs),
                    board_name+' BOM row'+str(index)+' references belong to this exact purchasing group')
            actual_fpids={components[ref].findtext('footprint','') for ref in row_refs if ref in components}
            require({p.strip() for p in row['cad_footprints'].split(';')}==actual_fpids
                    and {p.strip() for p in row['footprint'].split(';')}==actual_fpids,
                    board_name+' BOM row'+str(index)+' exact CAD footprint inventory')
        require(csv_groups == groups and len(rows) == len(groups), board_name + ' all BOM purchasing groups equal XML')
        require(board.GetCopperLayerCount() == 2, board_name + ' two copper layers')
        board_data[board_name] = {'board': board, 'fps': fps, 'xml': xml, 'components': components,
                                  'xpins': xpins, 'ppins': ppins, 'schematic_tree': schematic_tree, 'schematic_refs': schematic_refs, 'purchased': len(purchases),
                                  'physical': len(fps), 'excluded': excluded, 'BOM_groups': len(groups)}

    combined = list(csv.DictReader(track(root/'BOM-combined.csv').open(encoding='utf-8-sig')))
    require(sum(int(row['total_qty']) for row in combined) == 396, 'Combined BOM purchased total396')
    combined_groups = collections.Counter()
    for index,row in enumerate(combined,1):
        record = dict(row, value=row['component'], footprint=row['cad_footprints'])
        row_key=component_key(record)
        combined_groups[row_key] += int(row['total_qty'])
        row_total=0;actual_fpids=set()
        for prefix,board_name in (('lower',RLY),('upper',CPU)):
            row_refs=[ref.strip() for ref in row[prefix+'_references'].split(',') if ref.strip()]
            comps=board_data[board_name]['components']
            require(int(row[prefix+'_qty'])==len(row_refs), 'Combined BOM row'+str(index)+' '+prefix+' quantity equals references')
            require(all(ref in comps and purchased(comps[ref]) and component_key(component_record(comps[ref]))==row_key for ref in row_refs),
                    'Combined BOM row'+str(index)+' '+prefix+' references belong to this exact purchasing group')
            actual_fpids.update(comps[ref].findtext('footprint','') for ref in row_refs if ref in comps)
            row_total+=len(row_refs)
        require(int(row['total_qty'])==row_total, 'Combined BOM row'+str(index)+' total equals both reference lists')
        require({p.strip() for p in row['cad_footprints'].split(';')}==actual_fpids,
                'Combined BOM row'+str(index)+' exact CAD footprint inventory')
    require(combined_groups == global_groups and len(combined) == len(global_groups), 'Combined BOM all purchasing groups equal both XMLs')
    for side, prefix in (('Lower', 'lower'), ('Upper', 'upper')):
        refs = [ref.strip() for row in combined for ref in row[prefix+'_references'].split(',') if ref.strip()]
        require(collections.Counter(refs) == collections.Counter(global_refs[side]), 'Combined BOM ' + side + ' exact reference inventory')
        require(sum(int(row[prefix+'_qty']) for row in combined) == len(global_refs[side]), 'Combined BOM ' + side + ' quantity exact')

    old_path = source(RLY, '.kicad_pcb', before)
    old = pcb.LoadBoard(str(old_path))
    old_fp = {fp.GetReference(): fp for fp in old.GetFootprints()}
    current = board_data[RLY]
    new_fp = current['fps']
    old_xml, old_components, old_xml_count = parse_components(source(RLY, '.xml', before))
    old_xpins, duplicate_old_xml = xml_pins(old_xml)
    old_schematic = parse(source(RLY, '.kicad_sch', before).read_text())
    old_schematic_symbols=children(old_schematic, {'symbol'})
    old_schematic_refs = {ast_fields(n)['Reference']:n for n in old_schematic_symbols}
    require(len(old_schematic_symbols)==len(old_schematic_refs), 'Before RLY unique schematic symbol references')
    new_schematic_refs = current['schematic_refs']
    require(set(new_schematic_refs)-set(old_schematic_refs)==NEW and not set(old_schematic_refs)-set(new_schematic_refs), 'Exact48 schematic reference additions and no old symbol removed')
    old_embedded = {json.loads(n[1]).rsplit(':',1)[-1]:n for n in children(child(old_schematic,'lib_symbols'),{'symbol'})}
    new_embedded = {json.loads(n[1]).rsplit(':',1)[-1]:n for n in children(child(current['schematic_tree'],'lib_symbols'),{'symbol'})}
    require(set(new_embedded)-set(old_embedded)=={'DI16_LED_Shunt_Resistor'} and not set(old_embedded)-set(new_embedded), 'Only compact LED shunt symbol added to embedded library')
    require(all(old_embedded[k]==new_embedded[k] for k in old_embedded), 'All old embedded symbol definitions unchanged')
    old_library=parse(track(before/RLY/'RelayBoard.kicad_sym').read_text())
    new_library=parse(track(root/RLY/'RelayBoard.kicad_sym').read_text())
    old_definitions={json.loads(n[1]):n for n in children(old_library,{'symbol'})}
    new_definitions={json.loads(n[1]):n for n in children(new_library,{'symbol'})}
    require(set(new_definitions)-set(old_definitions)=={'DI16_LED_Shunt_Resistor'} and not set(old_definitions)-set(new_definitions), 'Only compact LED shunt symbol added to local symbol library')
    require(all(old_definitions[k]==new_definitions[k] for k in old_definitions), 'All old local symbol definitions unchanged')
    embedded_shunt=copy.deepcopy(new_embedded.get('DI16_LED_Shunt_Resistor',[]))
    if embedded_shunt:embedded_shunt[1]=json.dumps('DI16_LED_Shunt_Resistor')
    require(embedded_shunt==new_definitions.get('DI16_LED_Shunt_Resistor'), 'New compact shunt embedded/local definitions identical')
    for ref,node in old_schematic_refs.items():
        new_node = new_schematic_refs.get(ref,[])
        require(child(node,'uuid')==child(new_node,'uuid') and children(node,{'pin'})==children(new_node,{'pin'}), ref+' schematic symbol/pin UUIDs exact')
        if ref not in MOVABLE:
            require(node==new_node, ref+' unrelated complete schematic symbol AST exact')
    require(len(old_fp) == old_xml_count == len(old_components) == 203, 'Before RLY203 physical/XML parts')
    require(sum(purchased(c) for c in old_components.values()) == 200, 'Before RLY200 purchased parts')
    require(not duplicate_old_xml, 'Before XML each pin occurs once')
    require(set(new_fp)-set(old_fp) == NEW and not set(old_fp)-set(new_fp), 'Exact48 new RC/shunt references and none removed')
    require(set(current['components'])-set(old_components) == NEW, 'Exact48 new RC/shunt XML references')
    old_tree, new_tree = parse(old_path.read_text()), parse(source(RLY, '.kicad_pcb').read_text())
    old_ast, new_ast = footprint_tree_map(old_tree), footprint_tree_map(new_tree)
    require(graphics(old_tree, 'Edge.Cuts') == graphics(new_tree, 'Edge.Cuts'), 'RLY complete outline exact')
    branding = graphics(old_tree, branding=True)
    require(len(branding) >= 2 and branding == graphics(new_tree, branding=True), 'RLY model and Denisov Foundation branding exact')
    old_texts={graphic_uuid(n):n for n in children(old_tree,{'gr_text'})}
    new_texts={graphic_uuid(n):n for n in children(new_tree,{'gr_text'})}
    require(set(old_texts)==set(new_texts), 'RLY board-text UUID inventory unchanged')
    moved_input_legend=0;revision_changes=0
    for uid,a in old_texts.items():
        b=new_texts.get(uid)
        if b is None or a==b:continue
        text_a,text_b=json.loads(a[1]),json.loads(b[1])
        pos_a,pos_b=child(a,'at'),child(b,'at')
        back_layer=child(a,'layer')==child(b,'layer')==['layer','"B.SilkS"']
        is_input=(back_layer and pos_a is not None and math.isclose(float(pos_a[2]),117.7)
                  and text_a in ({'G'}|{str(i) for i in range(1,17)}))
        is_revision=back_layer and text_a=='r1.9.2 EMI'
        is_power_legend=(back_layer and text_a in {'+','-','12V'} and pos_a is not None and 116<=float(pos_a[2])<=119)
        if is_input:
            require(text_a==text_b and pos_b is not None and math.isclose(float(pos_b[2]),124.8)
                    and pos_a[1]==pos_b[1] and pos_a[3:]==pos_b[3:]
                    and without_graphic_pose(a)==without_graphic_pose(b),
                    'Authorized B input legend Y117.7-to124.8 '+uid)
            moved_input_legend+=1
            reason='Move existing duplicate input legend behind PTH pads for new RC capacitors; text and X/rotation/style retained.'
        elif is_revision:
            require(text_b=='1v0 RC IN' and without_graphic_pose(a,True)==without_graphic_pose(b,True),
                    'Authorized B technical revision rename and relocation')
            revision_changes+=1
            reason='Technical revision updated and relocated; product and company branding remains separately byte exact.'
        elif is_power_legend:
            require(text_a==text_b and without_graphic_pose(a)==without_graphic_pose(b), 'Authorized B power legend relocation '+uid)
            reason='Relocate duplicate B power legend without changing electrical text.'
        else:
            require(False,'Unrelated board text changed '+uid)
            reason='UNAUTHORIZED'
        authorized_silkscreen_deltas.append({'uuid':json.loads(uid),'before_text':text_a,'after_text':text_b,
                                           'layer':'B.SilkS' if back_layer else str(child(b,'layer')),
                                           'before_position_mm_deg':[float(p) for p in pos_a[1:]] if pos_a else None,
                                           'after_position_mm_deg':[float(p) for p in pos_b[1:]] if pos_b else None,
                                           'reason':reason})
    require(moved_input_legend==32, 'Exactly32 authorized duplicate B input labels moved to124.8mm')
    require(revision_changes==1, 'Exactlyone B technical revision updated to1v0 RC IN')

    allowed_old_pin_changes = {(f'U{20+i}', '3'): (f'DI{i}', f'DIF{i}') for i in range(1, 17)}
    allowed_old_pin_changes.update({(f'D{100+i}', '2'): (f'DI{i}', f'DIF{i}') for i in range(1, 17)})
    old_net_deltas, old_metadata_deltas, moved = [], [], {}
    unrelated_footprint_deltas = []
    for ref in sorted(set(old_fp) & set(new_fp), key=natural):
        a, b = old_fp[ref], new_fp[ref]
        expected_pins = pin_map(a)
        for pin, oldnet in list(expected_pins.items()):
            if (ref, pin) in allowed_old_pin_changes:
                require(oldnet == allowed_old_pin_changes[(ref, pin)][0], ref + ' baseline diode-return net is DI')
                expected_pins[pin] = allowed_old_pin_changes[(ref, pin)][1]
        require(pin_map(b) == expected_pins, ref + ' only authorized before-TLP old pin-net change')
        if pose(a) != pose(b):
            moved[ref] = {'before_nm_deg_layer': pose(a), 'after_nm_deg_layer': pose(b)}
        require(a.GetFPIDAsString() == b.GetFPIDAsString(), ref + ' original FPID unchanged')
        if ref not in MOVABLE:
            require(pose(a) == pose(b), ref + ' unrelated pose exact')
            require(pad_geometry(a, True) == pad_geometry(b, True), ref + ' unrelated world pad geometry exact')
            left = unordered_children(ast_without_pad_nets(old_ast[ref]))
            right = unordered_children(ast_without_pad_nets(new_ast[ref]))
            if ref == 'U9' and left != right:
                old_field = next((f for f in a.GetFields() if f.GetName() == 'BOMGroup'), None)
                new_field = next((f for f in b.GetFields() if f.GetName() == 'BOMGroup'), None)
                semantically_equal = (old_field is not None and new_field is not None
                                      and old_field.GetTextThickness() == new_field.GetTextThickness() == 150000
                                      and not old_field.IsVisible() and not new_field.IsVisible())
                normalized_a = unordered_children(normalized_hidden_bomgroup_thickness(left))
                normalized_b = unordered_children(normalized_hidden_bomgroup_thickness(right))
                if semantically_equal and normalized_a == normalized_b:
                    left, right = normalized_a, normalized_b
                    serialization_equivalences.append({'ref': 'U9', 'field': 'BOMGroup',
                                                       'native_before_and_after_thickness_nm': 150000,
                                                       'native_before_and_after_visible': False,
                                                       'scope': 'Only absent vs explicit0.15mm default hidden F.Fab font thickness; all other source AST values exact.'})
            if left != right:
                unrelated_footprint_deltas.append(ref)
            require(left == right, ref + ' unrelated complete footprint AST exact')
        if ref not in WETTING:
            require(a.GetValue() == b.GetValue(), ref + ' original value unchanged')
            require(xml_metadata(old_components[ref]) == xml_metadata(current['components'][ref]), ref + ' original technical metadata unchanged')
        else:
            require(a.GetValue() == '1.5k' and b.GetValue() == '1.2k', ref + ' authorized1.5k-to1.2k value')
            # No old ordering/rating fields outside these three may change.
            old_meta = xml_metadata(old_components[ref])
            expected_meta = copy.deepcopy(old_meta)
            expected_meta['value'] = '1.2k'
            expected_meta['fields']['MPN'] = 'CRCW08051K20FKTAHP'
            expected_meta['fields']['BOMGroup'] = 'R-0805-1.2k-1pct-500mW-Vishay-HP'
            require(expected_meta == xml_metadata(current['components'][ref]), ref + ' only authorized wetting ordering metadata delta')
    require(set(moved) <= MOVABLE, 'Only explicitly authorized existing input references moved')
    for key, oldnet in sorted(old_xpins.items()):
        newnet = current['xpins'].get(key)
        if key in allowed_old_pin_changes:
            require((oldnet, newnet) == allowed_old_pin_changes[key], 'XML authorized net change ' + '/'.join(key))
            old_net_deltas.append({'ref': key[0], 'pin': key[1], 'before': oldnet, 'after': newnet})
        else:
            require(oldnet == newnet, 'XML unrelated pin net unchanged ' + '/'.join(key))
    require(len(old_net_deltas) == 32, 'Exactly32 old pins changed DI-to-DIF')
    for ref in ('J43', 'J44', 'U9', 'C14'):
        require(ref in old_fp and ref in new_fp, ref + ' protected stack/FRAM part exists')
        if ref in old_fp and ref in new_fp:
            require(pose(old_fp[ref]) == pose(new_fp[ref]) and pad_geometry(old_fp[ref], True) == pad_geometry(new_fp[ref], True)
                    and pin_map(old_fp[ref]) == pin_map(new_fp[ref]), ref + ' stack/FRAM world pads and nets exact')

    for i in range(1, 17):
        u, wet, reverse, tvs, pull, filt, series, bypass, rc_r, rc_c, shunt = (
            f'U{20+i}', f'R{100+i}', f'D{100+i}', f'D{120+i}', f'R{120+i}',
            f'C{100+i}', f'R{140+i}', f'C{120+i}', f'R{160+i}', f'C{140+i}', f'R{180+i}')
        led, raw, filtered, exposed, damped = f'Net-(D{100+i}-K)', f'OPTO{i}_RAW', f'IN{i}', f'DI{i}', f'DIF{i}'
        topology = {u: {'1': led, '3': damped, '4': 'GND', '5': raw, '6': '+3V3'},
                    wet: {'1': '+12V_SYS', '2': led}, reverse: {'1': led, '2': damped},
                    tvs: {'1': exposed, '2': 'GND'}, pull: {'1': '+3V3', '2': raw},
                    filt: {'1': filtered, '2': 'GND'}, series: {'1': raw, '2': filtered},
                    bypass: {'1': '+3V3', '2': 'GND'}, rc_r: {'1': damped, '2': exposed},
                    rc_c: {'1': damped, '2': 'GND'}, shunt: {'1': led, '2': damped}}
        for ref, pins in topology.items():
            require(ref in new_fp and pin_map(new_fp[ref]) == pins, ref + ' exact full channel topology')
        values = {u: ('TLP2363', 'RelayBoard:TLP2363_5pin_SO6'),
                  wet: ('1.2k', 'RelayBoard:R_0805_Wetting'),
                  reverse: ('1N4148W-7-F', 'RelayBoard:D_SOD-123'),
                  tvs: ('PTVS15VS1UR', 'RelayBoard:Nexperia_CFP3_SOD-123W'),
                  pull: ('10k', 'RelayBoard:R_0805_2012Metric'),
                  series: ('470R', 'RelayBoard:R_0805_2012Metric'),
                  filt: ('100nF', 'RelayBoard:C_0805_2012Metric'),
                  bypass: ('100nF', 'RelayBoard:C_0805_2012Metric'),
                  rc_r: ('220R', 'RelayBoard:R_0805_2012Metric'),
                  rc_c: ('1uF', 'RelayBoard:C_0805_2012Metric'),
                  shunt: ('4.7k', 'RelayBoard:R_0805_2012Metric')}
        for ref, (value, fp_id) in values.items():
            require(ref in new_fp and new_fp[ref].GetValue() == value and new_fp[ref].GetFPIDAsString() == fp_id,
                    ref + ' exact channel value/FPID')
        required = {
            u: {'MPN': 'TLP2363(TPL,E', 'Manufacturer': 'Toshiba', 'PackageDrawing': '11-4L1S', 'Datasheet': TLP_DATASHEET},
            wet: {'MPN': 'CRCW08051K20FKTAHP', 'Manufacturer': 'Vishay', 'Tolerance': '1%', 'PowerRating': '0.5 W', 'BOMGroup': 'R-0805-1.2k-1pct-500mW-Vishay-HP', 'BOMPackage': '0805', 'Datasheet': RES_DATASHEET},
            rc_r: {'MPN': 'CRCW0805220RFKTAHP', 'Manufacturer': 'Vishay', 'Tolerance': '1%', 'PowerRating': '0.5 W', 'BOMGroup': 'R-0805-220R-1pct-500mW-Vishay-HP', 'BOMPackage': '0805', 'Datasheet': RES_DATASHEET},
            rc_c: {'MPN': 'C2012X7R1H105K125AB', 'Manufacturer': 'TDK', 'Tolerance': '10%', 'Voltage': '50 V', 'Dielectric': 'X7R', 'Height_Max': '1.45 mm', 'BOMGroup': 'C-0805-1uF-50V-X7R-10pct-TDK', 'BOMPackage': '0805', 'Datasheet': CAP_DATASHEET, 'SourceURL': CAP_SOURCE},
            shunt: {'Tolerance':'1%', 'PowerRating':'0.125 W', 'BOMGroup':'R-0805-4.7k-1pct-125mW', 'BOMPackage':'0805'},
            pull: {'Tolerance': '1%'}, series: {'Tolerance': '1%', 'PowerRating': '0.125 W'},
            filt: {'Tolerance': '10%', 'Voltage': '50 V', 'Dielectric': 'X7R'},
            bypass: {'Tolerance': '10%', 'Voltage': '50 V', 'Dielectric': 'X7R'},
        }
        for ref, fields in required.items():
            for name, expected in fields.items():
                require(ref in new_fp and field(new_fp[ref], name) == expected, ref + ' exact approved ' + name)
        for ref in (wet, rc_r, rc_c, shunt):
            spec = component_spec('Lower', ref)
            require(spec is not None and spec['value'] == current['components'][ref].findtext('value'), ref + ' common catalog value exact')
            if spec:
                actual = xml_fields(current['components'][ref])
                require(all(actual.get(k) == v for k, v in spec['fields'].items())
                        and current['components'][ref].findtext('datasheet', '') == spec.get('datasheet', ''), ref + ' common catalog fields exact')
        # Pin-to-pad distances are lower bounds, not electrical loop lengths.
        parts = {ref: {p.GetNumber(): p for p in new_fp[ref].Pads()} for ref in (u, bypass, rc_c)}
        def distance(a, b):
            pa, pb = a.GetPosition(), b.GetPosition()
            return math.hypot(pa.x-pb.x, pa.y-pb.y)/1e6
        bypass_dist = [distance(parts[u]['6'], parts[bypass]['1']), distance(parts[u]['4'], parts[bypass]['2'])]
        require(all(d < 10 for d in bypass_dist), u + ' existing bypass pad-distance lower bounds under10mm')
        channels.append({'channel': i, 'topology': topology,
                         'bypass_pad_distance_lower_bounds_mm': bypass_dist,
                         'RC_cap_to_TLP_cathode_distance_lower_bound_mm': distance(parts[rc_c]['1'], parts[u]['3'])})

    # Bind local circuit/library source in addition to the native board/XML.
    for rel in (RLY+'/RelayBoard.kicad_sym', RLY+'/3d/TLP2363_5pin_SO6.wrl',
                RLY+'/3d/TLP2363-provenance.json', 'tools/add_lower_input_rc_schematic.py'):
        track(root/rel)
    for rel in ('TLP2363-source-audit.json', 'TLP2363-validation.json'):
        a, b = track(before/rel), track(root/rel)
        if a.exists() and b.exists():
            require(sha(a) == sha(b), 'Historical report unchanged ' + rel)
    for path, initial in tracked.items():
        if not path.exists():
            require(False, 'Source exists ' + str(path))
        elif initial != sha(path):
            source_changed_during_audit.append(str(path))
    require(not source_changed_during_audit, 'All audited input sources stable during read-only run')
    return {'status': 'PASS' if not errors else 'FAIL', 'errors': errors, 'gates': gates, 'notes': notes,
            'project_root': str(root), 'before_root': str(before),
            'constraints': {'CPU_native_five_byte_exact': True, 'Lower_PRO_DRU_byte_exact': True,
                            'new_refs_exact': sorted(NEW, key=natural), 'movable_existing_refs_only': sorted(MOVABLE, key=natural),
                            'old_pin_changes_only': [{'ref': r, 'pin': p, 'before': a, 'after': b} for (r,p),(a,b) in sorted(allowed_old_pin_changes.items())],
                            'native_DRC_ERC_and_copper_connectivity_separate': True},
            'counts': {name: {k: d[k] for k in ('purchased', 'physical', 'excluded', 'BOM_groups')} for name,d in board_data.items()},
            'XML_PCB_pin_mismatches': pin_mismatches, 'XML_PCB_metadata_mismatches': metadata_mismatches,
            'schematic_XML_metadata_mismatches': schematic_metadata_mismatches,
            'library_pad_geometry_mismatches': library_mismatches, 'library_pad_checks': library_checks,
            'existing_moved_components': moved, 'old_pin_net_deltas': old_net_deltas,
            'authorized_silkscreen_deltas':authorized_silkscreen_deltas,
            'unrelated_footprint_deltas': unrelated_footprint_deltas, 'native_serialization_equivalences': serialization_equivalences,
            'channels': channels, 'source_changed_during_audit': source_changed_during_audit,
            'source_sha256': {str(path): sha(path) for path in sorted(tracked) if path.exists()},
            'source_only': True, 'CAD_files_not_written': True,
            'scope': 'Only source inventory, topology, metadata, library pads, BOMs and authorized local placement delta. PASS is not native DRC/ERC, electrical filled-copper connectivity, timing guarantee, enclosure thermal, prototype or EMC qualification. Power arithmetic is audited separately.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--before-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import wx
    application = wx.App(False)
    wx.Log.EnableLogging(False)
    import pcbnew
    root, before = args.project_root.resolve(), args.before_root.resolve()
    try:
        result = run(root, before, pcbnew)
    except Exception as exc:
        result = {'status': 'FAIL', 'errors': [type(exc).__name__+': '+str(exc)],
                  'project_root': str(root), 'before_root': str(before),
                  'CAD_files_not_written': True, 'source_only': True,
                  'scope': 'Audit could not complete; this is not a passed source check.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'errors': result['errors'], 'report': str(args.output.resolve())}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
