# -*- coding: utf-8 -*-
"""Read-only source guard: released EMI Upper131 -> experimental DATA8/SRDA148.

PASS here verifies the authorized source delta, never DRC/ERC, actual filled
copper connectivity, prototype EMC, or final placement/manufacturing readiness.
Only the requested JSON report is written. Historical audit_data8_revision.py
and all native CAD sources remain untouched. Run with KiCad Python.
"""
from pathlib import Path
from board_paths import board_dir
import argparse, collections, copy, csv, hashlib, json, sys
import xml.etree.ElementTree as ET
import audit_power_emi_revision as base
from audit_data8_revision import canonical
from srda_contract import check_srda_contract, expected_arrays
import pcbnew as p

BASELINE_UPPER_SHA = 'd81498f71022ca1f942df70da954d846e54012d6cf7ddeec27a39aa6dbe32d95'
KEEP_OUT_SHA = 'dce4aa7a39a01e31e7309415b9143db7fba61231227fd9199eaf558854b77e37'
APPROVED_EDGE_UUID = 'b5b6c61d-a1a5-478f-b558-7a18aac620ae'
NEW = {'U15'} | {f'R{i}' for i in range(57,71)} | {f'C{i}' for i in range(48,52)}
REMOVED = {'D5','D7'}
TVS = {'D1','D2','D3','D4','D6'}
MOVABLE = {'C14','C15','C22','R56','J2','J7','J8'}
APPROVED_EXISTING_POSES = {
 'C14':[103.0,83.0,180.0,'B.Cu'],
 'C15':[102.7,85.2,180.0,'B.Cu'],
 'C22':[103.7,88.5,0.0,'B.Cu'],
 'R56':[98.8,112.75,180.0,'B.Cu'],
 'J2':[86.0,101.6,0.0,'F.Cu'],
 'J7':[50.0,73.0,90.0,'F.Cu'],
 'J8':[115.45,118.0,0.0,'F.Cu'],
}
J2_APPROVED_POSE = [86.0,101.6,0.0,'F.Cu']
J7_APPROVED_POSE = [50.0,73.0,90.0,'F.Cu']
LIMITED_OLD_COPPER_IDS = {'/RS485_DIR': {'0287098a-df5b-48f4-9500-9c2739a7bd4b'}}
FIELD_PULLUPS = {'R17':'DATA1','R18':'DATA2','R35':'DATA3','R36':'DATA4',
                 'R39':'DATA5','R40':'DATA6','R21':'SDA','R22':'SCL'}
ALLOWED_COPPER = {'/+12V_LOGIC','/+3V3','/+3V3_RS485','/GND','/GND_ISO',
 '/+5V_ISO','/+3V3_ISO','/SDA_ISO','/SCL_ISO','/SDA_IC_ISO','/SCL_IC_ISO',
 '/RS485_RX_RAW','/DATA7_CPU','/DATA8_CPU','/USB_DN','/USB_DP',
 '/LED_NET_OUT','/LED_STATUS_OUT','/LED_ALARM_OUT','/LED_PWR_OUT',
 '/TVS_USB_REF','/TVS_LED_REF','/TVS_DATA14_REF_ISO','/TVS_DATA58_REF_ISO','/TVS_I2C_REF_ISO'}
ALLOWED_COPPER |= {f'/DATA{i}{suffix}' for i in range(1,9) for suffix in ('_ISO','_IC_ISO')}
EXACT_MANIFEST_NETS = {'/ETH_MISO_CPU','/ETH_INT_N','/ESP_BOOT','/USB_CC1','/USB_CC2','/USB_VBUS','/RS485_DIR','/MOD_VBUS','/STATUS_LED','/RTC_VBAT','/RS485_A','/RS485_B'}
EXPLICIT_PROTECTED = {'/USB_DP_CPU','/USB_DN_CPU','/USB_CC1','/USB_CC2',
 '/USB_VBUS','/USB_VBUS_SENSE','/ESP_BOOT','/ESP_EN','/I2C_SDA','/I2C_SCL',
 '/ISO_SDA_CPU','/ISO_SCL_CPU'} | {f'/DATA{i}_CPU' for i in range(1,7)}


def field_value(fp,name):
 try:return fp.GetFieldText(name)
 except KeyError:return ""

def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def xmlmap(root):
 return {(n.get('ref'),n.get('pin')):net.get('name') for net in root.findall('nets/net') for n in net.findall('node')}

def xmlnorm(node):
 return (node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),tuple(sorted([xmlnorm(c) for c in node],key=repr)))

def without_pad_nets(tree):
 tree=copy.deepcopy(canonical(tree))
 for pad in base.children(tree,{'pad'}):
  pad[:]=[x for x in pad if not(isinstance(x,list) and x[0]=='net')]
 return tree

def expected_existing(ref,old):
 out=dict(old)
 if ref=='U1':out.update({'31':'/DATA7_CPU','36':'/DATA8_CPU'})
 elif ref=='J3':out={**{str(i):f'/DATA{i}_ISO' for i in range(1,9)},'9':'/+5V_ISO','10':'/GND_ISO'}
 elif ref in TVS:out={k:'/'+v for k,v in expected_arrays()[ref].items()}
 elif ref in ('U6','U7','U8','U9'):
  for pin in ('6','7'):out[pin]=out[pin].replace('_ISO','_IC_ISO')
 elif ref in FIELD_PULLUPS:out['2']='/'+FIELD_PULLUPS[ref]+'_IC_ISO'
 return out

def expected_added():
 out={'U15':{'1':'/+3V3','2':'/DATA7_CPU','3':'/DATA8_CPU','4':'/GND','5':'/GND_ISO','6':'/DATA8_IC_ISO','7':'/DATA7_IC_ISO','8':'/+5V_ISO'}}
 for ref,a,b in [('R57','+3V3','DATA7_CPU'),('R58','+3V3','DATA8_CPU'),('R59','+5V_ISO','DATA7_IC_ISO'),('R60','+5V_ISO','DATA8_IC_ISO')]:out[ref]={'1':'/'+a,'2':'/'+b}
 for i in range(10):
  name=f'DATA{i+1}' if i<8 else ('SDA','SCL')[i-8]
  out[f'R{61+i}']={'1':'/'+name+'_ISO','2':'/'+name+'_IC_ISO'}
 for ref,rail,gnd in [('C48','+3V3','GND'),('C49','+3V3','GND'),('C50','+5V_ISO','GND_ISO'),('C51','+5V_ISO','GND_ISO')]:out[ref]={'1':'/'+rail,'2':'/'+gnd}
 return out

def zone_normalized(zone,board):
 z=copy.deepcopy(zone)
 for x in z:
  if isinstance(x,list) and x[0]=='net':
   if len(x)==2:
    try:x[1]=json.dumps(board.GetNetsByNetcode()[int(x[1])].GetNetname())
    except (KeyError,ValueError):pass
   else:x[:]=['net',x[-1]]
 return z

def zone_map(tree,board):
 return {json.loads(base.child(z,'uuid')[1]):zone_normalized(z,board) for z in base.zone_definitions(tree)}

def copper_record_delta(old,new,approved=frozenset()):
 # Record every item, including unauthorized items; an independent gate below
 # fails on any unapproved net. This diagnostic collection is not permission.
 allnets={v['net'] for d in (old,new) for v in d.values()}
 result=base.copper_delta(old,new,allnets)
 result['allowed_nets']=sorted(ALLOWED_COPPER)
 result['exact_manifest_only_nets']=sorted(approved)
 result['unapproved_changed_nets']=sorted(set(result['changed_nets'])-ALLOWED_COPPER-set(approved))
 result['all_other_net_geometry_exact']=all(v['geometry_exact'] for net,v in result['by_net'].items() if net not in ALLOWED_COPPER and net not in approved)
 return result

def run(root,before,pcb_override=None,approved_keepout=None,approved_copper=None):
 root=root.resolve();before=before.resolve();newpcb=(pcb_override or root/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb').resolve();oldpcb=before/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb'
 paths=[newpcb,oldpcb];errors=[];gates={}
 def check(ok,message):
  gates[message]=bool(ok)
  if not ok:errors.append(message)
 # .kicad_prl stores local editor/display state, not manufacturing CAD source.
 lower_names={'FCPLCN-RLY-1616-1v0'+ext for ext in ('.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_dru','.xml')}
 for name in sorted(lower_names):
  a,b=board_dir(before,'Lower')/name,board_dir(root,'Lower')/name;paths.extend([a,b])
  check(a.exists() and b.exists() and base.sha(a)==base.sha(b),'Lower byte exact '+name)
 for name,sub in [('Stack-mechanics.json',''),('FCPLCN-CPU-08-1v0.kicad_pro','Upper'),('FCPLCN-CPU-08-1v0.kicad_dru','Upper')]:
  a,b=(board_dir(before,sub) if sub else before)/name,(board_dir(root,sub) if sub else root)/name;paths.extend([a,b]);check(a.exists() and b.exists() and base.sha(a)==base.sha(b),'byte exact '+sub+'/'+name)
 for side in (before,root):paths.extend([side/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_sch',side/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.xml'])
 keep_path=(approved_keepout or root/'SRDA-approved-keepout.json').resolve();paths.append(keep_path)
 if approved_copper:paths.append(approved_copper.resolve())
 paths.extend([Path(__file__).resolve(),Path(base.__file__).resolve(),root/'tools/audit_data8_revision.py',root/'tools/srda_contract.py'])
 paths.extend([root/'FCPLCN-CPU-08-1v0/RelayStack.pretty'/name for name in ('SOIC8_SRDA_USB_Clearance.kicad_mod','C0805_C50_Clearance.kicad_mod','KF128-2.54-10P.kicad_mod')])
 paths.extend([root/'FCPLCN-CPU-08-1v0/BOM.csv',root/'FCPLCN-RLY-1616-1v0/BOM.csv',root/'BOM-combined.csv'])
 paths=list(dict.fromkeys(paths));missing=[str(f) for f in paths if not f.exists()];check(not missing,'all source files exist')
 if missing:return {'status':'FAIL','errors':errors,'missing':missing,'source_only':True,'CAD_files_not_written':True}
 hashes={str(f):base.sha(f) for f in paths};check(base.sha(oldpcb)==BASELINE_UPPER_SHA,'before Upper is frozen EMI131 baseline')
 bom_counts={side:sum(int(row['qty']) for row in csv.DictReader((board_dir(root,side)/'BOM.csv').open(encoding='utf-8-sig'))) for side in ('Upper','Lower')}
 combined_count=sum(int(row['total_qty']) for row in csv.DictReader((root/'BOM-combined.csv').open(encoding='utf-8-sig')))
 check(bom_counts=={'Upper':148,'Lower':154} and combined_count==302,'BOM148 Upper154 Lower302 combined quantities')
 boards=[p.LoadBoard(str(q)) for q in (oldpcb,newpcb)];old,new=boards
 fps=[{f.GetReference():f for f in b.GetFootprints()} for b in boards]
 check(len(fps[0])==131 and len(fps[1])==148,'Upper inventory131 to148')
 check(set(fps[1])-set(fps[0])==NEW and set(fps[0])-set(fps[1])==REMOVED,'exact19 additions and2 removals')
 trees=[base.parse(q.read_text()) for q in (oldpcb,newpcb)];afps=[base.fps_ast(t) for t in trees]
 exclude={'footprint','segment','via','arc','zone','net','gr_text'}
 top=lambda tree:[canonical(x) for x in tree if not(isinstance(x,list) and x[0] in exclude)]
 # One explicitly reviewed 1mm downward extension of the existing rectangle.
 # Match its entire original/final AST, including UUID, stroke and layer; never
 # ignore Edge.Cuts generally. No fifth isolation notch is approved here.
 edges=[]
 for tree in trees:
  edges.append([x for x in base.children(tree,{'gr_rect'}) if base.children(x,{'uuid'}) and json.loads(base.child(x,'uuid')[1])==APPROVED_EDGE_UUID])
 edge_ok=len(edges[0])==len(edges[1])==1
 outline_proof=None
 adjusted=copy.deepcopy(trees[1])
 if edge_ok:
  original=edges[0][0];expected=copy.deepcopy(original)
  edge_ok=(base.child(original,'start')==['start','47','70.96'] and base.child(original,'end')==['end','136','119.4'] and base.child(original,'layer')==['layer','"Edge.Cuts"'])
  base.child(expected,'end')[:]=['end','136','120.4']
  edge_ok=edge_ok and edges[1][0]==expected
  outline_proof={'uuid':APPROVED_EDGE_UUID,'before':original,'approved_after':expected,'actual_after':edges[1][0],'valid':bool(edge_ok),'dimensions_mm':[89.0,49.44]}
  if edge_ok:
   q=next(x for x in base.children(adjusted,{'gr_rect'}) if base.children(x,{'uuid'}) and json.loads(base.child(x,'uuid')[1])==APPROVED_EDGE_UUID)
   q[:]=copy.deepcopy(original)
 check(edge_ok,'exact approved single Edge.Cuts rectangle extension endY119.4 to120.4')
 check(top(trees[0])==top(adjusted),'all other outline layers setup and non-text board objects exact')
 moved={};fp_deltas={};unexpected_pose=[];added_geom=[]
 for ref in sorted(set(fps[0])&set(fps[1])):
  a,b=fps[0][ref],fps[1][ref];an,bn=base.netmap(a),base.netmap(b)
  if ref in APPROVED_EXISTING_POSES:
   check(base.pose(b)==APPROVED_EXISTING_POSES[ref],ref+' exact approved final rigid pose')
  check({k:v.replace('{slash}','/') for k,v in bn.items()}=={k:v.replace('{slash}','/') for k,v in expected_existing(ref,an).items()},ref+' allowed physical pin-net map')
  if base.pose(a)!=base.pose(b):
   moved[ref]={'before':base.pose(a),'after':base.pose(b),'before_footprint_sha256':base.footprint_digest(afps[0][ref]),'after_footprint_sha256':base.footprint_digest(afps[1][ref])}
   if ref not in MOVABLE|TVS:unexpected_pose.append(ref)
   if ref=='J2':check(base.pose(b)==J2_APPROVED_POSE,'J2 exact approved 1.3mm downward translation')
   if ref=='J7':check(base.pose(b)==J7_APPROVED_POSE,'J7 exact approved 1.1mm upward translation')
  left,right=without_pad_nets(afps[0][ref]),without_pad_nets(afps[1][ref])
  if ref=='J3':
   check(base.pose(a)==base.pose(b),'J3 origin rotation layer exact')
   check(b.GetValue()=='DATA1–8 / 5V / GND' and b.GetFPIDAsString()=='RelayStack:KF128-2.54-10P','J3 approved10P replacement')
   ap={v[0]:v for v in base.local_pad_geometry(a)};bp={v[0]:v for v in base.local_pad_geometry(b)}
   check(all(ap.get(str(i))==bp.get(str(i)) for i in range(1,9)),'J3 original eight physical pad geometries exact')
  elif ref in TVS:
   check(a.GetValue()=='PESD5V0X2UT' and a.GetFPIDAsString()=='Package_TO_SOT_SMD:SOT-23',ref+' baseline PESD replacement identity')
  else:
   if ref in MOVABLE:
    check(a.GetLayer()==b.GetLayer(),ref+' approved move retains layer')
    left,right=base.footprint_without_pose(left),base.footprint_without_pose(right)
   check(base.footprint_equal(left,right),ref+' all non-net footprint content exact except approved rigid pose')
   check(base.local_pad_geometry(a)==base.local_pad_geometry(b),ref+' local pads geometry exact')
  if not base.footprint_equal(canonical(afps[0][ref]),canonical(afps[1][ref])):
   fp_deltas[ref]={'before_ast':afps[0][ref],'after_ast':afps[1][ref]}
 check(not unexpected_pose,'no unapproved existing footprint pose changes')
 for ref,pins in expected_added().items():
  check(ref in fps[1] and base.netmap(fps[1][ref])==pins,ref+' exact new circuit pin map')
  if ref not in fps[1]:continue
  f=fps[1][ref]
  if ref=='R68':check(base.pose(f)==[107.0,118.3,0.0,'B.Cu'],'R68 exact approved final B.Cu pose')
  value='ISO1640BDR' if ref=='U15' else '4.3k' if ref in ('R57','R58') else '4.7k' if ref in ('R59','R60') else '100R' if ref.startswith('R') else '100nF' if ref in ('C48','C50') else '1nF'
  check(f.GetValue()==value,ref+' exact new value')
  if ref in ('R57','R58','R59','R60'):check(f.GetFieldText('Tolerance')==('1%' if ref in ('R57','R58') else '5%'),ref+' new pullup tolerance')
 # Physical geometry of new standard parts is independently compared to the
 # installed KiCad library, including mirrored/rotated pad shape and drill data.
 libroot=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
 templates=[];template_board=p.BOARD()
 for ref in sorted(NEW|TVS|{'J3'}):
  if ref not in fps[1]:continue
  f=fps[1][ref]
  expected_id='RelayStack:C0805_C50_Clearance' if ref=='C50' else 'RelayStack:SOIC8_SRDA_USB_Clearance' if ref=='D1' else 'RelayStack:KF128-2.54-10P' if ref=='J3' else 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm' if ref in TVS|{'U15'} else 'Resistor_SMD:R_0805_2012Metric' if ref.startswith('R') else 'Capacitor_SMD:C_0805_2012Metric'
  check(f.GetFPIDAsString()==expected_id,ref+' approved footprint library identity')
  lib,name=expected_id.split(':');libdir=root/'FCPLCN-CPU-08-1v0/RelayStack.pretty' if lib=='RelayStack' else libroot/(lib+'.pretty');src=libdir/(name+'.kicad_mod')
  check(src.exists(),ref+' physical footprint template available')
  if not src.exists():continue
  template=p.FootprintLoad(str(libdir),name);templates.append(template);template_board.Add(template)
  if f.GetLayer()==p.B_Cu:template.Flip(template.GetPosition(),False)
  template.SetOrientationDegrees(f.GetOrientationDegrees());template.SetPosition(f.GetPosition())
  check(base.local_pad_geometry(f)==base.local_pad_geometry(template),ref+' physical pads match approved library template')
  added_geom.append({'ref':ref,'template':str(src),'template_sha256':base.sha(src),'pose':base.pose(f),'actual_local_pads':base.local_pad_geometry(f)})
 # D1's local variant changes silk only. Independently retain the standard
 # SOIC copper, courtyard, fabrication body, attributes and 3D model.
 def srda_physical_asset(path):
  tree=base.parse(path.read_text())
  def strip_uuid(node):
   return [strip_uuid(x) if isinstance(x,list) else x for x in node if not(isinstance(x,list) and x[0]=='uuid')]
  out=[]
  for item in tree:
   if not isinstance(item,list):continue
   layer=next((x[1] for x in item if isinstance(x,list) and x[0]=='layer'),None)
   if item[0] in {'pad','model','attr'} or (item[0].startswith('fp_') and layer in {'"F.Fab"','"F.CrtYd"'}):out.append(strip_uuid(item))
  return collections.Counter(json.dumps(x) for x in out)
 custom=root/'FCPLCN-CPU-08-1v0/RelayStack.pretty/SOIC8_SRDA_USB_Clearance.kicad_mod'
 standard=libroot/'Package_SO.pretty/SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod'
 check(custom.exists() and srda_physical_asset(custom)==srda_physical_asset(standard),'D1 custom footprint retains standard pads courtyard Fab and model')
 custom_c50=root/'FCPLCN-CPU-08-1v0/RelayStack.pretty/C0805_C50_Clearance.kicad_mod'
 standard_c50=libroot/'Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod'
 check(custom_c50.exists() and srda_physical_asset(custom_c50)==srda_physical_asset(standard_c50),'C50 custom footprint retains standard0805 pads courtyard Fab and model')
 # This contract checks all5 arrays, grounded spareIO, floatingREF exclusivity,
 #10 FIELD series resistors, IC-sidepullups and unchanged USB22R.
 try:
  sd=check_srda_contract(set(fps[1]),lambda r:{k:v.removeprefix('/') for k,v in base.netmap(fps[1][r]).items()},lambda r:fps[1][r].GetValue(),lambda r,k:fps[1][r].GetFieldText(k),lambda r:fps[1][r].GetFPIDAsString())
 except Exception as e:sd=[repr(e)]
 check(not sd,'SRDA physical pin and part contract')
 copper=[base.copper(b) for b in boards];approved_nets=set();manifest_proof=None
 if approved_copper:
  manifest=json.loads(approved_copper.read_text());allowed_keys={'version','before_upper_pcb_sha256','after_upper_pcb_sha256','nets'}
  valid=set(manifest)==allowed_keys and manifest.get('version')==1 and manifest.get('before_upper_pcb_sha256')==base.sha(oldpcb) and manifest.get('after_upper_pcb_sha256')==base.sha(newpcb)
  records=manifest.get('nets',{});valid=valid and isinstance(records,dict) and bool(records) and set(records)<=EXACT_MANIFEST_NETS
  comparisons={}
  if isinstance(records,dict):
   for net,record in records.items():
    before_geometry=sorted(list(q) for q in base.geometry_counter(copper[0],net).elements())
    after_geometry=sorted(list(q) for q in base.geometry_counter(copper[1],net).elements())
    ok=isinstance(record,dict) and set(record)=={'before_geometry_nm','after_geometry_nm'} and record['before_geometry_nm']==before_geometry and record['after_geometry_nm']==after_geometry
    if net in LIMITED_OLD_COPPER_IDS:
     changed_old={uid for uid,record_old in copper[0].items() if record_old['net']==net and copper[1].get(uid)!=record_old}
     ok=ok and changed_old<=LIMITED_OLD_COPPER_IDS[net]
    comparisons[net]=bool(ok);valid=valid and ok
  check(valid,'exact approved MAIN copper manifest source finalSHA and complete geometry counters')
  if valid:approved_nets=set(records)
  manifest_proof={'file':str(approved_copper.resolve()),'sha256':base.sha(approved_copper),'valid':bool(valid),'by_net':comparisons,'full_manifest':manifest}
 delta=copper_record_delta(*copper,approved=approved_nets)
 check(not delta['unapproved_changed_nets'],'only explicitly authorized copper nets edited')
 check(delta['all_other_net_geometry_exact'],'all non-allowed copper geometries exact')
 protected=EXPLICIT_PROTECTED|({v['net'] for d in copper for v in d.values()}-ALLOWED_COPPER)
 protected_results={n:base.geometry_counter(copper[0],n)==base.geometry_counter(copper[1],n) for n in sorted(protected)}
 check(all(ok for net,ok in protected_results.items() if net not in approved_nets),'all protected USB internalI2C CPU sensor Ethernet LED-control and other nets exact except exact manifested permissions')
 # Keepouts require complete exact before/after tree matching, not merely two
 # coordinates. All other keepouts remain exact, without changing DRU/PRO.
 zm=[zone_map(t,b) for t,b in zip(trees,boards)];km=json.loads(keep_path.read_text());check(base.sha(keep_path)==KEEP_OUT_SHA,'approved keepout manifest hash exact')
 check(km.get('before_upper_pcb_sha256')==BASELINE_UPPER_SHA,'keepout manifest binds original source')
 approved={z['uuid']:z for z in km.get('zone_replacements',[])};zone_changes=[]
 for uid in sorted(set(zm[0])|set(zm[1])):
  a,b=zm[0].get(uid),zm[1].get(uid)
  if a==b:continue
  zone_changes.append({'uuid':uid,'before':a,'after':b})
  iskeep=any(isinstance(x,list) and x[0]=='keepout' for z in (a,b) if z for x in z)
  if iskeep:
   check(uid in approved and a==approved[uid]['before'] and b==approved[uid]['after'],'exact approved keepout delta '+uid)
  else:
   # Contour/priority changes to existing allowed pour nets are recorded.
   # Numeric clearance, thermal settings and layer set cannot be altered here.
   net=lambda z:json.loads(base.child(z,'net_name')[1]) if z and base.children(z,{'net_name'}) else json.loads(base.child(z,'net')[1]) if z and base.children(z,{'net'}) else ''
   check(a is not None and b is not None and net(a)==net(b) and net(a) in ALLOWED_COPPER,'existing allowed pour identity '+uid)
   controls=lambda z:[x for x in z if not(isinstance(x,list) and x[0] in {'polygon','priority'})] if z else None
   check(controls(a)==controls(b),'pour electrical settings exact '+uid)
 xm=[ET.parse(q/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.xml').getroot() for q in (before,root)];maps=[xmlmap(x) for x in xm];co=[{c.get('ref'):c for c in x.findall('components/comp')} for x in xm]
 expected={}
 for ref in set(co[0])-REMOVED:
  oldmap={pin:net for (r,pin),net in maps[0].items() if r==ref}
  expected.update({(ref,pin):net for pin,net in expected_existing(ref,oldmap).items()})
 for ref,ns in expected_added().items():expected.update({(ref,pin):net for pin,net in ns.items()})
 check(maps[1]==expected,'entire final XML pin map is exactly authorized delta')
 check(set(co[1])-set(co[0])==NEW and set(co[0])-set(co[1])==REMOVED,'XML component additions and removals exact')
 for ref in sorted(set(co[0])&set(co[1])-TVS-{'J3'}):check(xmlnorm(co[0][ref])==xmlnorm(co[1][ref]),ref+' entire XML component metadata exact')
 actual={};duplicate_errors=[]
 for f in fps[1].values():
  for q in f.Pads():
   if not q.GetNumber():continue
   key=(f.GetReference(),q.GetNumber());net=q.GetNetname().replace('{slash}','/')
   if key in actual and actual[key]!=net:duplicate_errors.append(str(key))
   actual[key]=net
 normalized_xml={k:v.replace('{slash}','/') for k,v in maps[1].items()}
 check(not duplicate_errors and actual==normalized_xml,'full final XML PCB pin parity including duplicate physical pad numbers')
 metadata=[]
 for ref in sorted(set(co[1])&set(fps[1])):
  f=fps[1][ref];c=co[1][ref]
  for name,actual_value,expected_value in [('Value',f.GetValue(),c.findtext('value','')),('Footprint',f.GetFPIDAsString(),c.findtext('footprint',''))]+[(k,field_value(f,k),c.findtext("fields/field[@name='"+k+"']",'') or '') for k in ('MPN','Manufacturer','Tolerance','Datasheet','PowerRating','ResistorType')]:
   if actual_value!=expected_value:metadata.append({'ref':ref,'field':name,'PCB':actual_value,'XML':expected_value})
 check(not metadata,'full final XML PCB metadata parity')
 check(hashes=={str(f):base.sha(f) for f in paths},'all source hashes unchanged during audit')
 return {'status':'PASS' if not errors else 'FAIL','scope':'SOURCE ONLY. Does not assert nativeDRC/ERC, current filled-plane connectivity, final placements, manufacturing release, or prototype EMC/USB performance.','preliminary_PCB_override':str(newpcb) if pcb_override else None,'source_sha256':hashes,'gates':gates,'errors':errors,'new_refs':sorted(NEW),'removed_refs':sorted(REMOVED),'replaced_TVS_refs':sorted(TVS),'approved_movable_existing_refs':sorted(MOVABLE),'observed_existing_pose_changes':moved,'unapproved_pose_changes':unexpected_pose,'footprint_changes':fp_deltas,'new_and_replaced_pad_template_proofs':added_geom,'SRDA_contract_errors':sd,'final_XML_unique_pin_count':len(maps[1]),'full_metadata_mismatches':metadata,'copper_delta':delta,'protected_copper_geometry_exact_by_net':protected_results,'approved_MAIN_copper_manifest':manifest_proof,'approved_outline_delta':outline_proof,'zone_definition_changes':zone_changes,'silkscreen_text_before':base.children(trees[0],{'gr_text'}),'silkscreen_text_after':base.children(trees[1],{'gr_text'}),'CAD_files_not_written':True}


def main():
 import wx
 app=wx.App(False);wx.Log.EnableLogging(False)
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--project-root',type=Path,required=True);parser.add_argument('--before-root',type=Path,required=True)
 parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pcb',type=Path,help='Optional frozen scratchPCB for preliminary source audit only')
 parser.add_argument('--approved-keepout',type=Path,help='Default project SRDA-approved-keepout.json; exact reviewed SHA required')
 parser.add_argument('--approved-copper-manifest',type=Path,help='Exact full before/final copper geometry and bothPCB hashes; only explicitly listed D1/J2/D4/J7 and J8 A/B nets; RS485_DIR may replace only old UUID0287098a')
 args=parser.parse_args();d=run(args.project_root,args.before_root,args.pcb,args.approved_keepout,args.approved_copper_manifest)
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'status':d['status'],'source_only':True,'errors':d['errors'],'gates_passed':sum(d.get('gates',{}).values()),'gates_total':len(d.get('gates',{})),'copper_counts':d.get('copper_delta',{}).get('counts'),'unapproved_copper_nets':d.get('copper_delta',{}).get('unapproved_changed_nets'),'unapproved_poses':d.get('unapproved_pose_changes')},ensure_ascii=False,indent=2))
 return 0 if d['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
