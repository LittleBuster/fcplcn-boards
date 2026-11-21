from pathlib import Path
import pcbnew as p,wx,hashlib,json,datetime
app=wx.App(False);wx.Log.EnableLogging(False)
S=Path(__file__).resolve().parents[1];upper=S/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb';lower=S/'FCPLCN-RLY-1616-1v0/FCPLCN-RLY-1616-1v0.kicad_pcb';sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();h=sha(upper)
assert h=='c9a7cbe08f812e2ce2c9469176646d118347bbdd33be58e48a8594f39d3fae1b'
b=p.LoadBoard(str(upper));lb=p.LoadBoard(str(lower));points=[]
for q in b.GetDrawings():
 if q.GetLayer()==p.Edge_Cuts:
  for v in[q.GetStart(),q.GetEnd()]:points.append([p.ToMM(v.x),p.ToMM(v.y)])
box=[min(q[0]for q in points),min(q[1]for q in points),max(q[0]for q in points),max(q[1]for q in points)];assert abs(box[3]-120.4)<1e-6
rows=[{'ref':f.GetReference(),'pin1_xy_mm':[p.ToMM(f.GetPosition().x),p.ToMM(f.GetPosition().y)]}for f in lb.GetFootprints()if'KF128'in f.GetFPIDAsString()and p.ToMM(f.GetPosition().y)>110]
mech=json.loads((S/'Stack-mechanics.json').read_text());budget=json.loads((S/'SRDA-mechanical-audit.json').read_text());assert budget['upper_sha256']==h
backparts=[q for q in budget['changed_footprints']if q['pose'][3]==p.B_Cu and q['maximum_xy_aabb_mm'][3]>119.4]
# The finished audit's changed underside components include R68 and the new U15/passives.
assert not backparts,backparts
z=mech['board_to_board_clearance_mm']-9.1-.05
r={'status':'pass'if z>0 else'fail','upper_sha256':h,'lower_sha256':sha(lower),'mechanics_sha256':sha(S/'Stack-mechanics.json'),'mechanical_envelope_report_sha256':sha(S/'SRDA-mechanical-audit.json'),'script_sha256':sha(Path(__file__)),'actual_upper_outline_centerline_aabb_mm':box,'actual_upper_dimensions_mm':[box[2]-box[0],box[3]-box[1]],'extension_from_previous_edge_mm':box[3]-119.4,'nominal_bare_pcb_strip_vertical_clearance_mm':z,'calculation':{'nominal_board_gap_mm':mech['board_to_board_clearance_mm'],'lower_terminal_maximum_height_mm':9.1,'extra_copper_soldermask_allowance_mm':.05},'lower_front_terminal_rows':rows,'nearest_lower_terminal_reference_axis_to_upper_edge_mm':min(q['pin1_xy_mm'][1]-box[3]for q in rows),'changed_backside_components_intersecting_added_strip':backparts,'scope':'Nominal Z clearance of added bare PCB strip above conservative Lower terminal9.1mm envelopes, plus reference-axis access distance. Component/tail collisions are in separate mechanical audit. Not a screwdriver-body clearance guarantee, full3Dboolean, or manufacturing/assembly stack tolerance qualification. Upper terminalY118 unchanged; prior requested terminal-row interval is unchanged.'}
assert abs(r['nearest_lower_terminal_reference_axis_to_upper_edge_mm']-2.3)<1e-6
assert sha(upper)==h
(S/'SRDA-PCB-strip-clearance.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k]for k in ['status','actual_upper_dimensions_mm','nominal_bare_pcb_strip_vertical_clearance_mm','nearest_lower_terminal_reference_axis_to_upper_edge_mm']}))
