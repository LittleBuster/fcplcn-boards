# -*- coding: utf-8 -*-
from pathlib import Path
import json,hashlib,math,ast
import argparse,sys,xml.etree.ElementTree as ET
parser=argparse.ArgumentParser(description='Read-only SRDA normal-logic/power/XML contract; not nativePCB orEMC validation')
parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--before-root',type=Path,required=True)
parser.add_argument('--output',type=Path)
opts=parser.parse_args();S=opts.project_root.resolve();B=opts.before_root.resolve();
p=json.loads((S/'Power-budget.json').read_text());old=json.loads((B/'Power-budget.json').read_text());l=json.loads((S/'RS485-logic-budget.json').read_text());a=p['main_3v3'];iso=p['isolated_3v3'];rc=p['protected_12v_RC'];new=p['DATA8_expansion'];checks={}
checks['main_allocations_sum']=sum(a['design_allocations_ma'].values())==a['design_total_ma']==890
checks['main_increment15_and_reserve110']=a['design_total_ma']-old['main_3v3']['design_total_ma']==15 and a['nominal_current_reserve_ma']==110
checks['RS485201of500_unchanged']=p['RS485']['local_regulator']['design_total_ma']==201 and p['RS485']['local_regulator']['rated_current_ma']==500
checks['common5V_full_TMR_budget_unchanged']=p['common_5v']==old['common_5v']
checks['isolated_electronics55_external120']=iso['own_electronics_5v_equivalent_reserve_ma']==55 and iso['external_sensor_current_design_limit_ma_combined']==120
checks['TMR_175of200_and25reserve']=55+120==iso['TMR_output_budget_ma']==175 and iso['TMR_output_design_reserve_ma']==25
checks['TMR_0p875W_below1W']=math.isclose(5*175/1000,iso['TMR_output_budget_w']) and iso['TMR_output_budget_w']<iso['upstream_total_power_w']
s=new['static_all_LOW'];checks['CPU_STATIC_independent_calc']=math.isclose(s['CPU_chip_plus_two_pullups_ma'],7.2+2000*3.5475/(4300*.99))
checks['FIELD_STATIC_independent_calc']=math.isclose(s['field_chip_plus_two_pullups_ma'],6.8+2000*5.5/(4700*.95))
checks['dynamic_reserves_positive']=s['CPU_dynamic_reserve_ma']>0 and s['field_dynamic_reserve_ma']>0
pin=(.890*3.3+(1/.76+.025*5)+.201*3.3)/.85
checks['converter_Pin_independent']=math.isclose(pin,rc['converter_input_power_W_assuming85pct_efficiency'])
checks['RC_balance']=math.isclose(rc['self_consistent_current_A']*(11.2-rc['self_consistent_current_A']),pin,rel_tol=1e-12)
checks['RC_loss']=math.isclose(rc['self_consistent_current_A']**2,rc['resistor_dissipation_W'])
checks['RC_tolerance_headroom']=rc['at_resistance_plus1pct']['protected_voltage_V']>8
checks['R12_hardware_unchanged']=rc['series_MPN']==old['protected_12v_RC']['series_MPN']and rc['R_ohm']==1
checks['inrush_ceiling_still400uF']=rc['startup_pulse']==old['protected_12v_RC']['startup_pulse']
checks['external_input_fuse_budget']=p['input_12v']['current_budget_a_minus10percent_coil_resistance']<p['input_12v']['fuse_recommended_continuous_current_a_at25c']
checks['logic_margins_unchanged_positive']=all(v>0 for k,v in l['normal_powered_checks'].items()if'margin_V'in k)
checks['no_architecture_12Vbridge']=p['RS485']['local_regulator']['input_net']=='+12V_LOGIC'and'input_bridge'not in p['RS485']
checks['DATA8_GPIO38_44_and_J3power9_10']=new['extra_direct_CPU_gpio']==[38,44]and new['J3_power_pin']==9 and new['J3_ground_pin']==10
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();lo='FCPLCN-RLY-1616-1v0/FCPLCN-RLY-1616-1v0.kicad_pcb';checks['LowerPCB_exact_before']=sha(S/lo)==sha(B/lo)
for f in ['tools/check_board.py','tools/electrical_audit.py','tools/srda_contract.py']:ast.parse((S/f).read_text())
checks['checkers_python_syntax']=True

from srda_contract import check_srda_contract
xml=ET.parse(S/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.xml').getroot();comp={c.get('ref'):c for c in xml.findall('components/comp')};netmap={r:{} for r in comp}
for net in xml.findall('nets/net'):
 for node in net.findall('node'):netmap[node.get('ref')][node.get('pin')]=net.get('name').removeprefix('/')
fields=lambda r,k:comp[r].findtext("fields/field[@name='"+k+"']",'') or ''
contract_errors=check_srda_contract(set(comp),lambda r:netmap[r],lambda r:comp[r].findtext('value',''),fields,lambda r:comp[r].findtext('footprint',''))
checks['SRDA_XML_pin_parts_and_floating_REF_contract']=not contract_errors
checks['Upper148_Lower154_combined302']=len(comp)==148 and len([v for v in ET.parse(S/'FCPLCN-RLY-1616-1v0/FCPLCN-RLY-1616-1v0.xml').findall('components/comp') if not v.get('ref').startswith('TP')])==154 and p['SRDA_protection']['combined_components']==302
review=json.loads((S/'SRDA-technical-review.json').read_text());c=review['calculations'];q=p['SRDA_protection']
checks['series100R1pct_FIELD_only']=c['Rseries_ohm_max']==101 and c['CPU_extra_series_ohm']==0
checks['DATA_LOW_independent']=math.isclose(c['DATA_5p5V_ISO_input_LOW_V'],.4+(5.5-.4)*101/(4465+101)+.002) and c['DATA_LOW_margin_V']>0
checks['I2C_LOW_independent']=math.isclose(c['I2C_3p5475V_ISO_input_LOW_V'],.4+(3.5475-.4)*101/(4465+101)+.002) and c['I2C_LOW_margin_V']>0
checks['DS18B20_LOW_and_sink_margin']=c['DS18B20_terminal_LOW_margin_V']>0 and c['DS18B20_sink_current_with_board_and2p2k_pullup_mA']<4
checks['CPU_LOW_existing53mV_no_series']=math.isclose(c['CPU_existing_LOW_margin_V'],.25*3.0525-.710) and c['CPU_existing_LOW_margin_V']>0
checks['I2C_min_sink_current_above_TI500uA']=c['ISO_min_sink_with_I2C_low_rail_mA']>.5
checks['I2C200pF_100k_rise_pass']=math.isclose(c['rise_30_70_us_at200pF'],math.log(7/3)*5036*200e-12*1e6) and c['rise_30_70_us_at200pF']<1
checks['I2C400pF_does_not_meet_100k_rise']=c['rise_30_70_us_at400pF']>1
checks['I2C_cap_ceiling234pF_and_design200pF']=math.isclose(c['I2C100k_1us_RCrise_cap_ceiling_pF'],1e6/(math.log(7/3)*5036)) and q['external_line_total_capacitance_design_pF']==200
checks['SRDA_8pF_is_typical_not_max']=q['capacitance_max_not_specified'] and q['typical_added_capacitance_pF_per_line']==8
checks['SRDA_leakage_scope_not_extended_to5p5V']=q['leakage_limit_not_guaranteed_above5V_or_temperature'] and q['logic_5p5V_corner_is_not_SRDA_leakage_qualification']
checks['protection_suballocations_within_existing_reserve']=q['main_protection_suballocation_ma']==.5 and q['field_protection_suballocation_ma']==1 and q['suballocations_do_not_increase_design_total'] and 15-s['CPU_chip_plus_two_pullups_ma']>.5 and 15-s['field_chip_plus_two_pullups_ma']>1+1.1
checks['TVS_typical_CVf_current_independent']=math.isclose(q['dynamic_typical_added_FIELD_ma_at100kHz_5p5V_all10lines'],10*8e-12*5.5*100000*1000)
checks['USB_RC_is_typical_increment_not_signoff']=math.isclose(c['USB_22R_8pF_typical_RC_ns'],22*8e-12*1e9)
checks['transient_absolute_max_not_claimed']=c['transient_illustration_only']['not_proven_by_abs_IO_current_rating']

files=['Power-budget.json','RS485-logic-budget.json','ASSEMBLY.md','tools/check_board.py','tools/electrical_audit.py','tools/README.md','RS485-WORK-STATUS.md','tools/srda_contract.py','FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.xml','SRDA-technical-review.json'];result={'status':'pass'if all(checks.values())else'fail','checks':checks,'source_sha256':{f:sha(S/f)for f in files},'Lower_PCB_sha256':sha(S/lo),'before_Upper_PCB_sha256':sha(B/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb'),'scope':'Static SRDA normal logic, XML contract, DATA8 power calculations and unchanged Lower only. Current Upper native routing, actual bypass lengths and physical/thermal/EMC qualification are separate. No current Upper CAD success asserted by this report.','calculation_summary':{'main_ma':890,'local_RS485_ma':201,'isolated_total_equivalent5V_ma':175,'isolated_external_design_limit_ma':120,'R12_current_A':rc['self_consistent_current_A'],'R12_heat_W':rc['resistor_dissipation_W'],'filtered12V_V':rc['protected_voltage_V']},'SRDA_contract_errors':contract_errors,'SRDA_normal_logic_calculations':c,'primary_sources':p['sources'],'checker_source_sha256':sha(Path(__file__))};(opts.output or S/'SRDA-budget-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'checks_passed':sum(checks.values()),'checks_total':len(checks),'failed':[k for k,v in checks.items()if not v],'summary':result['calculation_summary']},indent=2));assert all(checks.values())
