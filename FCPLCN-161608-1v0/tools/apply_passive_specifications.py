"""Apply the approved reference whitelist without rewriting CAD geometry.

Only Value/Datasheet/custom property values are replaced. New hidden fields are
inserted next to existing properties; every other byte of the source is retained.
"""
from dataclasses import dataclass
from pathlib import Path
from board_paths import board_file
import hashlib
import json
import re
import uuid

from passive_specifications import component_spec, approved_references

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+')


@dataclass
class Atom:
    text: str
    start: int
    end: int

    @property
    def value(self):
        return json.loads(self.text) if self.text.startswith('"') else self.text


@dataclass
class Node:
    parts: list
    start: int
    end: int

    @property
    def tag(self):
        return self.parts[0].value


def parse(source):
    tokens = list(TOKEN.finditer(source))
    index = 0

    def item():
        nonlocal index
        token = tokens[index]
        index += 1
        if token.group() != '(':
            return Atom(token.group(), token.start(), token.end())
        parts = []
        while tokens[index].group() != ')':
            parts.append(item())
        end = tokens[index].end()
        index += 1
        return Node(parts, token.start(), end)

    root = item()
    if index != len(tokens):
        raise ValueError('Trailing S-expression data')
    return root


def nodes(node, tag):
    return [part for part in node.parts if isinstance(part, Node) and part.tag == tag]


def properties(node):
    return {part.parts[1].value: part for part in nodes(node, 'property')}


def patch_file(path, board):
    source = path.read_text()
    tree = parse(source)
    pcb = path.suffix == '.kicad_pcb'
    edits = []
    found = set()
    changes = []
    for part in nodes(tree, 'footprint' if pcb else 'symbol'):
        props = properties(part)
        if 'Reference' not in props:
            continue
        reference = props['Reference'].parts[2].value
        spec = component_spec(board, reference)
        if spec is None:
            continue
        found.add(reference)
        footprint = part.parts[1].value if pcb else props['Footprint'].parts[2].value
        if spec['fields']['BOMPackage'] not in footprint:
            raise ValueError(f'{board}.{reference}: unexpected footprint {footprint}')
        values = {'Value': spec['value'], **spec['fields']}
        if 'datasheet' in spec:
            values['Datasheet'] = spec['datasheet']
        additions = []
        modified = []
        for name, value in values.items():
            if name in props:
                old = props[name].parts[2]
                if old.value != value:
                    edits.append((old.start, old.end, json.dumps(value, ensure_ascii=False)))
                    modified.append(name)
            else:
                quoted_name, quoted_value = (json.dumps(x, ensure_ascii=False) for x in (name, value))
                if pcb:
                    layer = nodes(part, 'layer')[0].parts[1].value
                    fab = 'B.Fab' if layer.startswith('B.') else 'F.Fab'
                    field_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f'fcplcn/passive/{board}/{reference}/{name}'))
                    text = f'(property {quoted_name} {quoted_value} (at 0 0 0) (layer "{fab}") (hide yes) (uuid "{field_uuid}") (effects (font (size 1 1) (thickness 0.15))))'
                else:
                    at = nodes(part, 'at')[0]
                    position = ' '.join(atom.text for atom in at.parts[1:])
                    text = f'(property {quoted_name} {quoted_value} (at {position}) (effects (font (size 1 1)) (hide yes)))'
                additions.append(text)
                modified.append(name)
        if additions:
            insert_at = max(prop.end for prop in props.values())
            edits.append((insert_at, insert_at, '\n' + '\n'.join(additions)))
        if modified:
            changes.append({'reference': reference, 'fields': modified})
    if found != approved_references(board):
        raise ValueError(f'{path}: approved references differ: {sorted(found ^ approved_references(board))}')
    updated = source
    for start, end, value in sorted(edits, reverse=True):
        updated = updated[:start] + value + updated[end:]
    if updated != source:
        path.write_text(updated)
    return {'path': str(path.relative_to(ROOT)), 'parts_changed': len(changes), 'changes': changes,
            'before_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'after_sha256': hashlib.sha256(updated.encode()).hexdigest()}


if __name__ == '__main__':
    report = {'scope': 'Approved passive specification unification; metadata only', 'files': []}
    for side in ('Upper', 'Lower'):
        for suffix in ('.kicad_sch', '.kicad_pcb'):
            report['files'].append(patch_file(board_file(ROOT, side, suffix), side))
    (ROOT / 'Passive-unification-application.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print([(item['path'], item['parts_changed']) for item in report['files']])
