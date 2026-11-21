from pathlib import Path
from board_paths import board_name
import argparse,hashlib,json,collections,pcbnew as p,wx
from audit_rs485_rules import audit_upper_rules
from audit_usb_copper import compare_usb, geometry
app=wx.App(False);wx.Log.EnableLogging(False)
parser=argparse.ArgumentParser(description="Read-only source delta audit for the ADM2687E revision")
parser.add_argument('--project-root',type=Path,required=True)
parser.add_argument('--before-root',type=Path,required=True)
parser.add_argument('--output',type=Path)
args=parser.parse_args()
root=args.project_root.resolve();backup=args.before_root.resolve()
protected_usb={'/USB_DP','/USB_DP_CPU','/USB_DN','/USB_DN_CPU','/USB_CC1','/USB_CC2'}
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def snapshot(board):
 return {f.GetReference():{'pose':(f.GetPosition().x,f.GetPosition().y,f.GetOrientationDegrees(),f.GetLayer()),'fp':f.GetFPIDAsString(),'value':f.GetValue(),'pads':{s.GetNumber():(s.GetPosition().x,s.GetPosition().y,s.GetNetname()) for s in f.Pads() if s.GetNumber()}} for f in board.GetFootprints()}
def track(t):return (*geometry(t),t.GetNetname())
def outline(board):
 return sorted((d.GetShape(),d.GetStart().x,d.GetStart().y,d.GetEnd().x,d.GetEnd().y,d.GetWidth()) for d in board.GetDrawings() if d.GetLayer()==p.Edge_Cuts)
result={}
for side in ('Lower','Upper'):
 rel=Path(board_name(side))/(board_name(side)+'.kicad_pcb');old=p.LoadBoard(str(backup/rel));new=p.LoadBoard(str(root/rel));a,b=snapshot(old),snapshot(new)
 removed=sorted(set(a)-set(b));added=sorted(set(b)-set(a));poses=[];netmaps=[];footprints=[];values=[]
 for ref in sorted(set(a)&set(b)):
  if a[ref]['pose']!=b[ref]['pose']:poses.append({'ref':ref,'before':a[ref]['pose'],'after':b[ref]['pose']})
  if a[ref]['fp']!=b[ref]['fp']:footprints.append({'ref':ref,'before':a[ref]['fp'],'after':b[ref]['fp']})
  pa={k:v[2] for k,v in a[ref]['pads'].items()};pb={k:v[2] for k,v in b[ref]['pads'].items()}
  if pa!=pb:netmaps.append({'ref':ref,'before':pa,'after':pb})
  if a[ref]['value']!=b[ref]['value']:values.append({'ref':ref,'before':a[ref]['value'],'after':b[ref]['value']})
 assert outline(old)==outline(new) and new.GetCopperLayerCount()==2
 oldtracks={t.m_Uuid.AsString():track(t) for t in old.GetTracks()};newtracks={t.m_Uuid.AsString():track(t) for t in new.GetTracks()}
 usb0=collections.Counter(track(t) for t in old.GetTracks() if t.GetNetname() in protected_usb)
 usb1=collections.Counter(track(t) for t in new.GetTracks() if t.GetNetname() in protected_usb)
 if side=='Lower':
  assert not removed and not added and not poses and not netmaps and not footprints
  assert values==[{'ref':'F1','before':'0452001.MRL','after':'045201.5MRL'}]
  assert oldtracks==newtracks
 else:
  assert set(removed)=={'J4','J9','J10','J11'}
  assert all(k['ref'] in {'J3','J8','U1'} for k in netmaps)
  assert all(k['ref'] in {'J3','J8','C34'} for k in footprints)
  assert a['C34']['value']==b['C34']['value']=='100nF','C34 must remain 100nF'
  for change in footprints:
   if change['ref']=='C34':
    assert change=={'ref':'C34','before':'Capacitor_SMD:C_0805_2012Metric','after':'Capacitor_SMD:C_1206_3216Metric'},'Unapproved C34 footprint change'
    assert a['C34']['value']==b['C34']['value']=='100nF','C34 must remain 100nF'
    assert {k:v[2] for k,v in a['C34']['pads'].items()}=={k:v[2] for k,v in b['C34']['pads'].items()}=={'1':'/RTC_VCC','2':'/GND'},'C34 net map changed'
  assert a['R9']==b['R9'],'R9 placement/0805/value/pads must remain exact'
  usb_audit=compare_usb(backup/rel,root/rel,root/'RS485-approved-USB-delta.json')
 approved_rule_delta=None
 if side=='Lower':
  for ext in ('.kicad_pro','.kicad_dru'):assert sha(root/rel.with_suffix(ext))==sha(backup/rel.with_suffix(ext)),str(rel.with_suffix(ext))
 else:
  approved_rule_delta=audit_upper_rules((backup/rel.with_suffix('.kicad_pro')).read_text(),(root/rel.with_suffix('.kicad_pro')).read_text(),(backup/rel.with_suffix('.kicad_dru')).read_text(),(root/rel.with_suffix('.kicad_dru')).read_text())
 points=[pt for d in new.GetDrawings() if d.GetLayer()==p.Edge_Cuts for pt in (d.GetStart(),d.GetEnd())]
 result[side]={'before_sha256':sha(backup/rel),'sha256':sha(root/rel),'footprints':len(b),'added_refs':added,'removed_refs':removed,'moved_or_flipped':poses,'changed_pad_net_maps':netmaps,'changed_footprints':footprints,'changed_values':values,'board_size_mm':[(max(q.x for q in points)-min(q.x for q in points))/1e6,(max(q.y for q in points)-min(q.y for q in points))/1e6],'outline_and_layer_count_preserved':True,'project_preserved':side=='Lower','rules_preserved_or_strengthened':side=='Lower','rules_match_approved_revision':True,'approved_rule_delta':approved_rule_delta,'USB_data_and_CC_track_via_geometry_preserved':usb0==usb1,'USB_data_and_CC_match_approved_revision':True,'approved_USB_DN_delta':usb_audit['approved_USB_DN_delta']if side=='Upper'else None,'copper_delta':{'added':len(set(newtracks)-set(oldtracks)),'removed':len(set(oldtracks)-set(newtracks)),'modified_existing':sum(oldtracks[k]!=newtracks[k] for k in set(oldtracks)&set(newtracks))}}
result['Stack-mechanics_sha256']=sha(root/'Stack-mechanics.json');assert sha(root/'Stack-mechanics.json')==sha(backup/'Stack-mechanics.json')
(args.output or root/'RS485-source-delta-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:{x:y for x,y in v.items() if x not in ['changed_pad_net_maps','moved_or_flipped']} for k,v in result.items() if isinstance(v,dict)},ensure_ascii=False,indent=2))
