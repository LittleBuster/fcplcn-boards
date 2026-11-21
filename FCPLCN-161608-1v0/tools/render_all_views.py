"""Native KiCad gallery: nine views of each PCB and of the mated assembly.

Run after routing is frozen. Rendering never edits either source PCB. Partial
runs with --scenes Lower and --scenes Upper Stack can share the output folder.
"""
from pathlib import Path
from board_paths import board_file, board_dir, scene_name
import argparse
import concurrent.futures
import hashlib
import html
import json
import struct
import subprocess
import tempfile

CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
ROOT = Path(__file__).resolve().parents[1]
VIEWS = {
    'top': ('top', None, 'Сверху'),
    'bottom': ('bottom', None, 'Снизу'),
    'front': ('front', None, 'Спереди'),
    'back': ('back', None, 'Сзади'),
    'left': ('left', None, 'Слева'),
    'right': ('right', None, 'Справа'),
    'angled-front': ('top', '-32,0,-8', 'Под наклоном спереди'),
    'angled-back': ('top', '32,0,8', 'Под наклоном сзади'),
    'angled-bottom': ('bottom', '-25,0,-8', 'Снизу под наклоном'),
}
LABELS = {'Stack': 'Платы в сборе', 'Upper': 'Верхняя плата', 'Lower': 'Нижняя плата'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project-root', type=Path, default=ROOT)
    ap.add_argument('--output-dir', type=Path)
    ap.add_argument('--scenes', nargs='+', choices=list(LABELS), default=list(LABELS))
    ap.add_argument('--jobs', type=int, default=2)
    ap.add_argument('--views', nargs='+', choices=list(VIEWS), default=list(VIEWS))
    args = ap.parse_args()
    root = args.project_root.resolve()
    out = (args.output_dir or root / 'Previews' / 'native-all-views').resolve()
    out.mkdir(parents=True, exist_ok=True)
    boards = {s: board_file(root, s, '.kicad_pcb') for s in ('Upper', 'Lower')}
    sides = ('Upper', 'Lower') if 'Stack' in args.scenes else tuple(args.scenes)
    sources = [boards[s].with_suffix(ext) for s in sides
               for ext in ('.kicad_pcb', '.kicad_sch', '.kicad_pro', '.kicad_dru')]
    sources.append(root / 'Stack-mechanics.json')
    for side in sides:
        sources.extend(p for p in sorted((board_dir(root, side) / '3d').glob('*'))
                       if p.suffix.lower() in ('.wrl', '.step', '.stp'))
    before = {str(p.relative_to(root)): sha(p) for p in sources}
    mechanics = json.loads((root / 'Stack-mechanics.json').read_text())
    gap = mechanics['socket']['body_height_mm'] + mechanics['header']['body_height_mm']
    assert abs(gap - mechanics['board_to_board_clearance_mm']) < 1e-6
    thickness = mechanics['upper_pcb_thickness_mm']
    top_delta = gap + thickness
    assert abs(top_delta - mechanics['upper_top_above_lower_top_mm']) < 1e-6
    results = []
    with tempfile.TemporaryDirectory(prefix='fcplcn-native-gallery-') as temp_dir:
        temp = Path(temp_dir)
        scenes = {s: boards[s] for s in args.scenes if s != 'Stack'}
        if 'Stack' in args.scenes:
            model = temp / 'Upper-assembly.wrl'
            subprocess.run([CLI, 'pcb', 'export', 'vrml', '--units', 'tenths',
                            '--user-origin', '0x0mm', '--output', str(model), str(boards['Upper'])],
                           check=True, capture_output=True, text=True)
            lower = boards['Lower'].read_text().replace('${KIPRJMOD}', str(board_dir(root, 'Lower')))
            assert lower.rstrip().endswith(')')
            assembly = f'''
  (footprint "RenderOnly:UpperAssembly" (layer "F.Cu") (at 0 0)
    (property "Reference" "RENDER_ONLY_UPPER" (at 0 0) (layer "F.Fab")
      (hide yes) (effects (font (size 1 1) (thickness 0.15))))
    (property "Value" "UpperAssembly" (at 0 0) (layer "F.Fab")
      (hide yes) (effects (font (size 1 1) (thickness 0.15))))
    (attr board_only exclude_from_pos_files exclude_from_bom)
    (model "{model}" (offset (xyz 0 0 {top_delta - thickness / 2:g}))
      (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))
'''
            stack = temp / 'Render-only-stack.kicad_pcb'
            stack.write_text(lower.rstrip()[:-1] + assembly + ')\n')
            scenes['Stack'] = stack

        def render(job):
            scene, board, name, side, rotation = job
            destination = out / f'{scene_name(scene)}-{name}.png'
            command = [CLI, 'pcb', 'render', '--width', '1736', '--height', '1264',
                       '--side', side, '--zoom', '1', '--background', 'opaque',
                       '--quality', 'high', '--floor']
            if rotation:
                command += ['--rotate', rotation]
            command += ['--output', str(destination), str(board)]
            with (out / f'{scene_name(scene)}-{name}.log').open('w') as log:
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
            actual_width, actual_height = struct.unpack('>II', destination.read_bytes()[16:24])
            result = {'scene': scene, 'view': name, 'side': side,
                      'rotation_deg': [float(x) for x in rotation.split(',')] if rotation else [0, 0, 0],
                      'file': destination.name, 'sha256': sha(destination),
                      'width': actual_width, 'height': actual_height,
                      'requested_width': 1736, 'requested_height': 1264}
            print(f'Rendered {scene}/{name}', flush=True)
            return result

        jobs = [(scene, board, name, side, rotation)
                for scene, board in scenes.items()
                for name, (side, rotation, _) in VIEWS.items() if name in args.views]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(render, jobs))
    after = {str(p.relative_to(root)): sha(p) for p in sources}
    assert before == after, 'Rendering changed CAD or model source files'
    for scene in args.scenes:
        old_path = out / f'{scene_name(scene)}-manifest.json'
        old_images = {}
        if old_path.exists() and set(args.views) != set(VIEWS):
            old = json.loads(old_path.read_text())
            assert all(sha(root / name) == value for name, value in old['source_sha256'].items()), \
                'Partial gallery render requires identical CAD/model sources'
            old_images = {r['view']: r for r in old['images']}
        old_images.update({r['view']: r for r in results if r['scene'] == scene})
        manifest = {'renderer': 'KiCad pcb export vrml + pcb render',
                    'source_sha256': after, 'source_files_preserved': True,
                    'board_to_board_clearance_mm': gap,
                    'upper_top_above_lower_top_mm': top_delta,
                    'images': [old_images[v] for v in VIEWS if v in old_images]}
        (out / f'{scene_name(scene)}-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    sections = []
    for scene, label in LABELS.items():
        manifest_path = out / f'{scene_name(scene)}-manifest.json'
        if not manifest_path.exists():
            continue
        data = json.loads(manifest_path.read_text())
        by_view = {r['view']: r for r in data['images']}
        cards = []
        for view, (_, _, view_label) in VIEWS.items():
            if view not in by_view:
                continue
            item = by_view[view]
            assert sha(out / item['file']) == item['sha256']
            cards.append(f'<a href="{html.escape(item["file"])}"><img loading="lazy" '
                         f'src="{html.escape(item["file"])}" alt="{label}: {view_label}">'
                         f'<span>{view_label}</span></a>')
        sections.append(f'<section><h2>{label}</h2><div class="grid">{"".join(cards)}</div></section>')
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FCPLCn — виды плат KiCad</title>
<style>body{margin:0;background:#111823;color:#e6edf4;font:16px system-ui,sans-serif}
main{max-width:1500px;margin:auto;padding:24px}h1{font-size:26px}p{color:#bdcad8}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
a{display:block;background:#222d3b;color:inherit;text-decoration:none;border-radius:8px;overflow:hidden}
img{display:block;width:100%;height:auto}span{display:block;padding:12px}section{margin:32px 0}</style>
<main><h1>FCPLCn — платы во всех ракурсах</h1>
<p>Рендеры исходных плат в KiCad. Нажмите изображение для полного размера.
Зазор между платами 11,05 мм. Это модель сборки, а не фотография изготовленного устройства.</p>
''' + ''.join(sections) + '</main></html>\n'
    (out / 'index.html').write_text(page)
    print(f'Gallery: {out / "index.html"}; CAD/model hashes unchanged.', flush=True)


if __name__ == '__main__':
    main()
