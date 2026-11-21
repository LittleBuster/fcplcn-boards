"""Read-only USB copper audit with one exact, hash-bound approved D1 exception.

All five other USB data/CC nets remain exact. With an approved manifest, USB_DN
must equal its complete approved after-inventory; it is never skipped. Without
one, all six data/CC nets must remain unchanged. Only the JSON report is written.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json

import pcbnew as p

PROTECTED = frozenset({'/USB_DP', '/USB_DP_CPU', '/USB_DN', '/USB_DN_CPU',
                       '/USB_CC1', '/USB_CC2'})
STRICT_FIVE = PROTECTED - {'/USB_DN'}
APPROVED_MANIFEST_SHA256 = 'aa87e6bd36a6b8cc6668de3fd9eaf0d89abb9a979d9b339db2855a6a77229e39'
DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / 'RS485-approved-USB-delta.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def geometry(item):
    """Normalize direction once, identically for before and after inventories."""
    if isinstance(item, p.PCB_VIA):
        v = item.GetPosition()
        return ('via', v.x, v.y, item.GetWidth(p.F_Cu), item.GetDrillValue(),
                item.TopLayer(), item.BottomLayer())
    a, b = item.GetStart(), item.GetEnd()
    start, end = sorted(((a.x, a.y), (b.x, b.y)))
    return ('track', *start, *end, item.GetLayer(), item.GetWidth())


def inventory(path):
    board = p.LoadBoard(str(path))
    assert board is not None, f'Cannot load PCB: {path}'
    records = collections.defaultdict(collections.Counter)
    for item in board.GetTracks():
        if item.GetNetname().startswith('/USB_'):
            records[item.GetNetname()][geometry(item)] += 1
    return records


def rows(counter):
    return [{'geometry_nm': list(key), 'quantity': n}
            for key, n in sorted(counter.items())]


def counter_from_rows(records):
    counter = collections.Counter()
    for record in records:
        key = tuple(record['geometry_nm'])
        n = record['quantity']
        assert type(n) is int and n > 0, 'Invalid geometry multiplicity'
        assert key[0] in ('track', 'via') and len(key) == 7, 'Invalid geometry schema'
        assert all(type(v) is int for v in key[1:]), 'Geometry must use integer nanometres'
        if key[0] == 'track':
            assert key[1:3] <= key[3:5], 'Track direction is not normalized'
        counter[key] += n
    return counter


def compare_usb(before, after, approved_delta=None):
    before, after = Path(before), Path(after)
    hashes = {str(path): sha(path) for path in (before, after)}
    old, new = inventory(before), inventory(after)
    assert all(old[net] == new[net] for net in STRICT_FIVE), 'One of the five unchanged USB data/CC nets changed'
    approval = None
    if approved_delta is None:
        assert old['/USB_DN'] == new['/USB_DN'], 'USB_DN changed without the exact approved manifest'
    else:
        approved_delta = Path(approved_delta)
        manifest_hash = sha(approved_delta)
        assert manifest_hash == APPROVED_MANIFEST_SHA256, 'Approved USB manifest content/binding changed'
        manifest = json.loads(approved_delta.read_text())
        assert manifest['schema'] == 'fcplcn.usb-copper-delta.v1'
        assert manifest['approved_net'] == '/USB_DN'
        assert set(manifest['strict_nets']) == STRICT_FIVE
        assert hashes[str(before)] == manifest['canonical_before']['sha256'], 'Wrong canonical USB before-PCB'
        expected_before = counter_from_rows(manifest['before_geometry'])
        expected_after = counter_from_rows(manifest['after_geometry'])
        removed = counter_from_rows(manifest['removed'])
        added = counter_from_rows(manifest['added'])
        assert sum(removed.values()) == 1 and sum(added.values()) == 5
        assert not removed - expected_before
        assert expected_before - removed + added == expected_after
        assert expected_before - expected_after == removed
        assert expected_after - expected_before == added
        assert old['/USB_DN'] == expected_before, 'USB_DN before geometry does not match approval'
        assert new['/USB_DN'] == expected_after, 'USB_DN after geometry differs from the exact approved D1 reroute'
        for net in STRICT_FIVE:
            assert old[net] == counter_from_rows(manifest['strict_net_geometries'][net]), f'Approved baseline differs on {net}'
        approval = {
            'manifest': str(approved_delta.resolve()),
            'manifest_sha256': manifest_hash,
            'canonical_before_sha256': manifest['canonical_before']['sha256'],
            'approved_candidate_sha256': manifest['approved_candidate']['sha256'],
            'net': '/USB_DN', 'removed_items': 1, 'added_items': 5,
            'complete_before_and_after_geometry_exact': True,
        }
    changes = {}
    for net in sorted(set(old) | set(new)):
        removed, added = old[net] - new[net], new[net] - old[net]
        changes[net] = {
            'unchanged': old[net] == new[net],
            'before_items': sum(old[net].values()),
            'after_items': sum(new[net].values()),
            'removed': rows(removed), 'added': rows(added),
        }
    assert hashes == {str(path): sha(path) for path in (before, after)}, 'PCB changed during read-only audit'
    return {
        'source_sha256': hashes,
        'protected_USB_data_and_CC_geometry_preserved': all(old[n] == new[n] for n in PROTECTED),
        'five_unchanged_USB_data_and_CC_nets_exact': True,
        'USB_data_and_CC_match_approved_revision': True,
        'approved_USB_DN_delta': approval,
        'scope': 'Physical track/via geometry counters, independent of UUID and track direction. '
                 'The five fixed data/CC nets are exact; USB_DN is unchanged or matches the complete '
                 'hash-bound approved inventory. VBUS and its voltage-sense changes are listed separately.',
        'nets': changes,
    }


def main():
    import wx
    app = wx.App(False)
    wx.Log.EnableLogging(False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--approved-delta', type=Path,
                        default=DEFAULT_MANIFEST if DEFAULT_MANIFEST.exists() else None)
    args = parser.parse_args()
    result = compare_usb(args.before, args.after, args.approved_delta)
    assert args.output.resolve() not in {args.before.resolve(), args.after.resolve()}, 'Report must not overwrite CAD'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({net: {'unchanged': row['unchanged'],
                            'removed': sum(x['quantity'] for x in row['removed']),
                            'added': sum(x['quantity'] for x in row['added'])}
                      for net, row in result['nets'].items()}, indent=2))


if __name__ == '__main__':
    main()
