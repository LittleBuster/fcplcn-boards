"""Read-only envelope checks for newly placed upper RS485 parts.

This is not a full 3D boolean collision test. It checks conservative package
rectangles, Lower tall-body envelopes, carrier modeled envelopes and THT tails.
"""
from pathlib import Path
import argparse,json,hashlib,math
import pcbnew as p,wx
app=wx.App(False);wx.Log.EnableLogging(False)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project-root',type=Path,required=True)
parser.add_argument('--upper',type=Path)
parser.add_argument('--baseline',type=Path,required=True)
parser.add_argument('--output',type=Path)
args=parser.parse_args()
root=args.project_root.resolve();upper=(args.upper or root/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb').resolve()
lower=root/'FCPLCN-RLY-1616-1v0/FCPLCN-RLY-1616-1v0.kicad_pcb';base=json.loads(args.baseline.read_text())
mech=json.loads((root/'Stack-mechanics.json').read_text());gap=mech['board_to_board_clearance_mm'];top=mech['upper_top_above_lower_top_mm']
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(lower)==base['lower_sha256'],'Lower changed; rerun high-envelope inventory'
assert sha(root/'FCPLCN-CPU-08-1v0/3d/W5500_Lite_2x6-assembly.wrl')==base['carrier_model_sha256'],'Carrier model changed; update its envelopes'
b=p.LoadBoard(str(upper));lb=p.LoadBoard(str(lower));fp={f.GetReference():f for f in b.GetFootprints()};lf={f.GetReference():f for f in lb.GetFootprints()}
def pose(f):return [f.GetPosition().x/1e6,f.GetPosition().y/1e6,f.GetOrientationDegrees(),f.GetLayer(),f.GetFPIDAsString()]
changed=[ref for ref,f in fp.items() if ref not in base['footprints'] or pose(f)!=base['footprints'][ref]]
def xy(f,lx=0,ly=0):
 a=math.radians(f.GetOrientationDegrees());return [f.GetPosition().x/1e6+math.cos(a)*lx+math.sin(a)*ly,f.GetPosition().y/1e6-math.sin(a)*lx+math.cos(a)*ly]
def rect(f,w,h,lx=0,ly=0):
 cx,cy=xy(f,lx,ly);a=math.radians(f.GetOrientationDegrees());hw=(abs(w*math.cos(a))+abs(h*math.sin(a)))/2;hh=(abs(w*math.sin(a))+abs(h*math.cos(a)))/2
 return [cx-hw,cy-hh,cx+hw,cy+hh]
def rectgap(a,c):
 dx=max(a[0]-c[2],c[0]-a[2],0);dy=max(a[1]-c[3],c[1]-a[3],0)
 return math.hypot(dx,dy),max(a[0],c[0])<=min(a[2],c[2]) and max(a[1],c[1])<=min(a[3],c[3])
def circgap(a,c,r):
 dx=max(a[0]-c[0],c[0]-a[2],0);dy=max(a[1]-c[1],c[1]-a[3],0)
 d=math.hypot(dx,dy)-r;return d,d<=0
def package(f):
 name=f.GetFPIDAsString()
 if 'RECOM_R-78K' in name:return (12.5,8.8,10.7,'RECOM maximum swept body incl pin-to-case tolerance; provenance maximum_body_mm')
 if 'ADM2687E' in name:return (10.55,12.95,2.64,'RI-16-2 maximum lead/body envelope')
 if 'SOIC-8_3.9x4.9' in name or name=='RelayStack:SOIC8_SRDA_USB_Clearance':return (6.3,5.1,2.0,'conservative SOIC8 full lead/body envelope including allowance over TI D8 package')
 if 'SOIC-14_3.9x8.7' in name:return (6.2,8.75,1.75,'Nexperia SO14 SOT108-1 maximum lead/body envelope')
 if 'SOT-223' in name:return (7.3,7.3,2.0,'conservative SOT223 full envelope incl allowance')
 if 'SOT-23' in name:return (3.3,3.1,1.5,'conservative SOT23 full envelope')
 if '0805' in name:return (3.2,1.6,3.0,'conservative 0805 body/land XY and 3mm height allowance')
 if '1206' in name:return (4.3,2.2,3.0,'conservative 1206 body/land XY and 3mm height allowance')
 if 'KF128' in name:
  n=len([pad for pad in f.Pads()if pad.GetNumber()]);return (n*2.54+.4,7.0,9.1,'KEFA maximum length; swept pin-to-body/depth limits; maximum height9.1')
 if 'HBXINTAO16PIN_DIP_Vertical' in name:return (9.34,4.70,6.90,'Seller drawing nominal8.94x4.30 including shield span,H6.50 plus0.40mm engineering allowance; vendor tolerances require sample verification')
 if 'PinHeader_1x05' in name:return (2.8,13.0,10.0,'Conservative 1x5 2.54mm header body/pin envelope; pin1-origin offset accounted separately')
 if 'PinHeader_1x02' in name:return (5.2,5.2,10.0,'conservative header/shunt upper envelope')
 raise ValueError((f.GetReference(),name,'package envelope missing'))

# Physical Lower tall envelopes. All other F-side SMDs and SIP resistor networks
# are covered by a deliberately generous 7mm height allowance over the board.
high=[]
for ref in ['C1','C11','C12']:
 high.append({'ref':ref,'circle':xy(lf[ref],1.25,0),'radius':3.4,'height':9.0,'source':'APAQ max6.8x9'})
high.append({'ref':'C8','circle':xy(lf['C8'],1.75,0),'radius':4.3,'height':13.0,'source':'conservative8.6x13 around existing D8/H12 model; outside Upper'})
for ref in ['J43','J44']:
 high.append({'ref':ref,'rect':rect(lf[ref],5.25,8.45,1.27,2.54),'height':8.75,'source':'SSW8.51 nominal plus conservative body/height allowance'})
high.append({'ref':'U2 R78E right column','rect':[135.8,81.0,146.0,98.0],'height':11.2,'source':'conservative region around unchanged R78E module'})
high.append({'ref':'relay and top-terminal row','rect':[45,39.7,146,70.1],'height':20.0,'source':'conservative entire unchanged relay stripe incl body tolerance'})
for f in lf.values():
 if 'KF128' not in f.GetFPIDAsString():continue
 n=len([pad for pad in f.Pads()if pad.GetNumber()])
 high.append({'ref':f.GetReference(),'rect':rect(f,n*2.54+.6,7.0,(n-1)*1.27,.3),'height':9.1,'source':'KEFA family max/swept body envelope'})

# Existing W5500 module model remains unchanged. These nominal model-derived
# coordinates include PCB, low underside parts, headers and RJ45, with .3mm XY
# expansion used as an analysis allowance rather than a vendor guarantee.
w=fp['U2'];assert pose(w)==base['footprints']['U2'],'W5500 moved; update carrier model geometry'
def carrier(name,wid,dep,lx,ly,z0,z1):
 a=rect(w,wid+.6,dep+.6,lx,ly);return {'ref':name,'rect':a,'z':[z0,z1]}
carrier_parts=[carrier('carrier PCB',23,25,0,.25,2.54,4.14),
 carrier('underside Ethernet IC',7,7,1.1,-2.4,1.14,2.54),
 carrier('underside crystal',3.2,2.5,-4.3,-6.7,1.74,2.54),
 carrier('left module header',2.5,15.24,-10.16,0,0,2.54),
 carrier('right module header',2.5,15.24,10.16,0,0,2.54),
 carrier('RJ45 modeled envelope',16.1,22.75,0,4.875,4.14,18.2)]
top_checks=[];bottom_checks=[];tail_checks=[];parts=[]
for ref in changed:
 f=fp[ref];wid,dep,h,method=package(f)
 # KF128 origin is pin1, other IC/passive origins are component centres.
 lx=(len([pad for pad in f.Pads()if pad.GetNumber()])-1)*1.27 if 'KF128' in f.GetFPIDAsString() else 0
 ly=.3 if 'KF128' in f.GetFPIDAsString() else 0
 if 'RECOM_R-78K' in f.GetFPIDAsString():lx,ly=2.79,-1.9
 if 'PinHeader_1x05' in f.GetFPIDAsString():lx,ly=0,5.08
 a=rect(f,wid,dep,lx,ly)
 parts.append({'ref':ref,'pose':pose(f),'maximum_xy_aabb_mm':a,'height_envelope_mm':h,'method':method})
 if f.GetLayer()==p.F_Cu:
  for item in carrier_parts:
   dist,overlap=rectgap(a,item['rect']);zgap=item['z'][0]-h
   top_checks.append({'upper_ref':ref,'carrier_ref':item['ref'],'xy_gap_mm':round(dist,4),'vertical_gap_if_xy_overlap_mm':round(zgap,4),'collision':overlap and h>=item['z'][0] and item['z'][1]>=0})
 else:
  # Conservative aggregate check covers all ordinary lower SMDs and SIP networks.
  bottom_checks.append({'upper_ref':ref,'lower_ref':'ordinary Lower components height allowance7mm','xy_gap_mm':0,'vertical_gap_if_xy_overlap_mm':round(gap-h-7.0,4),'collision':gap-h-7.0<=0})
  for item in high:
   dist,overlap=circgap(a,item['circle'],item['radius'])if'circle'in item else rectgap(a,item['rect'])
   zgap=gap-h-item['height']
   bottom_checks.append({'upper_ref':ref,'lower_ref':item['ref'],'xy_gap_mm':round(dist,4),'vertical_gap_if_xy_overlap_mm':round(zgap,4),'collision':overlap and zgap<=0})
 if ref in ['J2','J3','J7','J8','JP2'] or 'RECOM_R-78K' in f.GetFPIDAsString():
  tail=4.6 if 'RECOM_R-78K' in f.GetFPIDAsString() else 2.3 if ref=='J2' else 3.5 if ref in ['J7','JP2'] else 3.8
  for pad in f.Pads():
   if not pad.GetNumber() or pad.GetAttribute()!=p.PAD_ATTRIB_PTH:continue
   x,y=pad.GetPosition().x/1e6,pad.GetPosition().y/1e6;radius=.5 if ref=='J7'else .65;a2=[x-radius,y-radius,x+radius,y+radius]
   for item in high:
    dist,overlap=circgap(a2,item['circle'],item['radius'])if'circle'in item else rectgap(a2,item['rect'])
    zgap=top-tail-item['height']
    tail_checks.append({'upper_ref':ref,'pad':pad.GetNumber(),'tail_from_upper_F_mm':tail,'tail_XY_halfwidth_mm':radius,'lower_ref':item['ref'],'xy_gap_mm':round(dist,4),'vertical_gap_if_xy_overlap_mm':round(zgap,4),'collision':overlap and zgap<=0})

checks=top_checks+bottom_checks+tail_checks;collisions=[v for v in checks if v['collision']]
result={'upper_path':str(upper),'upper_sha256':sha(upper),'lower_sha256':sha(lower),'baseline_upper_sha256':base['upper_sha256'],'mechanics_sha256':sha(root/'Stack-mechanics.json'),'carrier_model_sha256':sha(root/'FCPLCN-CPU-08-1v0/3d/W5500_Lite_2x6-assembly.wrl'),'board_gap_nominal_mm':gap,'changed_footprints':parts,'carrier_envelopes':carrier_parts,'lower_tall_envelopes':high,'top_checks':top_checks,'bottom_checks':bottom_checks,'tail_checks':tail_checks,'collision_count':len(collisions),'collisions':collisions,'scope':'Conservative AABB/circle and height checks, not a full 3D boolean. Nominal mating height; max chip bodies plus explicit conservative allowances. All unchanged Upper parts require their existing audits. Hardware clone and final assembly need sample verification.'}
if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
else:print(json.dumps(result,indent=2))
assert sha(lower)==base['lower_sha256']
assert not collisions,collisions
