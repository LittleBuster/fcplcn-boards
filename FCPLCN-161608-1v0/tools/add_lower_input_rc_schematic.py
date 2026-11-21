"""Add a damped RC filter ahead of each lower-board TLP2363 receiver.

The external DI/TVS node remains before a new 220-ohm resistor. The TLP LED
cathode and its reverse diode return through DIFn, with 1 uF to GND. Existing
instance/pin UUIDs and all source outside these sixteen circuits are retained.
Re-running the completed migration is a no-op.
"""
from pathlib import Path
import json
import re

from board_paths import board_dir, board_file, board_name
from passive_specifications import SPECS
from schematic import Schematic, Pin, mm, rectangle
from add_lower_fram_schematic import expression_end
from replace_lower_tlp2363_schematic import top_nodes, properties, reference, source_uuid

ROOT = Path(__file__).resolve().parents[1]
RESISTOR_DATASHEET = 'https://www.vishay.com/docs/20115/crcwhp.pdf'
CAP_DATASHEET = 'https://product.tdk.com/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c2012x7r1h105k125ab.pdf'
CAP_SOURCE = 'https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C2012X7R1H105K125AB'
R_INPUT = {'Value': '1.2k', 'Datasheet': RESISTOR_DATASHEET,
           'MPN': 'CRCW08051K20FKTAHP', 'Manufacturer': 'Vishay',
           'BOMGroup': 'R-0805-1.2k-1pct-500mW-Vishay-HP', 'BOMPackage': '0805',
           'Tolerance': '1%', 'PowerRating': '0.5 W'}
R_SERIES_FIELDS = {'MPN': 'CRCW0805220RFKTAHP', 'Manufacturer': 'Vishay',
                   'BOMGroup': 'R-0805-220R-1pct-500mW-Vishay-HP', 'BOMPackage': '0805',
                   'Tolerance': '1%', 'PowerRating': '0.5 W'}
C_FILTER_FIELDS = {'MPN': 'C2012X7R1H105K125AB', 'Manufacturer': 'TDK',
                   'BOMGroup': 'C-0805-1uF-50V-X7R-10pct-TDK',
                   'BOMPackage': '0805', 'Tolerance': '10%', 'Voltage': '50 V',
                   'Dielectric': 'X7R', 'Height_Max': '1.45 mm', 'SourceURL': CAP_SOURCE}


def point(x, y):
    return round(x, 4), round(y, 4)


def update_properties(node, fields):
    at = re.search(r'\(at (-?[.\d]+) (-?[.\d]+) ', node)
    for key, value in fields.items():
        pattern = r'(\(property "' + re.escape(key) + r'" )"(?:\\.|[^"\\])*"'
        if re.search(pattern, node):
            node = re.sub(pattern, lambda m: m[1] + json.dumps(value), node)
        else:
            new = f'(property "{key}" {json.dumps(value)} (at {at[1]} {at[2]} 0) (effects (font (size 1 1)) (hide yes)))'
            node = node[:-1] + '\n' + new + ')'
    return node


def move_component(node, x, y):
    return re.sub(r'^(\(symbol \(lib_id "[^"]+"\) )\(at [-.\d]+ [-.\d]+ ([-.\d]+)\)',
                  lambda m: m[1] + f'(at {mm(x)} {mm(y)} {m[2]})', node)


def move_property(node, name, dx):
    start = node.index('(property "' + name + '"')
    end = expression_end(node, start)
    prop = node[start:end]
    prop = re.sub(r'\(at ([-.\d]+) ([-.\d]+) ([-.\d]+)\)',
                  lambda m: f'(at {mm(float(m[1])+dx)} {m[2]} {m[3]})', prop)
    return node[:start] + prop + node[end:]


def add_led_shunts(source, local_library):
    """Add the sixteen LED discharge shunts to either supported RC source."""
    nodes = list(top_nodes(source))
    refs = {reference(n):n for _,_,n in nodes if reference(n)}
    if 'R181' in refs:
        assert all(f'R{i}' in refs and properties(refs[f'R{i}'])['Value']=='4.7k' for i in range(181,197))
        return source, local_library
    assert not {f'R{i}' for i in range(181,197)} & refs.keys()
    schema = Schematic(board_name('Lower'), namespace='RelayBoard', uuid_seed='FCPLCN/lower-input-LED-shunts-v1')
    schema.root = '"'+source_uuid(source)+'"'
    schema.define('DI16_LED_Shunt_Resistor', 'R',
                  [Pin('1','~',0,2.54,270,length=1.27), Pin('2','~',0,-2.54,90,length=1.27)],
                  [rectangle((-.762,-1.27),(.762,1.27),fill='none',width=.254)],
                  names=False, numbers=False, footprint='RelayBoard:R_0805_2012Metric',
                  description='Resistor shunting the TLP LED to discharge its input filter; IEC compact schematic symbol')
    raw_wire=schema.wire
    schema.wire=lambda *points:raw_wire(*(tuple(round(v,4) for v in p) for p in points))
    splits={}; series_refs={}
    for ch in range(1,17):
        col,row=divmod(ch-1,4);dx=round(105.41*col,4);y=round(238.76+36.83*row,4)
        sh=schema.place('DI16_LED_Shunt_Resistor',f'R{180+ch}',point(190.5+dx,y),
                        value=SPECS['R4K7']['value'],ref_at=point(190.5+dx,y-5.588),
                        value_at=point(190.5+dx,y-3.81),fields=SPECS['R4K7']['fields'])
        left,right,mid=point(175.26+dx,y-2.54),point(193.04+dx,y-2.54),sh['1']
        splits[frozenset((left,right))]=(left,mid)
        schema.wire(mid,right);schema.junction(mid);schema.junction(sh['2'])
        series_refs[f'R{160+ch}']=-3.81
    replacements=[];split_count=0
    for start,end,node in nodes:
        updated=node
        if reference(node) in series_refs:
            updated=move_property(node,'Reference',series_refs[reference(node)])
        elif node.startswith('(wire '):
            pts=[point(*map(float,p)) for p in re.findall(r'\(xy ([-.\d]+) ([-.\d]+)',node)]
            if frozenset(pts) in splits:
                left,mid=splits[frozenset(pts)]
                start_pts=node.index('(pts ');end_pts=expression_end(node,start_pts)
                updated=node[:start_pts]+f'(pts (xy {mm(left[0])} {mm(left[1])}) (xy {mm(mid[0])} {mm(mid[1])}))'+node[end_pts:]
                split_count+=1
        elif node.startswith('(text '):
            updated=updated.replace('До TLP: C141–C156 1 мкФ / 50 В X7R. Время отклика зависит от порога TLP, ёмкости под напряжением и проводки; программный антидребезг сохраняется.',
                                    'C141–C156: 1 мкФ / 50 В X7R; R181–R196: 4,7 кОм параллельно LED. Отклик зависит от порогов TLP, ёмкости под напряжением и проводки; программный антидребезг сохраняется.')
            updated=updated.replace('ток около 7,4 мА при 12 В.', 'ток входа около 7,4 мА при 12 В.')
        if updated!=node:replacements.append((start,end,updated))
    assert split_count==16,split_count
    for start,end,updated in reversed(replacements):source=source[:start]+updated+source[end:]
    definition=schema.definitions['DI16_LED_Shunt_Resistor']
    lib_start=source.index('(lib_symbols');lib_end=expression_end(source,lib_start)
    source=source[:lib_end-1]+'\n'+definition.sexpr('RelayBoard')+'\n'+source[lib_end-1:]
    elements=[n.replace('(stroke (width 0) (type default))','(stroke (width 0.254) (type solid))').replace('(size 1.27 1.27)','(size 1 1)') for n in schema.elements]
    source=source.rstrip()[:-1]+'\n'+'\n'.join(elements)+'\n)\n'
    assert '(symbol "DI16_LED_Shunt_Resistor"' not in local_library
    local_library=local_library.rstrip()[:-1]+'\n'+definition.sexpr()+'\n)\n'
    return source,local_library


def main():
    path = board_file(ROOT, 'Lower', '.kicad_sch')
    source = path.read_text()
    libpath = board_dir(ROOT,'Lower')/'RelayBoard.kicad_sym'
    local_library = libpath.read_text()
    nodes = list(top_nodes(source))
    byref = {reference(n): n for _, _, n in nodes if reference(n)}
    if 'R161' in byref:
        assert all(f'R{i}' in byref for i in range(161, 177))
        assert all(f'C{i}' in byref for i in range(141, 157))
        assert all(properties(byref[f'R{i}'])['Value'] == '1.2k' for i in range(101, 117))
        assert all(properties(byref[f'R{i}'])['MPN'] == R_SERIES_FIELDS['MPN'] for i in range(161, 177))
        assert all(properties(byref[f'C{i}'])['MPN'] == C_FILTER_FIELDS['MPN'] for i in range(141, 157))
        result = source
        for start, end, node in reversed(nodes):
            if reference(node) in {f'C{i}' for i in range(141, 157)}:
                updated = update_properties(node, {'Datasheet': CAP_DATASHEET, **C_FILTER_FIELDS})
                result = result[:start] + updated + result[end:]
        result,library_result=add_led_shunts(result,local_library)
        if result != source:
            path.write_text(result)
        if library_result != local_library:
            libpath.write_text(library_result)
        print('Sixteen before-TLP RC filters and LED shunts present; exact approved metadata verified.')
        return
    assert all(properties(byref[f'U{i}'])['Value'] == 'TLP2363' for i in range(21, 37))
    assert all(properties(byref[f'R{i}'])['Value'] == '1.5k' for i in range(101, 117))
    assert not {f'C{i}' for i in range(141, 157)} & byref.keys()
    assert not {f'R{i}' for i in range(161, 177)} & byref.keys()

    schema = Schematic(board_name('Lower'), namespace='RelayBoard',
                       uuid_seed='FCPLCN/lower-input-RC-v1')
    schema.root = '"' + source_uuid(source) + '"'
    # Existing embedded/local symbol definitions are reused verbatim.
    schema.define('DI16_Wetting_Resistor', 'R',
                  [Pin('1', '~', -3.81, 0), Pin('2', '~', 3.81, 0, 180)], [])
    schema.define('DI16_Capacitor', 'C',
                  [Pin('1', '~', 0, 2.54, 270), Pin('2', '~', 0, -2.54, 90)], [])
    raw_wire = schema.wire
    schema.wire = lambda *points: raw_wire(*(tuple(round(v, 4) for v in p) for p in points))

    diode_at = {}
    coordinates = {}
    removed_wires = set()
    for channel in range(1, 17):
        col, row = divmod(channel - 1, 4)
        dx = round(105.41 * col, 4)
        y = round(238.76 + 36.83 * row, 4)
        old_k = point(186.69+dx, y-2.54)
        old_a = point(186.69+dx, y+2.54)
        new_k = point(193.04+dx, y-2.54)
        new_a = point(193.04+dx, y+2.54)
        diode_at[f'D{100+channel}'] = point(193.04+dx, y)
        coordinates[old_k] = new_k
        coordinates[old_a] = new_a
        terminal_node = point(177.8+dx, y+2.54)
        removed_wires.add(frozenset((terminal_node, old_a)))
        # Pin1 is the filtered LED return (DIFn); pin2 is the exposed DIn.
        series = schema.place('DI16_Wetting_Resistor', f'R{160+channel}',
                              point(186.69+dx, y+2.54), angle=180, value='220R',
                              ref_at=point(186.69+dx, y-.635),
                              value_at=point(186.69+dx, y+6.35),
                              footprint='RelayBoard:R_0805_2012Metric',
                              datasheet=RESISTOR_DATASHEET, fields=R_SERIES_FIELDS)
        cap = schema.place('DI16_Capacitor', f'C{140+channel}',
                           point(193.04+dx, y+11.43), value='1uF',
                           ref_at=point(198.12+dx, y+10.414),
                           value_at=point(198.12+dx, y+12.7),
                           footprint='RelayBoard:C_0805_2012Metric',
                           datasheet=CAP_DATASHEET, fields=C_FILTER_FIELDS)
        schema.wire(terminal_node, series['2'])
        schema.wire(series['1'], new_a)
        schema.wire(new_a, cap['1'])
        schema.label(f'DIF{channel}', cap['1'], angle=180, size=.9)
        schema.wire(cap['2'], point(193.04+dx, y+17.78))
        schema.label('GND', point(193.04+dx, y+17.78), size=1)

    replaced = []
    removed_count = 0
    retained = []
    changed_refs = set(diode_at) | {f'R{i}' for i in range(101, 117)} | {f'D{i}' for i in range(121, 137)}
    note_count = 0
    for start, end, node in nodes:
        result = node
        ref = reference(node)
        if ref in diode_at:
            result = move_component(result, *diode_at[ref])
        elif ref in {f'R{i}' for i in range(101, 117)}:
            result = update_properties(result, R_INPUT)
        elif ref in {f'D{i}' for i in range(121, 137)}:
            result = move_property(result, 'Reference', -22.86)
            result = move_property(result, 'Value', -22.86)
        elif node.startswith(('(wire ', '(junction ')):
            pts = [point(*map(float, p)) for p in re.findall(r'\((?:xy|at) ([-.\d]+) ([-.\d]+)', node)]
            if node.startswith('(wire ') and frozenset(pts) in removed_wires:
                result = ''
                removed_count += 1
            else:
                result = re.sub(r'\((xy|at) ([-.\d]+) ([-.\d]+)',
                                lambda m: '('+m[1]+' '+(' '.join(map(mm, coordinates[point(float(m[2]),float(m[3]))]))
                                  if point(float(m[2]),float(m[3])) in coordinates else m[2]+' '+m[3]), result)
        elif node.startswith('(text '):
            if 'Кнопка или геркон подключается между DI и GND.' in node:
                result = result.replace('(at 156.21 365.76 0)', '(at 156.21 374.65 0)')
                note_count += 1
            elif 'R101–R116: 1,5 кОм' in node:
                result = result.replace('R101–R116: 1,5 кОм ±1%, 0,5 Вт (Vishay CRCW0805-HP). Ток входа около 7 мА при 12 В.',
                                        'R101–R116: 1,2 кОм; R161–R176: 220 Ом. Все ±1%, 0,5 Вт (CRCW0805-HP); ток около 7,4 мА при 12 В.')
                result = result.replace('(at 156.21 370.84 0)', '(at 156.21 379.73 0)')
                note_count += 1
            elif 'TLP2363: питание 3,3 В; C121–C136' in node:
                result = result.replace('(at 156.21 375.92 0)', '(at 156.21 384.81 0)')
                note_count += 1
        if result != node:
            replaced.append((start, end, result))
        else:
            retained.append(node)
    assert removed_count == 16 and note_count == 3, (removed_count, note_count)
    schema.text('До TLP: C141–C156 1 мкФ / 50 В X7R. Время отклика зависит от порога TLP, ёмкости под напряжением и проводки; программный антидребезг сохраняется.',
                (156.21, 389.89), size=1.17)
    result = source
    for start, end, replacement in reversed(replaced):
        result = result[:start] + replacement + result[end:]
    # Explicit widths are necessary for the lower project's legacy drawing defaults.
    elements = [n.replace('(stroke (width 0) (type default))', '(stroke (width 0.254) (type solid))')
                  .replace('(size 1.27 1.27)', '(size 1 1)') for n in schema.elements]
    result = result.rstrip()[:-1] + '\n' + '\n'.join(elements) + '\n)\n'
    result_nodes = [n for _, _, n in top_nodes(result)]
    newrefs = [reference(n) for n in result_nodes if reference(n)]
    assert len(newrefs) == len(set(newrefs)) == len(byref) + 32
    for node in retained:
        assert node in result_nodes, 'Unrelated source expression changed'
    # Every original symbol root/pin UUID remains present despite local moves.
    afterrefs = {reference(n): n for n in result_nodes if reference(n)}
    for ref, node in byref.items():
        assert source_uuid(node) == source_uuid(afterrefs[ref]), ref
        old_pins = re.findall(r'\(pin "([^"]+)" \(uuid "([^"]+)"\)', node)
        new_pins = re.findall(r'\(pin "([^"]+)" \(uuid "([^"]+)"\)', afterrefs[ref])
        assert old_pins == new_pins, ref
    result,library_result=add_led_shunts(result,local_library)
    assert len([reference(n) for _,_,n in top_nodes(result) if reference(n)])==len(byref)+48
    path.write_text(result)
    libpath.write_text(library_result)
    print(f'Added16×220R/1uF before-TLP input filters and16 LED shunts; {len(byref)} -> {len(byref)+48} schematic instances.')
    print(f'Preserved all original symbol/pin UUIDs and {len(retained)} unrelated expressions.')


if __name__ == '__main__':
    main()
