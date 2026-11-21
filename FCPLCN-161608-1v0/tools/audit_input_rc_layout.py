#!/usr/bin/env python3
"""Read native PCB geometry and emit the input-RC layout inventory; never saves CAD.
Run with KiCad's bundled Python. Optional --before points to a baseline project root.
"""
import argparse, collections, csv, hashlib, json, math
from pathlib import Path
import wx
APP=wx.App(False)
wx.Log.EnableLogging(False)
import pcbnew as p

def mm(v): return p.ToMM(v)
def xy(v): return [round(mm(v.x),6),round(mm(v.y),6)]
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def footprint(f):
    return {"xy_mm":xy(f.GetPosition()),"rotation_deg":round(f.GetOrientationDegrees(),6),"side":"B.Cu" if f.GetLayer()==p.B_Cu else "F.Cu","footprint":str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName())}
def track(t):
    via=isinstance(t,p.PCB_VIA)
    return {"net":str(t.GetNetname()),"layer":t.GetLayer(),"a_mm":xy(t.GetStart()),"b_mm":xy(t.GetEnd()),"width_mm":round(mm(t.GetWidth(p.F_Cu) if via else t.GetWidth()),6),"drill_mm":round(mm(t.GetDrillValue()),6) if via else None}
def non45(t):
    a,b=xy(t.GetStart()),xy(t.GetEnd());dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1])
    return min(dx,dy)>.000003 and abs(dx-dy)>.000003

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--before',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();name='FCPLCN-RLY-1616-1v0';d=args.root/name;pcb=d/(name+'.kicad_pcb');b=p.LoadBoard(str(pcb));fs={f.GetReference():f for f in b.GetFootprints()}
    newrefs=['R'+str(i) for i in range(161,177)]+['C'+str(i) for i in range(141,157)]+['R'+str(i) for i in range(181,197)]
    with (d/'BOM.csv').open(encoding='utf-8-sig',newline='') as stream: purchased=sum(int(row['qty']) for row in csv.DictReader(stream))
    result={"status":"FROZEN_LAYOUT_INVENTORY","pcb_sha256":digest(pcb),"schematic_sha256":digest(d/(name+'.kicad_sch')),"native_report":"Input-RC-DRC.json","physical_footprints":len(fs),"purchased_components":purchased,"new_0805_component_count":len(newrefs),"new_component_geometry":{r:footprint(fs[r]) for r in newrefs},"input_limiters":{r:{"value":fs[r].GetValue(),"MPN":next((q.GetText() for q in fs[r].GetFields() if q.GetName()=='MPN'),'')} for r in ['R'+str(i) for i in range(101,117)]},"back_input_pin_legend_y_mm":124.8,"technical_back_revision":{"text":"1v0 RC IN","xy_mm":[95,73]},"ground_connection_note":"Four new capacitor returns have short 0.30 mm GND links; additional 0.90/0.30 mm GND stitch at 76.10,109.95 mm. Original TLP logic filters, terminals and the main component geometry are retained."}
    if args.before:
        oldd=args.before/name if (args.before/name).is_dir() else args.before;old=p.LoadBoard(str(oldd/(name+'.kicad_pcb')));oldfs={f.GetReference():f for f in old.GetFootprints()};oldts={t.m_Uuid.AsString():t for t in old.GetTracks()};current=list(b.GetTracks());added=[t for t in current if t.m_Uuid.AsString() not in oldts];changed=[t for t in current if t.m_Uuid.AsString() in oldts and track(t)!=track(oldts[t.m_Uuid.AsString()])];newvias=[t for t in added if isinstance(t,p.PCB_VIA)];newtraces=[t for t in added if not isinstance(t,p.PCB_VIA)]
        moved={r:{"before":footprint(f),"after":footprint(fs[r])} for r,f in oldfs.items() if r in fs and footprint(f)!=footprint(fs[r])}
        padchanges=[]
        for r,f in oldfs.items():
            if r not in fs:continue
            pp={q.GetNumber():str(q.GetNetname()) for q in f.Pads()}
            for q in fs[r].Pads():
                if q.GetNumber() in pp and str(q.GetNetname())!=pp[q.GetNumber()]:padchanges.append({"ref":r,"pin":q.GetNumber(),"before":pp[q.GetNumber()],"after":str(q.GetNetname())})
        result.update({"baseline_pcb_sha256":digest(oldd/(name+'.kicad_pcb')),"baseline_footprints":len(oldfs),"existing_footprint_geometry_changes":moved,"existing_pad_net_changes":padchanges,"project_settings_bytes_unchanged":(d/(name+'.kicad_pro')).read_bytes()==(oldd/(name+'.kicad_pro')).read_bytes(),"custom_rules_bytes_unchanged":(d/(name+'.kicad_dru')).read_bytes()==(oldd/(name+'.kicad_dru')).read_bytes(),"new_trace_segments":len(newtraces),"new_trace_widths_mm":dict(collections.Counter(round(mm(t.GetWidth()),6) for t in newtraces)),"changed_old_copper_nets":sorted({str(t.GetNetname()) for t in changed}),"new_or_modified_non45_segments":[track(t) for t in added+changed if not isinstance(t,p.PCB_VIA) and non45(t)],"new_vias":[dict(track(t),annular_ring_mm=round((mm(t.GetWidth(p.F_Cu))-mm(t.GetDrillValue()))/2,6)) for t in newvias]})
    report=d/'Input-RC-layout.json' if not args.output else args.output;report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({"report":str(report),"physical_footprints":len(fs),"purchased_components":purchased,"moved_existing":len(result.get('existing_footprint_geometry_changes',{})),"new_or_modified_non45":len(result.get('new_or_modified_non45_segments',[])),"new_vias":len(result.get('new_vias',[]))},ensure_ascii=False))
if __name__=='__main__':main()
