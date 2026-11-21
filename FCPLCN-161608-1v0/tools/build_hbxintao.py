"""HBXINTAO 16PIN vertical USB-C nominal CAD from the seller's b16 drawing.

The electrical hole pattern follows the supplied drawing. Four shield holes
are deliberately shifted 0.05mm outwards in Y, retaining their diameter, so
the 0.15mm annulus and 0.20mm inter-pad clearance both fit. The model retains
the physical nominal shield lead centres Y=+/-2.15mm.
"""
from pathlib import Path
from math import pi,sin,cos
import argparse

parser=argparse.ArgumentParser()
parser.add_argument('--output-dir',type=Path)
args=parser.parse_args()
candidate=Path(__file__).resolve().parents[1]
if args.output_dir:fp_dir=model_dir=args.output_dir
elif (candidate/'FCPLCN-CPU-08-1v0').is_dir():
 fp_dir=candidate/'FCPLCN-CPU-08-1v0/RelayStack.pretty';model_dir=candidate/'FCPLCN-CPU-08-1v0/3d'
else:fp_dir=model_dir=Path(__file__).parent
fp_dir.mkdir(parents=True,exist_ok=True);model_dir.mkdir(parents=True,exist_ok=True)
name='USB_C_Receptacle_HBXINTAO16PIN_DIP_Vertical'
xs=[-3.85,-2.75,-1.65,-.55,.55,1.65,2.75,3.85]
row_a=['A1','A4','A5','A6','A7','A8','A9','A12']
row_b=['B12','B9','B8','B7','B6','B5','B4','B1']
pins={n:(x,y) for row,y in [(row_a,-.8),(row_b,.8)] for n,x in zip(row,xs)}
shell_holes=[(x,y) for x in (-2.5,2.5) for y in (-2.20,2.20)]
shell_leads=[(x,y) for x in (-2.5,2.5) for y in (-2.15,2.15)]
lines=[f'''(footprint "{name}"
  (version 20250114)
  (generator "pcbnew")
  (layer "F.Cu")
  (descr "HBXINTAO16PIN vertical DIP USB-C from supplied b16-detail-5-4 seller drawing. All16 electrical pins and4 shield pins are THT. Signalholes0.50mm, pitch1.10mm, rows1.60mm; shieldholes1.30mm. Deliberate mounting adaptation: shield drill centresY+/-2.20mm instead of nominal leadY+/-2.15mm, maintaining annulus0.15mm and minimum copperclearance0.20mm. No SMD signal pads. Tube8.94x3.16,H6.50mm;16 signal tails project1.90mm.")
  (tags "USB Type-C USB2.0 HBXINTAO16PIN vertical DIP THT")
  (attr through_hole)
  (property "Reference" "REF**" (at 0 -3.8) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.1))))
  (property "Value" "HBXINTAO16PIN" (at 0 3.8) (layer "F.Fab") (hide yes) (effects (font (size 0.8 0.8) (thickness 0.1))))
  (fp_rect (start -4.47 -1.58) (end 4.47 1.58) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
  (fp_rect (start -4.47 -2.15) (end 4.47 2.15) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
  (fp_rect (start -4.60 -3.20) (end 4.60 3.20) (stroke (width 0.1) (type solid)) (fill no) (layer "F.SilkS"))
  (fp_rect (start -4.75 -3.25) (end 4.75 3.25) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))''']
for n,(x,y) in pins.items():
 lines.append(f'  (pad "{n}" thru_hole circle (at {x} {y}) (size 0.80 0.80) (drill 0.50) (layers "*.Cu" "*.Mask"))')
for x,y in shell_holes:
 lines.append(f'  (pad "SH" thru_hole circle (at {x} {y}) (size 1.60 1.60) (drill 1.30) (layers "*.Cu" "*.Mask"))')
lines.append(f'  (model "${{KIPRJMOD}}/3d/{name}.wrl" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))\n)')
(fp_dir/(name+'.kicad_mod')).write_text('\n'.join(lines)+'\n')

parts=[];s=2.54
silver='0.69 0.72 0.75';black='0.03 0.035 0.04';gold='0.76 0.57 0.22'
def mesh(points,faces,color,ccw=False):
 coords=', '.join(' '.join(f'{v/s:.8f}' for v in (x,-y,z)) for x,y,z in points)
 indices=', '.join(', '.join(map(str,f))+', -1' for f in faces)
 winding='TRUE' if ccw else 'FALSE'
 return f'Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} shininess .35 }} }} geometry IndexedFaceSet {{ solid FALSE ccw {winding} coord Coordinate {{ point [{coords}] }} coordIndex [{indices}] }} }}'
def box(x,y,z,dx,dy,dz,color):
 pts=[(x+ix*dx/2,y+iy*dy/2,z+iz*dz/2) for iz in (-1,1) for iy in (-1,1) for ix in (-1,1)]
 fs=[[0,1,3,2],[4,6,7,5],[0,4,5,1],[2,3,7,6],[0,2,6,4],[1,5,7,3]]
 parts.append(mesh(pts,fs,color,ccw=True))
def oval(w,d,z):
 r=d/2;dx=w/2-r
 return [(dx+r*cos(-pi/2+i*pi/20),r*sin(-pi/2+i*pi/20),z) for i in range(21)]+[(-dx+r*cos(pi/2+i*pi/20),r*sin(pi/2+i*pi/20),z) for i in range(21)]
outer0,outer1=oval(8.94,3.16,.20),oval(8.94,3.16,6.50)
inner0,inner1=oval(8.34,2.56,.20),oval(8.34,2.56,6.50)
n=len(outer0);pts=outer0+outer1+inner0+inner1;faces=[]
for i in range(n):
 j=(i+1)%n
 faces.extend([[i,j,j+n,i+n],[i+2*n,i+3*n,j+3*n,j+2*n],[i+n,j+n,j+3*n,i+3*n]])
parts.append(mesh(pts,faces,silver))
# Nominal base/tongue moulding, without the wide AB7 retaining ears.
base0,base1=oval(8.85,3.05,0),oval(8.85,3.05,.50)
m=len(base0);fs=[list(reversed(range(m))),list(range(m,2*m))]
fs.extend([[i,(i+1)%m,(i+1)%m+m,i+m] for i in range(m)])
parts.append(mesh(base0+base1,fs,black))
box(0,0,.6,7.7,2.45,1.2,black)
box(0,0,3.43,6.55,.70,4.92,black)
for x in [-2.75,-1.25,-.75,-.25,.25,.75,1.25,2.75]:
 for sg in (-1,1):box(x,sg*.356,4.63,.20,.045,2.30,gold)
# Electrical tails: exact nominal1.90mm projection, all sixteen independent.
for x,y in pins.values():box(x,y,-.75,.28,.12,2.30,gold)
# Nominal physical shield leads remain on the source Y+/-2.15 centres.
# Shield projection is not separately dimensioned; 1.90mm is nominally
# derived from the drawing's overall8.40mm minus body6.50mm.
for x,y in shell_leads:
 sg=1 if y>0 else -1
 box(x,sg*1.865,.25,1.00,.87,.30,silver)
 box(x,y,-.70,1.00,.30,2.40,silver)
model='#VRML V2.0 utf8\n# Nominal mechanical model from supplied HBXINTAO16PIN b16 seller drawing.\n# Tube8.94x3.16mm,H6.50mm. Sixteen independent THT signal/power tails project1.90mm explicitly dimensioned.\n# Shield projection1.90mm nominally derived from overall8.40mm minus body6.50mm, not separately dimensioned.\n# Shield lead centresX+/-2.50,Y+/-2.15mm remain nominal; PCB drill centres differ0.05mm.\n# No AB7 ears or paired power tails. Small internal moulding details nominal.\n'+'\n'.join(parts)+'\n'
(model_dir/(name+'.wrl')).write_text(model)
print(fp_dir/(name+'.kicad_mod'));print(model_dir/(name+'.wrl'))
