"""Native KiCad 3D detail views of J2; does not edit the PCB.

The bottom view retains the HBXINTAO nominal1.90mm contact tails. On the
1.60mm PCB they project0.30mm below the plated holes. The model does not
artificially lengthen them. It also retains nominal shell-lead Y=+/-2.15mm,
while the mounting holes are shifted0.05mm outwards for copper clearance.
"""
from pathlib import Path
import argparse
import hashlib
import re
import shlex
import subprocess

default_root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--project-root',type=Path,default=default_root)
parser.add_argument('--input',type=Path)
parser.add_argument('--output-dir',type=Path)
parser.add_argument('--view',choices=['both','top','bottom'],default='both')
parser.add_argument('--print-command',action='store_true')
args=parser.parse_args()
board=args.input or args.project_root/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb'
output=args.output_dir or args.project_root
text=board.read_text()
before=hashlib.sha256(board.read_bytes()).hexdigest()
rect=next(block for block in re.findall(r'\n\t\(gr_rect[\s\S]*?\n\t\)',text) if '"Edge.Cuts"' in block)
x0,y0=map(float,re.search(r'\(start ([^)]*)\)',rect)[1].split())
x1,y1=map(float,re.search(r'\(end ([^)]*)\)',rect)[1].split())
footprint=next(block for block in text.split('\n\t(footprint ')[1:] if '(property "Reference" "J2"' in block)
jx,jy=map(float,re.search(r'\n\t\t\(at ([^)]*)\)',footprint)[1].split()[:2])
cx,cy=(x0+x1)/2,(y0+y1)/2
xy=f'{(jx-cx)/10:g},{(cy-jy)/10:g}'
cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
views={
 'top':{'rotate':'-32,0,-8','z':'.325','zoom':'3.4','file':'FCPLCN-CPU-08-1v0-USB-DIP-3D-top.png'},
 'bottom':{'rotate':'-20,0,0','z':'-.16','zoom':'4.5','file':'FCPLCN-CPU-08-1v0-USB-DIP-3D-bottom.png'}}
for side,setting in views.items():
 if args.view!='both' and args.view!=side:continue
 command=[cli,'pcb','render','--width','1600','--height','1100',
          '--side',side,'--rotate',setting['rotate'],'--pivot',xy+','+setting['z'],
          '--zoom',setting['zoom'],'--background','opaque','--quality','high',
          '--floor','--output',str(output/setting['file']),str(board)]
 print(shlex.join(command),flush=True)
 if not args.print_command:
  output.mkdir(parents=True,exist_ok=True)
  with (output/('usb-dip-render-'+side+'.log')).open('w') as log:
   subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
  print('Wrote '+str(output/setting['file']),flush=True)
after=hashlib.sha256(board.read_bytes()).hexdigest()
assert before==after,'Rendering changed the PCB'
print('PCB SHA256 '+after+'; source stable',flush=True)
