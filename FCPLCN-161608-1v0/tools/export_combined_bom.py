"""Export purchased parts for both boards from their current KiCad XML netlists."""
from pathlib import Path
from board_paths import board_file
import csv
import re
import xml.etree.ElementTree as ET
from bom_common import component_record, component_key

ROOT = Path(__file__).resolve().parents[1]


def natural(value):
    return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', value)]


def category(reference):
    return {'U': 'Микросхемы и модули', 'R': 'Резисторы',
            'C': 'Конденсаторы', 'D': 'Диоды и защита',
            'Q': 'Транзисторы', 'J': 'Разъёмы', 'K': 'Реле',
            'L': 'Индуктивности', 'S': 'Кнопки', 'B': 'Батарейные держатели',
            'F': 'Предохранители'}.get(reference[0], 'Прочее')


groups = {}
excluded = {}
for side in ('Lower', 'Upper'):
    excluded[side] = []
    path = board_file(ROOT, side, '.xml')
    for part in ET.parse(path).getroot().findall('components/comp'):
        ref = part.attrib['ref']
        if part.find("property[@name='exclude_from_bom']") is not None:
            excluded[side].append(ref)
            continue
        record = component_record(part)
        key = component_key(record)
        row = groups.setdefault(key, {
            **{key: value for key, value in record.items() if key not in ('value', 'footprint')},
            'category': category(ref), 'component': record['value'],
            'Lower': [], 'Upper': [], '_footprints': set()})
        row[side].append(ref)
        row['_footprints'].add(record['footprint'])
        row['datasheet'] = row['datasheet'] or record['datasheet']

rows = []
for row in groups.values():
    lower, upper = (sorted(row.pop(side), key=natural) for side in ('Lower', 'Upper'))
    row.update(lower_qty=len(lower), upper_qty=len(upper),
               total_qty=len(lower) + len(upper),
               lower_references=', '.join(lower), upper_references=', '.join(upper))
    row['cad_footprints'] = '; '.join(sorted(row.pop('_footprints')))
    rows.append(row)
rows.sort(key=lambda r: (r['category'], natural(r['component']), r['package'], r['mpn']))
columns = ['category', 'component', 'package', 'lower_qty', 'upper_qty', 'total_qty',
           'lower_references', 'upper_references', 'mpn', 'datasheet', 'source_url',
           'manufacturer', 'tolerance', 'supplier_part_number', 'bom_group',
           'power_rating', 'voltage', 'dielectric', 'resistor_type', 'height_max', 'cad_footprints']
with (ROOT / 'BOM-combined.csv').open('w', encoding='utf-8-sig', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
print({side: sum(r[f'{side.lower()}_qty'] for r in rows) for side in ('Lower', 'Upper')})
print('Excluded board-only parts:', excluded)
