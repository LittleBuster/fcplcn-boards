"""Collect hash-bound static SRDA evidence; never write CAD or native reports."""
from pathlib import Path
from board_paths import board_dir, board_file
import json,hashlib,datetime
S=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda n:json.loads((S/n).read_text())
u=S/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb';l=S/'FCPLCN-RLY-1616-1v0/FCPLCN-RLY-1616-1v0.kicad_pcb'
assert sha(u)=='c9a7cbe08f812e2ce2c9469176646d118347bbdd33be58e48a8594f39d3fae1b'
assert sha(l)=='2a56e136b4ce4d115cb48b419a28f73fd18d330313a269209082fe5df8b0d337'
budget=read('SRDA-budget-audit.json');electrical=read('SRDA-electrical-audit.json');mechanical=read('SRDA-mechanical-audit.json');r78=read('SRDA-R78-mechanical-audit.json');strip=read('SRDA-PCB-strip-clearance.json');adm=read('SRDA-bypass-copper.json');iso=read('SRDA-ISO-bypass-copper.json')
assert budget['status']==electrical['status']=='pass'
assert all(budget['checks'].values()) and len(budget['checks'])==39
assert mechanical['collision_count']==r78['collision_count']==0 and strip['status']=='pass'
assert adm['source_stable_during_audit'] and all(q['constructed_lead_path_at_most10mm']for q in adm['records'])
for report,key in[(mechanical,'upper_sha256'),(r78,'upper_sha256'),(strip,'upper_sha256'),(adm,'source_sha256'),(iso,'source_sha256')]:assert report[key]==sha(u)
for rel,h in budget['source_sha256'].items():assert sha(S/rel)==h,rel
for path,h in electrical['sources_sha256'].items():assert sha(Path(path))==h,path
reports=['SRDA-budget-audit.json','SRDA-electrical-audit.json','SRDA-mechanical-audit.json','SRDA-R78-mechanical-audit.json','SRDA-PCB-strip-clearance.json','SRDA-bypass-copper.json','SRDA-ISO-bypass-copper.json','SRDA-electrical-connectivity.json','SRDA-source-delta-audit.json','SRDA-source-negative-controls.json']
raw=read('FCPLCN-CPU-08-1v0/DRC-with-exclusions.json')
excluded=raw['violations']
assert len(excluded)==2 and not raw['unconnected_items'] and not raw['schematic_parity']
assert all(q['type']=='npth_inside_courtyard' and q.get('excluded') for q in excluded)
assert {q['items'][0]['uuid'] for q in excluded}=={'dff86a73-60e1-4609-8bb6-a0778385b956','9ecc5bfa-0f65-4d7a-971f-928fec42a6b4'}
reports.append('FCPLCN-CPU-08-1v0/DRC-with-exclusions.json')
native={}
for board in ['Upper','Lower']:
 d=read(str(board_dir(S,board).relative_to(S))+'/DRC.json');e=read(str(board_dir(S,board).relative_to(S))+'/ERC.json');counts={k:len(d[k])for k in ['violations','unconnected_items','schematic_parity']};counts['ERC_violations']=sum(len(q.get('violations',[]))for q in e.get('sheets',[]));assert not any(counts.values()),counts;native[board]=counts
 reports += [str(board_dir(S,board).relative_to(S))+'/DRC.json',str(board_dir(S,board).relative_to(S))+'/ERC.json']
assert read('SRDA-electrical-connectivity.json')['status']=='pass'
assert read('SRDA-source-delta-audit.json')['status']=='PASS'
assert read('SRDA-source-negative-controls.json')['status']=='PASS'
sourcefiles=['ASSEMBLY.md','RS485-WORK-STATUS.md','tools/README.md','Power-budget.json','RS485-logic-budget.json','SRDA-technical-review.json','Stack-mechanics.json','tools/check_rs485_clearance.py','tools/check_r78_clearance.py','tools/check_pcb_strip_clearance.py','tools/electrical_audit.py','tools/check_board.py','tools/srda_contract.py','tools/audit_srda_budget.py','tools/collect_srda_final_evidence.py']
for board in ['Upper','Lower']:
 for ext in ['.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_dru','.xml']:sourcefiles.append(str(board_file(S,board,ext).relative_to(S)))
record={'status':'pass_for_checked_static_requirements_with_documented_layout_limits','created_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sources_sha256':{n:sha(S/n)for n in sourcefiles},'reports_sha256':{n:sha(S/n)for n in reports},'native_active_counts':native,'previous_excluded_Upper_BT1_courtyard_items':2,'inventory':{'Upper':148,'Lower':154,'combined_purchased_parts':302,'new_zero_ohm_jumper_added':False},'static_budget':{'passed':39,'total':39,**budget['calculation_summary']},'actual_ADM_bypass':{'all_six_at_most10mm':True,'constructed_external_lead_totals_mm':{q['capacitor']:q['combined_lead_length_mm']for q in adm['records']},'maximum_mm':max(q['combined_lead_length_mm']for q in adm['records'])},'ISO_engineering_target':{'target_combined_lead_mm':10,'is_claimed_mandatory_manufacturer_limit':False,'target_demonstrated_for_all_four':all(q['at_most_10mm']for q in iso['records']),'constructed_external_lead_totals_mm':{q['capacitor']:q['combined_lead_mm']for q in iso['records']},'interpretation':'Constructed copper-path upper bounds; the10mm engineering target is not demonstrated. These are documented layout limits for prototype switching/noise tests, not EM simulation or a fabricatedPASS.'},'mechanical':{'component_carrier_tail_collisions':0,'R78_and_lowstack_cap_collisions':0,'nominal_added_strip_vertical_clearance_mm':strip['nominal_bare_pcb_strip_vertical_clearance_mm'],'lower_terminal_axis_distance_from_upper_edge_mm':strip['nearest_lower_terminal_reference_axis_to_upper_edge_mm'],'actual_upper_dimensions_mm':strip['actual_upper_dimensions_mm'],'full3Dboolean_or_stack_tolerance_signoff':False},'limits':['No hardware, thermal, surge, ESD or EMC qualification performed.','No physical USB FullSpeed waveform or cable interoperability qualification performed.','TVS plus100ohmFIELDseries is not proof of compliance with every ISO1640 absolute-maximum transient condition and is not12/24V miswire protection.','Mechanical envelopes use nominal mating height and stated conservative body allowances; verify vendor clones and tool access on the assembled sample.','Full source manifests, DRC reports and actual contour connectivity are separate linked evidence, not replaced by this summary.']}
(S/'SRDA-final-evidence.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'status':record['status'],'evidence_sha256':sha(S/'SRDA-final-evidence.json'),'budget_sha256':sha(S/'SRDA-budget-audit.json'),'electrical_sha256':sha(S/'SRDA-electrical-audit.json'),'Upper_sha256':sha(u),'Lower_sha256':sha(l)},indent=2))
