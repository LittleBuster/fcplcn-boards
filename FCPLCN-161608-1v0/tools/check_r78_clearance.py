"""Read-only interboard clearance check for new Upper R78 pins against tall Lower capacitors."""
from pathlib import Path
import json,sys,hashlib,math
import pcbnew as p,wx
app=wx.App(False);wx.Log.EnableLogging(False)
root=Path(__file__).resolve().parents[1]
upper=Path(sys.argv[1]) if len(sys.argv)>1 else root/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb'
lower=root/'FCPLCN-RLY-1616-1v0/FCPLCN-RLY-1616-1v0.kicad_pcb'
b=p.LoadBoard(str(upper));lb=p.LoadBoard(str(lower))
lf={f.GetReference():f for f in lb.GetFootprints()}
mech=json.loads((root/'Stack-mechanics.json').read_text())
caps=[]
for ref in ('C1','C11','C12'):
 f=lf[ref];a=math.radians(f.GetOrientationDegrees())
 x=f.GetPosition().x/1e6+1.25*math.cos(a);y=f.GetPosition().y/1e6-1.25*math.sin(a)
 caps.append({'ref':ref,'center_mm':[x,y],'radius_max_mm':3.4,'height_max_mm':9.0})
# Existing C8 has a 12mm-body model. It is wholly outside Upper's right edge, but include its planform.
f=lf['C8'];a=math.radians(f.GetOrientationDegrees());caps.append({'ref':'C8','center_mm':[f.GetPosition().x/1e6+1.75*math.cos(a),f.GetPosition().y/1e6-1.75*math.sin(a)],'radius_max_mm':4.0,'height_max_mm':12.073})
checks=[]
mlcc_checks=[]
r78_refs={f.GetReference() for f in b.GetFootprints() if f.GetValue().startswith('R-78K3.3')}
assert r78_refs=={'U3','U5','U12'}, ('Expected three Upper R78 modules',sorted(r78_refs))
for f in b.GetFootprints():
 if f.GetReference() not in ('C3','C4'):continue
 if f.GetLayer()!=p.B_Cu:continue
 cx,cy=f.GetPosition().x/1e6,f.GetPosition().y/1e6
 a=math.radians(f.GetOrientationDegrees())
 for cap in caps:
  dx,dy=cap['center_mm'][0]-cx,cap['center_mm'][1]-cy
  # Inverse KiCad image-coordinate rotation; package maximumL3.4,W1.8 fromTDKMPN.
  lx=math.cos(a)*dx-math.sin(a)*dy;ly=math.sin(a)*dx+math.cos(a)*dy
  dist=math.hypot(max(abs(lx)-1.7,0),max(abs(ly)-.9,0))
  xygap=dist-cap['radius_max_mm']
  zgap=mech['board_to_board_clearance_mm']-1.8-cap['height_max_mm']
  mlcc_checks.append({'upper_ref':f.GetReference(),'mpn':'C3216X5R1V226M160AC','max_body_mm':[3.4,1.8,1.8],'center_mm':[cx,cy],'rotation_deg':f.GetOrientationDegrees(),'lower_ref':cap['ref'],'xy_clearance_mm':round(xygap,4),'vertical_clearance_without_solder_standoff_mm':round(zgap,4),'collision':xygap<=0 and zgap<=0})
for f in b.GetFootprints():
 if not f.GetValue().startswith('R-78K3.3'):continue
 for pad in f.Pads():
  x,y=pad.GetPosition().x/1e6,pad.GetPosition().y/1e6
  # Manufacturer general x.x tolerance gives 4.1+.5=4.6mm max tail below the upper F surface.
  floor=mech['upper_top_above_lower_top_mm']-4.6
  for cap in caps:
   d=math.hypot(x-cap['center_mm'][0],y-cap['center_mm'][1])
   # Use lead circumscribed half diagonal (square0.74max) for conservative plan separation.
   xy_gap=d-cap['radius_max_mm']-(.74*math.sqrt(2)/2)
   zgap=floor-cap['height_max_mm']
   checks.append({'upper_ref':f.GetReference(),'upper_pad':pad.GetNumber(),'pin_xy_mm':[x,y],'lower_ref':cap['ref'],'xy_clearance_mm':round(xy_gap,4),'vertical_clearance_if_xy_overlap_mm':round(zgap,4),'collision':xy_gap<=0 and zgap<=0})
result={'upper_path':str(upper),'upper_sha256':hashlib.sha256(upper.read_bytes()).hexdigest(),'lower_sha256':hashlib.sha256(lower.read_bytes()).hexdigest(),'method':'R78Ktail length4.6maxinclmanufacturerx.x±0.5;0.74squareleadmaxcircumscribedradius; capmaxcircularbodyplanform','tail_max_mm':4.6,'tail_minimum_height_above_lower_f_mm':mech['upper_top_above_lower_top_mm']-4.6,'caps':caps,'checks':checks,'mlcc_checks':mlcc_checks,'collision_count':sum(c['collision']for c in checks)+sum(c['collision']for c in mlcc_checks),'minimum_xy_gap_mm':min(c['xy_clearance_mm']for c in checks)}
result['checked_regulators']=sorted(r78_refs)
print(json.dumps(result,indent=2))

assert result['collision_count'] == 0, 'New R78 leads or capacitors collide with Lower capacitors'
