"""Recalculate the approved split supplies; all current sums are design estimates.

Do not infer measured maxima, guaranteed transient performance or environmental
qualification from the static/tolerance arithmetic. Historical reports stay intact.
"""
from pathlib import Path
from copy import deepcopy
import json, math
ROOT=Path(__file__).resolve().parents[1]
def up(value, places=1):
    scale=10**places
    return math.ceil((value-1e-10)*scale)/scale

def apply():
    p=json.loads((ROOT/'Power-budget.json').read_text())
    p['revision']='Local supplies split: CPU164/RLY248 total412; Lower3V3 K0.5 plus bead; Upper5V E1.0 for TMR'
    if 'historical_5v_LDO_budget' not in p:
        p['historical_5v_LDO_budget']={'status':'history, superseded by local supply split','common_5v':deepcopy(p['common_5v']),'lower_LDO':deepcopy(p['Lower3V3_current_review']['LDO'])}
    p['common_5v']={
        'source':'Upper.U17 R-78E5.0-1.0','input_net':'+12V_LOGIC','output_net':'+5V_TMR',
        'rated_current_ma':1000,'loads':['Upper.U4 TMR-1-0511 input pin2; C11 and C56 local bypass'],
        'lower_design_current_ma':0,'TMR_at_full_output_1w_typical_efficiency_pct':76,
        'TMR_at_full_output_typical_input_ma':round(1000/.76/5,3),
        'combined_full_load_design_estimate_ma':round(1000/.76/5,3),
        'engineering_allocation_ma':300,'nominal_current_reserve_ma':700,
        'TMR_no_load_input_typical_ma':40,'full_load_efficiency_must_not_be_applied_at_no_load':True,
        'main_Upper_3v3_not_supplied_by_5v':True,'RS485_Upper_3v3_not_supplied_by_5v':True,
        'interboard_5v':False,'Lower_no_5v_loads':True,
        'scope':'263.158mA is the 1W TMR input estimate at typical76% efficiency.300mA is a rounded engineering allocation, not a guaranteed maximum input current across startup/load/temperature. Isolated output remains1W and external sensor budget remains120mA combined.'}
    p['common_5v']['voltage_review']={'additive_static_25C_V':[4.625,5.375],
        'including_half_120mVpp_reference_ripple_V':[4.565,5.435],
        'TMR_input_operating_range_V':[4.5,5.5],
        'scope':'Illustrative25C accuracy/line/load corner; reference ripple is not a guaranteed all-temperature/transient envelope. Verify at U4 pins, particularly startup and no-load.'}
    p['stack_power_pins']['LEFT_J43_J1_pins_3_4']='GND; left header1..4 all GND,5SDA,6SCL'
    p['stack_power_pins']['no_interboard_5v_or_3v3']=True
    lo=3.3*(1-(.027+.003+.027));hi=3.3*(1+(.027+.003+.027));dt=3.3*.0001*65
    bead_r=.05;allocation=.1;drop=bead_r*allocation;ripple_pp=.060
    vmin=lo-drop-ripple_pp/2-dt; vmax=hi+dt+ripple_pp/2
    review=p['Lower3V3_current_review'];review.pop('LDO',None)
    review.update(source='Lower.U2 R-78K3.3-0.5 from +12V_LOGIC; +3V3_DCDC through FB1 to +3V3',
        review_rail_V=[vmin,vmax],rail_scope='Engineering envelope:25C additive accuracy/line/load, stated temperature coefficient over65K,5mV bead DC drop at100mA, plus half the60mVp-p reference ripple in each direction. Coefficient/ripple are not guaranteed worst-case limits; trace drops, startup and transients remain unbounded by this estimate.')
    rows=review['rows']
    for row in rows:
        if row['refs']=='R121..R136':
            row['initial_tolerance_only_all_LOW_bound_ma']=16*hi/(10000*.99)*1000
            row['engineering_tol_plus_TCR_bound_ma']=16*vmax/(10000*(1-.01-.0065))*1000
            row['calculation']='16*3.53955V/[10k*(1-0.01-0.0065)]; rounded up. Generic resistor100ppm/K across65K remains an engineering assumption.'
            row['component_allocation_ma']=up(row['engineering_tol_plus_TCR_bound_ma'])
        elif row['refs']=='RN1,RN2':
            row['initial_tolerance_only_bound_ma']=16*hi/(10000*.98)*1000
            row['engineering_rail_and_tol_plus_TCR_bound_ma']=16*vmax/(10000*(1-.02-.0065))*1000
            row['component_allocation_ma']=up(row['engineering_rail_and_tol_plus_TCR_bound_ma'])
            row['scope']='Bourns2% initial tolerance and100ppm/K with65K allowance; new3.53955V engineering upper rail. Resistor ageing and PCB heating require validation.'
        elif row['refs']=='R2,R3':
            row['initial_tolerance_only_both_LOW_bound_ma']=2*hi/(4700*.99)*1000
            row['engineering_tol_plus_TCR_bound_ma']=2*vmax/(4700*(1-.01-.0065))*1000
            row['component_allocation_ma']=up(row['engineering_tol_plus_TCR_bound_ma'])
    total=round(sum(r['component_allocation_ma'] for r in rows),3)
    review.update(engineering_component_envelope_ma=total,reserve_over_component_envelope_ma=100-total,
        envelope_scope=f'{total}mA combines published component limits with labelled rail/resistor/driver assumptions;100mA is the approved allocation. Neither is a measured full-board or guaranteed all-temperature maximum.')
    rp=10000*(1+.01+.0065);rs=470*(1+.01+.0065)
    low=.6+1e-6*rs;high=vmin-(50e-6+1e-6)*rp-1e-6*rs
    logic={'GPPUA_GPPUB':0,'TLP_VOLmax_at_listed_test_point_V':.6,'TLP_OFF_leakage_at_listed_limit_uA':50,
           'MCP_input_leakage_uA':1,'pullup_max_engineering_ohm':rp,'series_max_engineering_ohm':rs,
           'review_min_rail_V':vmin,'Vin_LOWmax_V':low,'MCP_VIL_limit_V':.2*vmin,'LOW_margin_V':.2*vmin-low,
           'Vin_HIGHmin_V':high,'MCP_VIH_required_V':.8*vmin,'HIGH_margin_V':high-.8*vmin,
           'required_minimum_VDD_for_LOW_V':low/.2,
           'rail_headroom_above_LOW_requirement_V':vmin-low/.2,
           'scope':'Reuses existing TLP/MCP published test-condition limits; calculated after new supply engineering envelope. Positive static margins do not guarantee startup, hot-plug, EFT or surge performance.'}
    p['lower_3v3']={
        'source':'Lower.U2 R-78K3.3-0.5','input_net':'+12V_LOGIC','raw_output_net':'+3V3_DCDC','output_net':'+3V3',
        'rated_current_ma':500,'engineering_allocation_ma':100,'engineering_component_envelope_ma':total,'nominal_current_reserve_ma':400,
        'ferrite':{'ref':'FB1','MPN':'BLM21PG221SN1D','DCR_max_ohm':bead_r,'current_rating_ma':2000,'DC_drop_V_at100mA':drop,'power_W_at100mA':allocation**2*bead_r,'DC_loss_already_inside_U2_raw_output_power':True,
                  'scope':'220ohm is its100MHz impedance, not DC resistance. Attenuation at converter ripple frequency or cable disturbances is not inferred from that number.'},
        'accuracy_max_pct_at25C':2.7,'line_regulation_max_pct':.3,'load_regulation_max_pct_0_to100percent':2.7,
        'additive_static_corner_at25C_V':[lo,hi],'filtered_min_static_at25C_V':lo-drop,
        'reference_ripple_pp_V':ripple_pp,'temperature_coefficient_pct_per_K':.01,'temperature_delta_K_assumption':65,
        'engineering_rail_V':[vmin,vmax],'logic_review':logic,
        'efficiency_assumption_pct':85,'output_power_W_at100mA':3.3*allocation,
        'dissipation_W_at100mA_estimate':3.3*allocation/.85-3.3*allocation,
        'scope':review['rail_scope'],
        'removed_LDO_U8':True,'filter_caps':'C3/C6 raw side; C7 and IC100nF bypass filtered side',
        'prototype_checks':['U2 input/output startup and load steps','Local3V3 at the furthest TLP/MCP under all inputs and relays','Temperature and converter ripple in enclosure','Independent rail sequencing/I2C partial-power behaviour']}
    t=p['TLP2363'];t['engineering_lower3v3_envelope_V']=[vmin,vmax];t['lower3v3_envelope_scope']=review['rail_scope']
    t['logic_margins_with_GPPU_disabled']=logic
    for key in ['common5v_design_current_ma','lower_LDO_dissipation_W_at5V_and3p3V','lower_LDO_loss_includes_0p1mA_ground_current_allowance']:t.pop(key,None)
    t['historical_budget_note']='Original LDO/5V numbers are retained in historical_5v_LDO_budget and prior SHA-bound reports only.'
    p['SRDA_protection'].update(Upper_components=164,Lower_components=248,combined_components=412)
    # Simultaneous design allocation, with full external TMR power already inside its input allocation.
    powers={'main3v3':3.3*.902,'RS485_local3v3':3.3*.201,'lower3v3':p['lower_3v3']['output_power_W_at100mA'],'TMR_input5v':5*.300}
    pin=sum(powers.values())/.85
    panel=.108;vin=11.2
    def rc(r):
        current=((vin+r*panel)-math.sqrt((vin+r*panel)**2-4*r*(pin+vin*panel)))/(2*r)
        return {'R_ohm':r,'I_A':current,'protected_voltage_V':vin-current*r,'resistor_dissipation_W':current**2*r}
    cr=rc(1.01);cn=rc(1)
    d=p['input_12v'];calc=d['calculation'];coil=11.6/1200*16;coilhi=coil/.9;di=(11.6-1.2)/1420*16
    calc.update(logic_supply_after_R12_v=cr['protected_voltage_V'],common5v_output_power_w=powers['TMR_input5v'],
        lower3v3_output_power_w=powers['lower3v3'],logic_input_current_a=cr['I_A'],series_resistor_power_W=cr['resistor_dissipation_W'],logic_converter_power_before_R12_w=pin,
        scope='Simultaneous902mA UpperMAIN3V3,201mA RS485,100mA Lower3V3 at nominal raw3.3V; bead loss is already inside the raw output power,300mA local5V TMR input and108mA panel; all regulators85% illustrative efficiency. Full1W TMR at76%typ would instead require263.158mA at5V. Not measured peak/inrush or guaranteed PSU/efficiency maximum.')
    for key in ['Lower_LDO_ground_current_allowance_ma','U12_conversion_only_reduction_a_without_RC_vs_5v_LDO','FRAM_increment_ma_on_lower3v3_and_5v','TLP2363_detector_increment_ma_on_lower3v3_and_5v']:calc.pop(key,None)
    d.update(current_budget_a_nominal_coils=cr['I_A']+coil+di,current_budget_a_minus10percent_coil_resistance=cr['I_A']+coilhi+di,
        audit='Power-split-design-review.json; historical fuse/input reports validate their own earlier budgets only.')
    d['nominal_25c_fuse_current_reserve_a_at_minus10percent_coil_resistance']=1.125-d['current_budget_a_minus10percent_coil_resistance']
    r=p['protected_12v_RC'];r.update(converter_input_power_W_assuming85pct_efficiency=pin,self_consistent_current_A=cn['I_A'],voltage_drop_V=cn['I_A'],protected_voltage_V=cn['protected_voltage_V'],resistor_dissipation_W=cn['resistor_dissipation_W'])
    r['at_resistance_plus1pct']={**cr,'headroom_to_Upper_R78E5_min8V':cr['protected_voltage_V']-8,'headroom_to_R78K_min4p5V':cr['protected_voltage_V']-4.5}
    p['ibutton_panel']['filtered_logic_rail_at_full_budget_v']=cr['protected_voltage_V']
    p['RS485']['local_regulator']['input_current_ma_at_filtered_design_voltage_estimate']=p['RS485']['local_regulator']['input_power_w_estimate']/cr['protected_voltage_V']*1000
    p['sources']['Murata_BLM21PG221SN1D']='https://www.murata.com/en-eu/api/pdfdownloadapi?cate=cgsubChipFerriBead&partno=BLM21PG221SN1D'
    p['lower_3v3']['review_report']='Power-split-design-review.json'
    report={'revision':p['revision'],'supplies':{k:p[k]for k in ['main_3v3','lower_3v3','common_5v','isolated_3v3']},'Lower3V3_current_review':review,'input_12v':d,'protected_12v_RC':r,
        'TMR_1W_and_external120mA_limits_unchanged':True,'Upper_U12_RS485_design_current_ma':201,
        'retained_field_input_RC':'Unchanged1.2k/220R/1uF/4.7k; prior timing reports are historical calculations using prior rail assumptions',
        'postfilter_release_engineering_corner_ms':-(rp+rs)*126.5e-9*math.log(1-.8*vmin/high)*1000,
        'postfilter_release_scope':'Initial input0V, effective C upper1.265*100nF, leakage limits and resistorTCR allowances above; not a guaranteed timing limit',
        'sources':p['sources'],'limits':'Design arithmetic and published part test points; assembled startup, EMI, transient and thermal qualification remain prototype work.'}
    (ROOT/'Power-budget.json').write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'Power-split-design-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'Lower_component_envelope_ma':total,'Lower_allocation_ma':100,'TMR_5V_engineering_allocation_ma':300,'Lower_engineering_rail_V':[vmin,vmax],'input_current_a':d['current_budget_a_minus10percent_coil_resistance'],'R12_power_w':cr['resistor_dissipation_W']},indent=2))
if __name__=='__main__':apply()
