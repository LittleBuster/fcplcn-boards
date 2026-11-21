"""Render the real two-board KiCad assembly without editing either PCB.

The upper PCB is exported by KiCad as an embedded VRML assembly. A render-only
copy of the lower PCB carries that model at the connector-defined height.
VRML uses KiCad's native tenths-of-an-inch units, so no model scale conversion
is needed. Both PCBs remain in the same global X/Y coordinate system.
"""
from pathlib import Path
from board_paths import board_file, board_dir
import argparse
import hashlib
import json
import subprocess
import tempfile


CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project-root', type=Path, default=ROOT)
parser.add_argument('--output-dir', type=Path)
parser.add_argument('--base', action='store_true', help='Also render the lower PCB alone')
parser.add_argument('--upper-bottom', action='store_true',
                    help='Also render flat and angled underside views of the upper PCB')
args = parser.parse_args()
root = args.project_root.resolve()
output = (args.output_dir or root).resolve()
output.mkdir(parents=True, exist_ok=True)
boards = {name: board_file(root, name, '.kicad_pcb')
          for name in ('Upper', 'Lower')}
sources = [path.with_suffix(suffix) for path in boards.values()
           for suffix in ('.kicad_pcb', '.kicad_pro', '.kicad_sch', '.kicad_dru')]
mechanics_path = root / 'Stack-mechanics.json'
mechanics = json.loads(mechanics_path.read_text())
sources.append(mechanics_path)
sources.extend(sorted({path for side in ('Upper', 'Lower')
                       for path in (board_dir(root, side) / '3d').glob('*')
                       if path.suffix.lower() in ('.wrl', '.step', '.stp')}))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


before = {str(path): sha(path) for path in sources}
# The physical socket and header bodies define the distance between PCBs.
# Exported VRML PCB coordinates have their origin at the board mid-plane.
# A front footprint's model origin is the lower top surface; subtract half
# the 1.6 mm upper thickness to place its exported mid-plane correctly.
upper_thickness_mm = mechanics['upper_pcb_thickness_mm']
board_gap_mm = mechanics['socket']['body_height_mm'] + mechanics['header']['body_height_mm']
top_surface_delta_mm = board_gap_mm + upper_thickness_mm
assert abs(board_gap_mm - mechanics['board_to_board_clearance_mm']) < 1e-6
assert abs(top_surface_delta_mm - mechanics['upper_top_above_lower_top_mm']) < 1e-6
upper_model_offset_mm = top_surface_delta_mm - upper_thickness_mm / 2
view_settings = {
    'preview': ['--rotate', '-32,0,-8'],
    'top': [],
}

with tempfile.TemporaryDirectory(prefix='relay-stack-render-') as temp:
    temp = Path(temp)
    model = temp / 'Upper-assembly.wrl'
    export = [CLI, 'pcb', 'export', 'vrml', '--units', 'tenths',
              '--user-origin', '0x0mm', '--output', str(model), str(boards['Upper'])]
    subprocess.run(export, check=True, capture_output=True, text=True)
    lower = boards['Lower'].read_text()
    # The temporary copy has a different KIPRJMOD directory. Preserve every
    # real lower-board custom model by resolving only that path variable.
    lower = lower.replace('${KIPRJMOD}', str(board_dir(root, 'Lower')))
    assert lower.rstrip().endswith(')')
    assembly = f'''
  (footprint "RenderOnly:UpperAssembly"
    (layer "F.Cu")
    (at 0 0)
    (property "Reference" "RENDER_ONLY_UPPER"
      (at 0 0) (layer "F.Fab") (hide yes)
      (effects (font (size 1 1) (thickness 0.15))))
    (property "Value" "UpperAssembly"
      (at 0 0) (layer "F.Fab") (hide yes)
      (effects (font (size 1 1) (thickness 0.15))))
    (attr board_only exclude_from_pos_files exclude_from_bom)
    (model "{model}"
      (offset (xyz 0 0 {upper_model_offset_mm:g}))
      (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
  )
'''
    stack = temp / 'Render-only-stack.kicad_pcb'
    stack.write_text(lower.rstrip()[:-1] + assembly + ')\n')
    scenes = [('Stack', stack)]
    if args.base:
        scenes.append(('Base', boards['Lower']))
    for scene, board in scenes:
        for view, setting in view_settings.items():
            destination = output / f'{scene}-3D-{view}.png'
            command = [CLI, 'pcb', 'render', '--width', '1736', '--height', '1264',
                       '--side', 'top', '--zoom', '1', '--background', 'opaque',
                       '--quality', 'high', '--floor', *setting,
                       '--output', str(destination), str(board)]
            log = output / f'{scene}-3D-{view}.log'
            with log.open('w') as handle:
                subprocess.run(command, check=True, stdout=handle, stderr=subprocess.STDOUT)
            print(f'Wrote {destination}', flush=True)
    if args.upper_bottom:
        for view, setting in {
                'bottom': [],
                'bottom-preview': ['--rotate', '-25,0,-8'],
        }.items():
            destination = output / f'FCPLCN-CPU-08-1v0-3D-{view}.png'
            command = [CLI, 'pcb', 'render', '--width', '1736', '--height', '1264',
                       '--side', 'bottom', '--zoom', '1', '--background', 'opaque',
                       '--quality', 'high', '--floor', *setting,
                       '--output', str(destination), str(boards['Upper'])]
            log = output / f'FCPLCN-CPU-08-1v0-3D-{view}.log'
            with log.open('w') as handle:
                subprocess.run(command, check=True, stdout=handle, stderr=subprocess.STDOUT)
            print(f'Wrote {destination}', flush=True)

after = {str(path): sha(path) for path in sources}
assert before == after, 'Native rendering changed a source PCB, project, schematic, or rule file'
manifest = {
    'renderer': 'KiCad pcb export vrml + pcb render',
    'source_sha256': after,
    'upper_top_above_lower_top_mm': top_surface_delta_mm,
    'board_to_board_clearance_mm': round(top_surface_delta_mm - upper_thickness_mm, 3),
    'source_files_preserved': True,
    'mechanics_config': str(mechanics_path),
    'socket_height_mm': mechanics['socket']['body_height_mm'],
    'header_body_height_mm': mechanics['header']['body_height_mm'],
    'view_rotation_deg': {'preview': [-32, 0, -8], 'top': [0, 0, 0]},
    'upper_bottom_views': args.upper_bottom,
}
if args.upper_bottom:
    manifest['upper_bottom_view_rotation_deg'] = {
        'bottom': [0, 0, 0], 'bottom-preview': [-25, 0, -8]}
(output / '3D-render-validation.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
print('Source PCB/project hashes unchanged.', flush=True)
