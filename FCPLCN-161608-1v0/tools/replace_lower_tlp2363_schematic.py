"""Migrate the lower-board dry-contact receivers to sixteen TLP2363.

Edits only section 07 of the existing schematic and appends one library symbol.
Unrelated source expressions remain byte-for-byte intact. Re-running is a no-op.
PCB footprint replacement/routing is deliberately a separate operation.
"""
from pathlib import Path
import json
import re

from board_paths import board_dir, board_file, board_name
from passive_specifications import SPECS
from schematic import Schematic, Pin, rectangle, polyline, circle
from add_lower_fram_schematic import expression_end

ROOT = Path(__file__).resolve().parents[1]
DATASHEET = "https://toshiba.semicon-storage.com/info/TLP2363_datasheet_en_20251218.pdf?did=67887&prodName=TLP2363"
FOOTPRINT = "RelayBoard:TLP2363_5pin_SO6"
WETTING_DATASHEET = 'https://www.vishay.com/docs/20115/crcwhp.pdf'
WETTING_FIELDS = {'MPN': 'CRCW08051K50FKTAHP', 'Manufacturer': 'Vishay',
                  'BOMGroup': 'R-0805-1.5k-1pct-500mW-Vishay-HP', 'BOMPackage': '0805',
                  'Tolerance': '1%', 'PowerRating': '0.5 W'}


def top_nodes(text):
    pos = re.match(r'\(\S+', text).end()
    while pos < len(text):
        if text[pos] == '(':
            end = expression_end(text, pos)
            yield pos, end, text[pos:end]
            pos = end
        elif text[pos] == ')':
            return
        else:
            pos += 1


def properties(node):
    return {json.loads('"' + key + '"'): json.loads('"' + value + '"')
            for key, value in re.findall(r'\(property "((?:\\.|[^"\\])*)" "((?:\\.|[^"\\])*)"', node)}


def reference(node):
    return properties(node).get('Reference') if node.startswith('(symbol (lib_id') else None


def source_uuid(node):
    return re.search(r'\(uuid "([^"]+)"\)', node).group(1)


def retain_identifiers(node, source, pins=True):
    """Retain instance UUID and, for unchanged parts, all of their pin UUIDs."""
    node = re.sub(r'\(uuid "[^"]+"\)', '(uuid "' + source_uuid(source) + '")', node, count=1)
    if pins:
        old_pins = dict(re.findall(r'\(pin "([^"]+)" \(uuid "([^"]+)"\)', source))
        node = re.sub(r'\(pin "([^"]+)" \(uuid "[^"]+"\)',
                      lambda m: '(pin "' + m[1] + '" (uuid "' + old_pins[m[1]] + '")', node)
    return node


def approved_wetting_values(text):
    """Update electrical rating/ordering data without changing instance identity."""
    replacements = []
    for start, end, node in top_nodes(text):
        ref = reference(node)
        if ref not in {f'R{i}' for i in range(101, 117)}:
            continue
        for key, value in {'Value': '1.5k', 'Datasheet': WETTING_DATASHEET, **WETTING_FIELDS}.items():
            pattern = r'(\(property "' + re.escape(key) + r'" )"(?:\\.|[^"\\])*"'
            if re.search(pattern, node):
                node = re.sub(pattern, lambda m: m[1] + json.dumps(value), node)
            else:
                at = re.search(r'\(at (-?[.\d]+) (-?[.\d]+) ', node)
                prop = f'(property "{key}" {json.dumps(value)} (at {at[1]} {at[2]} 0) (effects (font (size 1 1)) (hide yes)))'
                node = node[:-1] + '\n' + prop + ')'
        replacements.append((start, end, node))
    assert len(replacements) == 16
    for start, end, node in reversed(replacements):
        text = text[:start] + node + text[end:]
    text = text.replace('R101–R116: 1,8 кОм, не менее 0,125 Вт. Ток замкнутого входа около 6 мА.',
                        'R101–R116: 1,5 кОм ±1%, 0,5 Вт (Vishay CRCW0805-HP). Ток входа около 7 мА при 12 В.')
    return text


def tlp_drawing():
    """Show the emitter, optical path and inverting photo-IC explicitly."""
    return [rectangle((-7.62, -7.62), (7.62, 7.62)),
            polyline((-7.62, 2.54), (-5.08, 2.54), (-5.08, 1.27)),
            polyline((-6.35, 1.27), (-3.81, 1.27), (-5.08, -1.27), (-6.35, 1.27)),
            polyline((-6.35, -1.27), (-3.81, -1.27)),
            polyline((-5.08, -1.27), (-5.08, -2.54), (-7.62, -2.54)),
            polyline((-3.81, .635), (-1.27, 1.905), (-2.286, 1.905)),
            polyline((-1.27, 1.905), (-1.905, 1.016)),
            polyline((-3.81, -.635), (-1.27, .635), (-2.286, .635)),
            polyline((-1.27, .635), (-1.905, -.254)),
            rectangle((0, -3.81), (3.81, 3.81), fill='none', width=.127),
            polyline((0, 7.62), (2.54, 7.62), (2.54, 3.81)),
            polyline((0, -7.62), (2.54, -7.62), (2.54, -3.81)),
            circle((4.445, 0), .635, width=.127),
            polyline((5.08, 0), (7.62, 0))]


def horizontal_series_symbols(text):
    # A horizontal two-pin resistor keeps its annotations horizontal in KiCad.
    replacements = []
    for start, end, node in top_nodes(text):
        if reference(node) in {f'R{i}' for i in range(141, 157)}:
            node = node.replace('(lib_id "RelayBoard:DI16_Resistor")', '(lib_id "RelayBoard:DI16_Wetting_Resistor")')
            node = re.sub(r'^(\(symbol \(lib_id "[^"]+"\) \(at [-.\d]+ [-.\d]+) 90\)', r'\1 0)', node)
            replacements.append((start, end, node))
    for start, end, node in reversed(replacements):
        text = text[:start] + node + text[end:]
    return text


def refresh_tlp_drawing(text):
    start = text.index('(symbol "TLP2363_0_1"')
    end = expression_end(text, start)
    return text[:start] + '(symbol "TLP2363_0_1" ' + '\n'.join(tlp_drawing()) + ')' + text[end:]


def main():
    path = board_file(ROOT, 'Lower', '.kicad_sch')
    libpath = board_dir(ROOT, 'Lower') / 'RelayBoard.kicad_sym'
    original = path.read_text()
    original_library = libpath.read_text()
    nodes = list(top_nodes(original))
    byref = {reference(n): n for _, _, n in nodes if reference(n)}
    if 'R161' in byref or 'C141' in byref:
        assert all(f'R{i}' in byref for i in range(161, 177))
        assert all(f'C{i}' in byref for i in range(141, 157))
        print('Later input RC migration is present; earlier TLP2363 migration left unchanged.')
        return
    if properties(byref['U21']).get('Value') == 'TLP2363':
        assert all(properties(byref[f'U{i}']).get('Value') == 'TLP2363' for i in range(21, 37))
        result = horizontal_series_symbols(refresh_tlp_drawing(approved_wetting_values(original)))
        library_result = refresh_tlp_drawing(original_library)
        if library_result != original_library:
            libpath.write_text(library_result)
        if result != original:
            path.write_text(result)
        print('TLP2363 schematic migration already present; approved wetting values verified.')
        return
    assert all(properties(byref[f'U{i}']).get('Value') == 'LTV-847S' for i in range(21, 25))
    replacing = {f'U{i}' for i in range(21, 25)}
    replacing |= {f'{prefix}{i}' for prefix, first in (('R', 101), ('R', 121), ('C', 101), ('D', 101), ('D', 121)) for i in range(first, first + 16)}
    assert len(replacing) == 84 and replacing <= byref.keys()
    assert not ({f'U{i}' for i in range(25, 37)} & byref.keys())
    assert not ({f'C{i}' for i in range(121, 137)} & byref.keys())
    assert not ({f'R{i}' for i in range(141, 157)} & byref.keys())

    schema = Schematic(board_name('Lower'), namespace='RelayBoard',
                       uuid_seed='FCPLCN/lower-TLP2363-v1')
    schema.root = '"' + source_uuid(original) + '"'
    schema.define('TLP2363', 'U', [
        Pin('1', 'A', -10.16, 2.54, 0, 'passive'),
        Pin('3', 'K', -10.16, -2.54, 0, 'passive'),
        Pin('4', 'GND', 0, -12.7, 90, 'power_in', length=5.08),
        Pin('5', 'VO', 12.7, 0, 180, 'open_collector', length=5.08),
        Pin('6', 'VCC', 0, 12.7, 270, 'power_in', length=5.08),
    ], tlp_drawing(),
        footprint=FOOTPRINT, description='Toshiba TLP2363 inverting photo-IC optocoupler; open-collector output, 2.7-5.5 V, SO6 (5 leads), package 11-4L1S',
        datasheet=DATASHEET)
    # Reuse the following embedded definitions verbatim (only pin geometry is
    # needed to place instances and attach wires).
    for name, ref, pins in [
        ('DI16_Wetting_Resistor', 'R', [Pin('1', '~', -3.81, 0), Pin('2', '~', 3.81, 0, 180)]),
        ('DI16_Reverse_Diode', 'D', [Pin('1', 'K', 0, 2.54, 270), Pin('2', 'A', 0, -2.54, 90)]),
        ('DI16_ESD_Diode', 'D', [Pin('1', 'K', 0, 2.54, 270), Pin('2', 'A', 0, -2.54, 90)]),
        ('DI16_Resistor', 'R', [Pin('1', '~', 0, 3.81, 270), Pin('2', '~', 0, -3.81, 90)]),
        ('DI16_Capacitor', 'C', [Pin('1', '~', 0, 2.54, 270), Pin('2', '~', 0, -2.54, 90)]),
    ]:
        schema.define(name, ref, pins, [])

    def place_existing(ref, at, ref_at, value_at, **kwargs):
        p = properties(byref[ref])
        definition = p.pop('Value')
        name = re.search(r'\(lib_id "RelayBoard:([^"]+)"', byref[ref]).group(1)
        p.pop('Reference')
        fp, ds, desc = p.pop('Footprint'), p.pop('Datasheet'), p.pop('Description')
        schema.place(name, ref, at, value=definition, ref_at=ref_at, value_at=value_at,
                     footprint=fp, datasheet=ds, fields={**p, 'Description': desc}, **kwargs)
        # Description was supplied as a field so replace its initial empty
        # property, then remove the duplicate property produced by the helper.
        node = schema.elements[-1]
        props = list(re.finditer(r'\(property "Description"', node))
        assert len(props) == 2
        first = props[0].start(); first_end = expression_end(node, first)
        second = props[1].start(); second_end = expression_end(node, second)
        desc_expr = node[second:second_end]
        node = node[:second] + node[second_end:]
        node = node[:first] + desc_expr + node[first_end:]
        schema.elements[-1] = retain_identifiers(node, byref[ref])
        return schema.instances[ref]

    raw_wire = schema.wire
    schema.wire = lambda *points: raw_wire(*(tuple(round(v, 4) for v in p) for p in points))

    for ch in range(1, 17):
        col, row = divmod(ch - 1, 4)
        dx = round(105.41 * col, 4)
        x, y = round(205.74 + dx, 4), round(238.76 + 36.83 * row, 4)
        opto_ref = f'U{20+ch}'
        op = schema.place('TLP2363', opto_ref, (x, y), value='TLP2363',
                          ref_at=(x-5.08, y-10.16), value_at=(x+12.7, y-10.16),
                          fields={'MPN': 'TLP2363(TPL,E', 'Manufacturer': 'Toshiba',
                                  'BOMPackage': 'SO6-5pin', 'BOMGroup': 'IC-OPTO-TLP2363-SO6-5pin',
                                  'PackageDrawing': '11-4L1S'})
        if opto_ref in byref:
            schema.elements[-1] = retain_identifiers(schema.elements[-1], byref[opto_ref], pins=False)
        wet = place_existing(f'R{100+ch}', (171.45+dx, y-2.54),
                             (171.45+dx, y-5.969), (171.45+dx, y+0.127))
        rev = place_existing(f'D{100+ch}', (186.69+dx, y),
                             (186.69+dx, y-10.16), (186.69+dx, y-7.62))
        tvs = place_existing(f'D{120+ch}', (177.8+dx, y+7.62),
                             (187.96+dx, y+6.35), (187.96+dx, y+8.89))
        pu = place_existing(f'R{120+ch}', (228.6+dx, y-7.62),
                            (235.0+dx, y-9.144), (235.0+dx, y-6.858))
        fc = place_existing(f'C{100+ch}', (251.46+dx, y+7.62),
                            (258.445+dx, y+6.35), (258.445+dx, y+8.89))
        rs = schema.place('DI16_Wetting_Resistor', f'R{140+ch}', (240.03+dx, y),
                          value=SPECS['R470']['value'], ref_at=(240.03+dx, y-3.81),
                          value_at=(240.03+dx, y+3.81),
                          footprint='RelayBoard:R_0805_2012Metric', fields=SPECS['R470']['fields'])
        bc = schema.place('DI16_Capacitor', f'C{120+ch}', (224.79+dx, y+8.89),
                          value=SPECS['C100N']['value'], ref_at=(232.41+dx, y+8.128),
                          value_at=(232.41+dx, y+10.414),
                          footprint='RelayBoard:C_0805_2012Metric', fields=SPECS['C100N']['fields'])
        # Field input: +12V -> resistor -> LED -> external dry contact to GND.
        schema.wire((154.94+dx, y-2.54), wet['1'])
        schema.label('+12V_SYS', (154.94+dx, y-2.54), size=1.0)
        schema.wire(wet['2'], rev['1'], op['1'])
        schema.junction(rev['1'])
        schema.wire((165.1+dx, y+2.54), (177.8+dx, y+2.54), rev['2'], op['3'])
        schema.label(f'DI{ch}', (165.1+dx, y+2.54), size=1.0)
        schema.wire((177.8+dx, y+2.54), tvs['1'])
        schema.junction((177.8+dx, y+2.54)); schema.junction(rev['2'])
        schema.wire(tvs['2'], (177.8+dx, y+12.7), (187.96+dx, y+12.7))
        schema.label('GND', (187.96+dx, y+12.7), angle=180, size=1.0)
        # TLP local decoupling, VCC pin6 and GND pin4.
        schema.wire(op['6'], (x, y-15.24)); schema.label('+3V3', (x, y-15.24), size=1.0)
        schema.wire(op['4'], (x, y+15.24)); schema.label('GND', (x, y+15.24), size=1.0)
        schema.wire(bc['1'], (224.79+dx, y+3.81)); schema.label('+3V3', (224.79+dx, y+3.81), size=1.0)
        schema.wire(bc['2'], (224.79+dx, y+13.97)); schema.label('GND', (224.79+dx, y+13.97), size=1.0)
        # Keep pull-up on the RAW side of the added 470-ohm resistor. It limits
        # discharge of the existing 100-nF MCP23017 input filter capacitor.
        schema.wire(pu['1'], (228.6+dx, y-13.97)); schema.label('+3V3', (228.6+dx, y-13.97), size=1.0)
        schema.wire(op['5'], (228.6+dx, y), rs['1'])
        schema.wire(pu['2'], (228.6+dx, y)); schema.junction((228.6+dx, y))
        schema.label(f'OPTO{ch}_RAW', op['5'], size=.9)
        schema.wire(rs['2'], (251.46+dx, y), (260.35+dx, y))
        schema.wire((251.46+dx, y), fc['1']); schema.junction((251.46+dx, y))
        schema.label(f'IN{ch}', (260.35+dx, y), angle=180, size=1.0)
        schema.wire(fc['2'], (251.46+dx, y+13.97)); schema.label('GND', (251.46+dx, y+13.97), size=1.0)

    # Suppress oversized repeated diode values only if the section remains
    # readable at print scale: use 1.0-mm instance lettering throughout inputs.
    schema.elements = [n.replace('(size 1.27 1.27)', '(size 1 1)') for n in schema.elements]
    schema.text('TLP2363: питание 3,3 В; C121–C136 100 нФ у выводов 6–4. R141–R156 470 Ом ограничивают ток C101–C116.',
                (156.21, 375.92), size=1.17)
    # Identify only existing section-07 connectivity, never geometry elsewhere.
    removal = []
    preserved = []
    for start, end, node in nodes:
        ref = reference(node)
        points = [tuple(map(float, p)) for p in re.findall(r'\((?:xy|at) (-?[.\d]+) (-?[.\d]+)', node)]
        is_connectivity = node.startswith(('(wire ', '(junction ', '(label '))
        inside = points and all(150 <= a <= 585 and 220 <= b <= 363 for a, b in points)
        if ref in replacing or (is_connectivity and inside):
            removal.append((start, end))
        else:
            preserved.append(node)
    assert len([r for r in replacing if r in byref]) == 84
    result = original
    for start, end in reversed(removal):
        result = result[:start] + result[end:]
    lib_start = result.index('(lib_symbols')
    lib_end = expression_end(result, lib_start)
    definition = schema.definitions['TLP2363']
    result = result[:lib_end-1] + '\n' + definition.sexpr('RelayBoard') + '\n' + result[lib_end-1:]
    elements = [n.replace('(stroke (width 0) (type default))', '(stroke (width 0.254) (type solid))') for n in schema.elements]
    result = result.rstrip()[:-1] + '\n' + '\n'.join(elements) + '\n)\n'
    result_nodes = [n for _, _, n in top_nodes(result)]
    for node in preserved:
        if node.startswith('(lib_symbols'):
            continue
        assert node in result_nodes, 'Unrelated schematic expression changed'
    newrefs = [reference(n) for n in result_nodes if reference(n)]
    assert len(newrefs) == len(set(newrefs))
    assert len(newrefs) == len(byref) + 44
    assert '(symbol "TLP2363"' not in original_library
    lib = original_library.rstrip()[:-1] + '\n' + definition.sexpr() + '\n)\n'
    path.write_text(approved_wetting_values(result))
    libpath.write_text(lib)
    print(f'Replaced four LTV-847S by sixteen TLP2363; added 16 bypass capacitors and 16 output resistors. {len(byref)} -> {len(newrefs)} instances.')
    print(f'Preserved {len(preserved)-1} unrelated expressions, and all existing input-passive UUIDs.')


if __name__ == '__main__':
    main()
