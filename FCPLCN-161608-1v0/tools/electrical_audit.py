"""Read-only independent ADM2687E electrical audit of KiCad XML and PCB.

Only the requested JSON output is written; native PCB/SCM/projects are never saved.
The geometric terminal-loop metrics are explicitly placement lower bounds, not
fabricated full electromagnetic/copper return-path verification.
"""
from pathlib import Path
from board_paths import board_dir
import argparse,ast,hashlib,json,math,xml.etree.ElementTree as ET
import wx
app=wx.App(False);wx.Log.EnableLogging(False)
import pcbnew as p
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project-root',type=Path,default=root)
parser.add_argument('--pcb',type=Path,default=None)
parser.add_argument('--xml',type=Path,default=None)
parser.add_argument('--sch',type=Path,default=None)
parser.add_argument('--output',type=Path,default=None)
parser.add_argument('--stage',action='store_true')
parser.add_argument('--lead-audit',type=Path)
a=parser.parse_args()
root=a.project_root.resolve()
a.pcb=(a.pcb or root/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb').resolve()
a.xml=(a.xml or root/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.xml').resolve()
a.sch=(a.sch or root/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_sch').resolve()
a.output=(a.output or root/'SRDA-electrical-audit.json').resolve()
a.output.parent.mkdir(parents=True,exist_ok=True)
tracked=[a.pcb,a.xml,a.sch,root/'tools/check_board.py',root/'Power-budget.json',root/'RS485-logic-budget.json',root/'tools/srda_contract.py']
tracked.append(root/'FCPLCN-RLY-1616-1v0/FCPLCN-RLY-1616-1v0.kicad_pcb')
if a.lead_audit:tracked.append(a.lead_audit)
sha=lambda file:hashlib.sha256(file.read_bytes()).hexdigest()
hashes={str(f):sha(f) for f in tracked if f.exists()}
b=p.LoadBoard(str(a.pcb));fps=list(b.GetFootprints());fp={f.GetReference():f for f in fps}
xml=ET.parse(a.xml).getroot();cs=xml.findall('components/comp');co={c.get('ref'):c for c in cs}
errors=[];notes=[]
def require(condition,message):
 if not condition:errors.append(message)
def nets(ref):
 return {pad.GetNumber():pad.GetNetname().removeprefix('/') for pad in fp[ref].Pads() if pad.GetNumber()}
def field(ref,name):
 try:return fp[ref].GetFieldText(name)
 except KeyError:return ''
require(len(fps)==len(fp),'PCB footprint references are not unique')
require(len(cs)==len(co),'XML component references are not unique')
require(set(fp)==set(co),'XML/PCB reference inventory mismatch: '+str(sorted(set(fp)^set(co))))
xmlpins={}
for net in xml.findall('nets/net'):
 for node in net.findall('node'):
  key=(node.get('ref'),node.get('pin'))
  require(key not in xmlpins,'XML duplicate pin '+str(key))
  xmlpins[key]=net.get('name').removeprefix('/')
pcbpins={};duplicate_physical_pads={}
for f in fps:
 for pad in f.Pads():
  if not pad.GetNumber():continue
  key=(f.GetReference(),pad.GetNumber());net=pad.GetNetname().removeprefix('/')
  if net.startswith('unconnected-'):net=net.replace('{slash}','/')
  if key in pcbpins:
   duplicate_physical_pads.setdefault(key[0]+'.'+key[1],[]).append(net)
   require(pcbpins[key]==net,'Duplicated pad number has conflicting nets '+str(key))
  pcbpins[key]=net
require(xmlpins==pcbpins,'Full XML/PCB pin-net mismatch')
metadata_mismatches=[]
for ref in sorted(set(fp)&set(co)):
 c=co[ref]
 for name,actual,expected in [('Value',fp[ref].GetValue(),c.findtext('value','')),('Footprint',fp[ref].GetFPIDAsString(),c.findtext('footprint',''))]:
  if actual!=expected:metadata_mismatches.append({'ref':ref,'field':name,'PCB':actual,'XML':expected})
 for name in ['MPN','Manufacturer','Tolerance','Datasheet']:
  expected=c.findtext("fields/field[@name='"+name+"']",'') or ''
  actual=field(ref,name)
  if actual!=expected:metadata_mismatches.append({'ref':ref,'field':name,'PCB':actual,'XML':expected})
require(not metadata_mismatches,'XML/PCB component metadata mismatch')
from srda_contract import check_srda_contract
srda_errors=check_srda_contract(set(fp),nets,lambda r:fp[r].GetValue(),field,lambda r:fp[r].GetFPIDAsString())
for message in srda_errors:require(False,'SRDA: '+message)

expected={
'U11':{'1':'GND','2':'+3V3_RS485','3':'RS485_RX_RAW','4':'RS485_DIR','5':'RS485_DIR','6':'RS485_TX','7':'+3V3_RS485','8':'GND','9':'GND_ISO','10':'RS485_VISO_OUT','11':'RS485_A','12':'RS485_B','13':'RS485_B','14':'RS485_A','15':'RS485_VISO','16':'GND_ISO'},
'U12':{'1':'+12V_LOGIC','2':'GND','3':'+3V3_RS485'},
'U13':{'1':'GND','2':'RS485_TX_CPU','3':'RS485_TX_BUF','4':'GND','5':'RS485_DIR_CPU','6':'RS485_DIR_BUF','7':'GND','8':'unconnected-(U13-3Y-Pad8)','9':'GND','10':'+3V3_RS485','11':'unconnected-(U13-4Y-Pad11)','12':'GND','13':'+3V3_RS485','14':'+3V3_RS485'},
'U14':{'1':'GND','2':'RS485_RX_RAW','3':'RS485_RX_BUF','4':'+3V3','5':'GND','6':'unconnected-(U14-2Y-Pad6)','7':'GND','8':'unconnected-(U14-3Y-Pad8)','9':'GND','10':'+3V3','11':'unconnected-(U14-4Y-Pad11)','12':'GND','13':'+3V3','14':'+3V3'},
'FB1':{'1':'RS485_VISO_OUT','2':'RS485_VISO'},
'D9':{'1':'RS485_A','2':'RS485_B','3':'GND_ISO'},
'J8':{'1':'+5V_ISO','2':'RS485_A','3':'RS485_B','4':'GND_ISO'},
'JP2':{'1':'RS485_TERM','2':'RS485_B'}}
expected_values={}
for ref,value,n1,n2 in [
('R47','22R','RS485_TX_BUF','RS485_TX'),('R48','22R','RS485_DIR_BUF','RS485_DIR'),('R49','22R','RS485_RX_BUF','RS485_RX_CPU'),('R50','47k','+3V3','RS485_TX_CPU'),('R51','10k','RS485_DIR_CPU','GND'),('R52','10k','RS485_RX_CPU','+3V3'),('R53','120R 0.25W','RS485_A','RS485_TERM'),('R54','47k','+3V3_RS485','RS485_TX'),('R55','47k','RS485_DIR','GND'),('R56','47k','+3V3_RS485','RS485_RX_RAW'),
('C37','22uF 35V X5R','+12V_LOGIC','GND'),('C38','10uF','+3V3_RS485','GND'),('C39','100nF','+3V3_RS485','GND'),('C40','100nF','+3V3_RS485','GND'),('C41','10uF','RS485_VISO_OUT','GND_ISO'),('C42','100nF','RS485_VISO_OUT','GND_ISO'),('C43','100nF','RS485_VISO','GND_ISO'),('C44','10nF','RS485_VISO','GND_ISO'),('C45','10nF','+3V3_RS485','GND'),('C46','100nF','+3V3_RS485','GND'),('C47','100nF','+3V3','GND')]:
 expected[ref]={'1':n1,'2':n2};expected_values[ref]=value
for ref,pins in expected.items():
 require(ref in fp,'Missing RS485 component '+ref)
 if ref not in fp:continue
 require(nets(ref)==pins,ref+' physical pin-net mapping mismatch')
 if ref in expected_values:require(fp[ref].GetValue()==expected_values[ref],ref+' value mismatch')
for ref in ['R47','R48','R49','R50','R51','R52','R54','R55','R56']:require(field(ref,'Tolerance')=='1%',ref+' requires1%')
for pin,net in [('12','RS485_TX_CPU'),('24','RS485_RX_CPU'),('25','RS485_DIR_CPU')]:require(nets('U1')[pin]==net,'ESP32S3 module pin'+pin+' wrong signal')
mpns={'U11':('ADM2687EBRIZ','Analog Devices'),'U12':('R-78K3.3-0.5','RECOM'),'U13':('74LVC125AD,118','Nexperia'),'U14':('74LVC125AD,118','Nexperia'),'FB1':('BLM21PG221SN1D','Murata'),'D9':('CDSOT23-SM712','Bourns'),'C37':('C3216X5R1V226M160AC','TDK'),'C38':('C3216X7R1E106K160AB','TDK')}
for ref,(mpn,manufacturer) in mpns.items():
 require(field(ref,'MPN')==mpn,ref+' wrong/missing exact MPN')
 require(field(ref,'Manufacturer')==manufacturer,ref+' wrong/missing manufacturer')
for ref in ['U13','U14']:require(fp[ref].GetFPIDAsString()=='Package_SO:SOIC-14_3.9x8.7mm_P1.27mm',ref+' requires SOIC14 P1.27')
for ref,tolerance in [('C37','20%'),('C38','10%')]:
 require(fp[ref].GetFPIDAsString()=='Capacitor_SMD:C_1206_3216Metric',ref+' requires1206')
 require(field(ref,'Tolerance')==tolerance,ref+' requires '+tolerance)
require('7.5x12.75mm_P1.27mm' in fp['U11'].GetFPIDAsString(),'ADM package pitch/outline mismatch')
require(fp['U12'].GetFPIDAsString()=='RelayStack:RECOM_R-78K3.3-0.5_SIP3_P2.54mm','U12 requires the sourced RECOM SIP3 footprint')
require(all(q.GetAttribute()==p.PAD_ATTRIB_PTH for q in fp['U12'].Pads()),'U12 must use three through-hole leads')
require('R57' in fp and fp['R57'].GetValue()=='4.3k' and nets('R57')=={'1':'+3V3','2':'DATA7_CPU'},'DATA8 R57 must be the CPU4.3k pullup, not the abandoned VIN jumper')
require('/+12V_RS485' not in b.GetNetsByName(),'Abandoned +12V_RS485 net definition must not remain in PCB')
require(not any(net.get('name').removeprefix('/')=='+12V_RS485' for net in xml.findall('nets/net')),'Abandoned +12V_RS485 net must not remain in XML')
require(not any(q.GetNetname().removeprefix('/')=='+12V_RS485' for f in fp.values() for q in f.Pads()),'Abandoned +12V_RS485 branch must not remain')
require(len(fp)==len(co)==148,'DATA8/SRDA Upper inventory must include148 components')
require(b.GetCopperLayerCount()==2,'Board copper layers not2')
# The shared protected 12 V filter must exist on the actual Lower PCB too.
lower_board=p.LoadBoard(str(root/'FCPLCN-RLY-1616-1v0/FCPLCN-RLY-1616-1v0.kicad_pcb'))
lower_fp={f.GetReference():f for f in lower_board.GetFootprints()}
lower_expected={'D3':{'1':'+12V_LOGIC_RAW','2':'+12V_SYS'},'R12':{'1':'+12V_LOGIC_RAW','2':'+12V_LOGIC'},'C13':{'1':'+12V_LOGIC','2':'GND'},'C8':{'1':'+12V_LOGIC','2':'GND'}}
lower_actual={ref:{q.GetNumber():q.GetNetname().removeprefix('/') for q in lower_fp[ref].Pads() if q.GetNumber()} for ref in lower_expected if ref in lower_fp}
require(lower_actual==lower_expected,'Lower damping filter D3/R12/C13/C8 pin map differs from reviewed topology')
if 'R12' in lower_fp:
 require(lower_fp['R12'].GetFieldText('MPN')=='CRM2512-FX-1R00ELF','Lower R12 must be the reviewed pulse-rated Bourns part')
 require(lower_fp['R12'].GetFieldText('Tolerance')=='1%','Lower R12 requires 1%')
if 'C13' in lower_fp:
 require(lower_fp['C13'].GetValue()=='100nF / 50V X7R','Lower C13 value/rating differs from reviewed bypass')
raw_pins={(f.GetReference(),q.GetNumber()) for f in lower_fp.values() for q in f.Pads() if q.GetNetname().removeprefix('/')=='+12V_LOGIC_RAW'}
require(raw_pins=={('D3','1'),('R12','1')},'RAW net must end only at D3 cathode and R12 input')
lower_filter={'expected_pin_map':lower_expected,'actual_pin_map':lower_actual,'RAW_pad_inventory':sorted(raw_pins),'scope':'Independent physical-pad topology check; native clearances and connectivity must separately prove that no copper bypass remains around R12.'}
# Evaluate the root checker RS485 electrical assertions against native PCB,
# keeping this check separate from the independent expected datasheet map.
checker=root/'tools/check_board.py';text=checker.read_text();start=text.index("assert nets('J8') ==");end=text.index("assert fp['U10'].GetValue()",start);snippet=text[start:end]
root_compare='pass'
try:exec(compile(snippet,str(checker)+'::RS485', 'exec'),{'fp':fp,'nets':nets,'cpu':nets('U1'),'upper':b})
except Exception as e:root_compare=repr(e);errors.append('Root RS485 assertions failed: '+repr(e))
# Geometric bypass metrics; independent regulator supply and package checks follow.
mm=lambda v:[round(v.x/1e6,6),round(v.y/1e6,6)]
def pad(ref,number):return next(x for x in fp[ref].Pads() if x.GetNumber()==str(number))
def distance(a,c):return math.hypot(a.x-c.x,a.y-c.y)/1e6
thickness=b.GetDesignSettings().GetBoardThickness()/1e6
loops=[]
for cref,power,ground in [('C39',2,1),('C45',2,1),('C40',7,8),('C42',10,9),('C43',15,16),('C44',15,16)]:
 c1,c2=pad(cref,1),pad(cref,2);ap,ag=pad('U11',power),pad('U11',ground)
 lead_xy=distance(c1.GetPosition(),ap.GetPosition())+distance(c2.GetPosition(),ag.GetPosition())
 xy=lead_xy+distance(c1.GetPosition(),c2.GetPosition())+distance(ap.GetPosition(),ag.GetPosition())
 opposite=fp[cref].GetLayer()!=fp['U11'].GetLayer();vertical=2*thickness if opposite else 0
 record={'cap':cref,'ADM_power_pin':power,'ADM_ground_pin':ground,'cap_side':b.GetLayerName(fp[cref].GetLayer()),'ADM_side':b.GetLayerName(fp['U11'].GetLayer()),'cap_plus_xy_mm':mm(c1.GetPosition()),'cap_ground_xy_mm':mm(c2.GetPosition()),'ADM_power_xy_mm':mm(ap.GetPosition()),'ADM_ground_xy_mm':mm(ag.GetPosition()),'direct_power_distance_XY_mm':distance(c1.GetPosition(),ap.GetPosition()),'direct_ground_distance_XY_mm':distance(c2.GetPosition(),ag.GetPosition()),'terminal_loop_XY_lower_bound_mm':xy,'minimum_vertical_via_allowance_mm':vertical,'terminal_loop_3D_lower_bound_mm':xy+vertical,'two_external_leads_3D_lower_bound_mm':lead_xy+vertical,'two_external_leads_lower_bound_under10mm':lead_xy+vertical<10,'scope':'Center-to-center terminal-loop placement lower bound. Actual routed detours/ground-plane return path and effective high-frequency loop are not inferred from this metric.'}
 loops.append(record)
 if lead_xy+vertical>=10:notes.append(cref+' two-external-lead placement lower bound exceeds10mm; final routing/bypass return requires review.')
power_budget=json.loads((root/'Power-budget.json').read_text())
budget=power_budget['RS485']['local_regulator']
require(power_budget['main_3v3']['design_total_ma']==890,'DATA8 main3V3 allocation must be890mA')
require(power_budget['isolated_3v3']['own_electronics_5v_equivalent_reserve_ma']==55,'DATA8 isolated electronics reserve must be55mA')
require(power_budget['isolated_3v3']['external_sensor_current_design_limit_ma_combined']==120,'Combined external sensor limit must remain120mA')
require(budget['MPN']=='R-78K3.3-0.5' and budget['input_net']=='+12V_LOGIC','Power budget does not describe the fitted U12 supply')
require(budget['design_total_ma']==201 and budget['rated_current_ma']==500,'U12 design/rated current differs from reviewed allocation')
regulator_power={'regulator':'U12 R-78K3.3-0.5','side':b.GetLayerName(fp['U12'].GetLayer()),'budget':budget,'pads':[],'scope':'Illustrative switching-regulator power estimate, not guaranteed efficiency or enclosure thermal qualification. No SOT223 output-tab cooling assertion applies. C37/C38 are local decoupling; powered board mating is prohibited and input slew/hard-plug electrolytic requirements need independent verification.'}
for pp in fp['U12'].Pads():
 info={'pin':pp.GetNumber(),'xy_mm':mm(pp.GetPosition()),'size_mm':mm(pp.GetSize()),'drill_mm':mm(pp.GetDrillSize()),'net':pp.GetNetname().removeprefix('/'),'zones_containing_pad_center':[]}
 for layer in [p.F_Cu,p.B_Cu]:
  for z in b.Zones():
   if z.GetNetCode()==pp.GetNetCode() and z.IsOnLayer(layer) and z.GetFilledPolysList(layer).Contains(pp.GetPosition()):
    info['zones_containing_pad_center'].append({'layer':b.GetLayerName(layer),'filled_area_mm2':z.GetFilledArea()/1e12})
 regulator_power['pads'].append(info)
adm_ground_copper=[]
for number in [1,8,9,16]:
 pp=pad('U11',number);ground={'pin':number,'net':pp.GetNetname().removeprefix('/'),'xy_mm':mm(pp.GetPosition()),'same_net_nearby_vias_mm':[],'same_side_filled_copper_at_pad_center':[]}
 for item in b.GetTracks():
  if isinstance(item,p.PCB_VIA) and item.GetNetCode()==pp.GetNetCode():
   d=distance(item.GetPosition(),pp.GetPosition())
   if d<=3:ground['same_net_nearby_vias_mm'].append(round(d,6))
 for z in b.Zones():
  if z.GetNetCode()==pp.GetNetCode() and z.IsOnLayer(fp['U11'].GetLayer()) and z.GetFilledPolysList(fp['U11'].GetLayer()).Contains(pp.GetPosition()):
   ground['same_side_filled_copper_at_pad_center'].append({'area_mm2':z.GetFilledArea()/1e12,'pad_connection':z.GetPadConnection(),'thermal_spoke_mm':z.GetThermalReliefSpokeWidth()/1e6})
 ground['same_net_nearby_vias_mm'].sort();adm_ground_copper.append(ground)

# Reports are read, never regenerated here. Final audit binds them to exact source
# SHA externally; native reports contain their input filenames and timestamps.
reports={}
if not a.stage:
 for board in ['Lower','Upper']:
  for kind in ['ERC','DRC']:
   report=board_dir(root,board)/(kind+'.json')
   doc=json.loads(report.read_text());reports[board+'.'+kind]={'sha256':sha(report)}
   if kind=='DRC':
    counts={key:len(doc[key]) for key in ['violations','unconnected_items','schematic_parity']};reports[board+'.'+kind].update(counts)
    require(not any(counts.values()),board+' native DRC/opens/parity not zero')
   else:
    count=sum(len(s.get('violations',[])) for s in doc.get('sheets',[]));reports[board+'.'+kind]['violations']=count;require(count==0,board+' native ERC not zero')
copper_leads=None
if a.lead_audit:
 copper_leads=json.loads(a.lead_audit.read_text())
 require(copper_leads['source_sha256']==sha(a.pcb),'Copper-lead audit PCB SHA differs from electrical audit source')
 for q in copper_leads['records']:
  require(q['constructed_lead_path_at_most10mm'],q['capacitor']+' lacks demonstrated two-external-lead copper path at most10mm')
final_hashes={str(f):sha(f) for f in tracked if f.exists()}
require(hashes==final_hashes,'Source changed while audit was reading it; rerun from stable final files')
result={'date':'2026-11-14','status':'pass' if not errors else 'fail','stage_only':a.stage,'sources_sha256':hashes,'native_reports':reports,'errors':errors,'notes':notes,'XML_PCB_full_parity':{'component_count':len(co),'footprint_count':len(fp),'XML_pin_count':len(xmlpins),'PCB_unique_pin_count':len(pcbpins),'refs_unique':len(cs)==len(co) and len(fps)==len(fp),'full_pin_net_match':xmlpins==pcbpins,'duplicate_physical_pad_numbers':duplicate_physical_pads,'metadata_mismatches':metadata_mismatches},'independent_RS485_pin_map':expected,'critical_MPNs':{ref:{'MPN':field(ref,'MPN'),'Manufacturer':field(ref,'Manufacturer'),'footprint':fp[ref].GetFPIDAsString()} for ref in mpns},'SRDA_pin_part_contract':{'status':'pass' if not srda_errors else 'fail','errors':srda_errors,'scope':'Pin topology and component contract; no transient/USB qualification inferred.'},'root_check_board_RS485_comparison':{'status':root_compare,'assertion_statements':sum(isinstance(x,ast.Assert) for x in ast.walk(ast.parse(snippet)))},'bypass_placement':loops,'bypass_actual_copper_leads':copper_leads,'local_regulator_power':regulator_power,'ADM_ground_copper':adm_ground_copper,'poweroff_logic':{'buffers':'Nexperia74LVC125AD,118; U13 local3V3_RS485 / U14 main3V3','ADM_input_biases':'TX47kPUlocal; DIR47kPD; localRO47kPU','CPU_side_biases':'TX47kPUmain; DIR10kPD; RX10kPUmain','Ioff_10uA_scope':'VCC=0V, -40..85C; not an intermediate-ramp guarantee','prototype_required':['Independent main/local rail on/off order and slow ramps','ADM transmit/receive under load54ohm and120ohm','R78 U12 heat, VIN slew and main/local rail ripple/undershoot during relay switching','Actual total input current and fuse/inrush margin']},'dangerous_connections_checked':{'ADM_primary_power_is_dedicated_3V3_from_12V_R78':nets('U12')==expected['U12'] and nets('U11')['2']==nets('U11')['7']=='+3V3_RS485','no_5V_RxD_direct_into_ESP32':nets('U14')==expected['U14'] and nets('U11')['3']=='RS485_RX_RAW','no_internal_ADM_isoPower_parallel_with_external3V3ISO':'+3V3_ISO' not in nets('U11').values() and nets('FB1')==expected['FB1'],'half_duplex_A_Y_and_B_Z_joined_correctly':nets('U11')['11']==nets('U11')['14']=='RS485_A' and nets('U11')['12']==nets('U11')['13']=='RS485_B','all_bus_ground_refs_GND_ISO':nets('U11')['9']==nets('U11')['16']==nets('J8')['4']=='GND_ISO','bus_supply_pin_5V_from_TMR_domain':nets('J8')['1']=='+5V_ISO','sensor_and_RS485_ground_domain_shared_not_port_isolated':nets('J3')['10']==nets('J5')['4']==nets('J8')['4']=='GND_ISO'},'primary_sources':{'ADM2687E':'https://www.analog.com/media/en/technical-documentation/data-sheets/adm2682e-adm2687e.pdf','buffer':'https://assets.nexperia.com/documents/data-sheet/74LVC125A.pdf','U12_R78':'https://recom-power.com/pdf/Innoline/R-78K-0.5.pdf','C37':'https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C3216X5R1V226M160AC','C38':'https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=C3216X7R1E106K160AB','C38_characterization':'https://product.tdk.com/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c3216x7r1e106k160ab_200122.pdf'},'limits':'XML/PCB physical pin topology, part metadata, placement lower bounds, regulator pin map and filled copper inventory. Not EMC certification, high-voltage isolation qualification, full EM return-path extraction or physical prototype validation.'}
result['Lower_RC_filter']=lower_filter
a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'output':str(a.output),'status':result['status'],'errors':errors,'notes':notes,'component_count':len(co),'full_pin_net_match':xmlpins==pcbpins,'root_RS485_assertions':root_compare},indent=2,ensure_ascii=False))
if errors:raise SystemExit(1)
