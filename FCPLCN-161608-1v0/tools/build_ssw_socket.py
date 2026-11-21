"""Build the nominal Samtec SSW-103-01-L-D socket mechanical model.

One 8.51 mm housing, six real openings and 2.64 mm solder tails. All body,
pitch and tail dimensions follow the Samtec print. Small mouth/contact details
are nominal visual geometry, not manufacturing dimensions.
"""
from pathlib import Path
import json,hashlib,re

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'FCPLCN-RLY-1616-1v0/3d/StackSocket_2x03_P2.54mm.wrl'
FP=ROOT/'FCPLCN-RLY-1616-1v0/RelayBoard.pretty/StackSocket_2x03_P2.54mm.kicad_mod'
SOURCE='https://suddendocs.samtec.com/prints/ssw-1xx-xx-xxx-x-xx-xxx-xx-mkt.pdf'
HEIGHT=8.51
PITCH=2.54
TAIL=2.64
X0,X1=-1.205,3.745
Y0,Y1=-1.525,6.605
pins=[(x,y)for y in(0,PITCH,2*PITCH)for x in(0,PITCH)]
parts=['#VRML V2.0 utf8',
 '# Nominal Samtec SSW-103-01-L-D: one 8.51 mm body, 4.95 x 8.13 mm, 2.54 mm pitch.',
 '# Solder tail 0.79 x 0.41 mm, 2.64 mm long below the lower PCB top.',
 '# Source: '+SOURCE,
 '# Mouth funnel and contact spring details are nominal visual geometry.']
vertices=[];faces=[]
def face(points):
 ids=[]
 for point in points:ids.append(len(vertices));vertices.append(point)
 faces.append(ids)
def rect(x0,y0,x1,y1,z):face([(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)])
# A single mesh housing: top grid omits six 1.0 mm square openings.
xs=[X0,-.5,.5,PITCH-.5,PITCH+.5,X1]
ys=[Y0,-.5,.5,PITCH-.5,PITCH+.5,2*PITCH-.5,2*PITCH+.5,Y1]
for xa,xb in zip(xs,xs[1:]):
 for ya,yb in zip(ys,ys[1:]):
  cx,cy=(xa+xb)/2,(ya+yb)/2
  if any(abs(cx-px)<.499 and abs(cy-py)<.499 for px,py in pins):continue
  rect(xa,ya,xb,yb,HEIGHT)
# Four exterior sides and the underside of the single insulator body.
rect(X0,Y0,X1,Y1,0);faces[-1].reverse()
for (xa,ya),(xb,yb)in zip([(X0,Y0),(X1,Y0),(X1,Y1),(X0,Y1)],[(X1,Y0),(X1,Y1),(X0,Y1),(X0,Y0)]):
 face([(xa,ya,0),(xb,yb,0),(xb,yb,HEIGHT),(xa,ya,HEIGHT)])
for px,py in pins:
 corners=[(px-.5,py-.5),(px+.5,py-.5),(px+.5,py+.5),(px-.5,py+.5)]
 for a,b in zip(corners,corners[1:]+corners[:1]):
  face([(a[0],a[1],.7),(b[0],b[1],.7),(b[0],b[1],HEIGHT),(a[0],a[1],HEIGHT)]);faces[-1].reverse()
 rect(px-.5,py-.5,px+.5,py+.5,.7)
def number(v):return f'{v:.9g}'
def mesh(vertices,faces,color):
 pts=', '.join(' '.join(number(v)for v in(x/2.54,-y/2.54,z/2.54))for x,y,z in vertices)
 indices=', '.join(', '.join(str(i)for i in reversed(face))+', -1'for face in faces)
 return f'Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry IndexedFaceSet {{ solid FALSE coord Coordinate {{ point [{pts}] }} coordIndex [{indices}] }} }}'
parts.append(mesh(vertices,faces,'.045 .049 .057'))
def box(x,y,z,sx,sy,sz,color):
 parts.append(f'Transform {{ translation {number(x/2.54)} {number(-y/2.54)} {number(z/2.54)} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Box {{ size {number(sx/2.54)} {number(sy/2.54)} {number(sz/2.54)} }} }} ] }}')
for x,y in pins:
 # Flat rectangular solder-tail cross-section matches lead style -01.
 box(x,y,(3.15-TAIL)/2,.79,.41,3.15+TAIL,'.72 .73 .75')
 # Two visible mating contact springs inside the bore, below the body top.
 for sx in(-1,1):box(x+sx*.43,y,5.6,.09,.65,5.1,'.71 .55 .22')
MODEL.write_text('\n'.join(parts)+'\n')
t=FP.read_text()
t=re.sub(r'\(descr "[^"]*"\)', '(descr "Samtec SSW-103-01-L-D, 2x3 contacts, single 8.51 mm housing, 2.64 mm solder tails; compatible TSW-103-07-L-D mating post 5.842 mm. Common physical top-view pad order. '+SOURCE+'")',t)
FP.write_text(t)
provenance={'mpn':'SSW-103-01-L-D','manufacturer':'Samtec','source_url':SOURCE,'body_height_mm':HEIGHT,'body_xy_mm':[4.95,8.13],'pitch_mm':PITCH,'tail_length_mm':TAIL,'tail_cross_section_mm':[.79,.41],'mating_post':'TSW-103-07-L-D','mating_post_length_mm':5.842,'allowed_insertion_depth_mm':[3.68,6.35],'male_insulator_height_mm':2.54,'fully_seated_board_gap_mm':11.05,'upper_board_top_above_lower_top_mm':12.65,'pcb_thickness_mm':1.6,'socket_tail_projection_below_lower_bottom_mm':1.04,'model_height_is_not_two_stacked_housings':True,'visual_only_dimensions':['1.0mm mouth','0.7mm bore floor','contact spring shape'],'generator':'tools/build_ssw_socket.py','model_sha256':hashlib.sha256(MODEL.read_bytes()).hexdigest()}
source_pdf=ROOT/'FCPLCN-RLY-1616-1v0/datasheets/Samtec-SSW-series-print.pdf'
if source_pdf.exists():provenance.update({'local_source_print':'FCPLCN-RLY-1616-1v0/datasheets/Samtec-SSW-series-print.pdf','source_print_sha256':hashlib.sha256(source_pdf.read_bytes()).hexdigest()})
(ROOT/'FCPLCN-RLY-1616-1v0/3d/StackSocket-SSW103-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(MODEL)
