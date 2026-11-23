import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from board_paths import board_file
from passive_specifications import component_spec, approved_references, TDK_10UF_MPN

import wx

app = wx.App(False)
wx.Log.EnableLogging(False)
import pcbnew as p

root = Path(sys.argv[1])
boards = {k: p.LoadBoard(str(board_file(root, k, '.kicad_pcb'))) for k in ('Lower', 'Upper')}
upper = boards['Upper']
fp = {f.GetReference(): f for f in upper.GetFootprints()}
lower_fp = {f.GetReference(): f for f in boards['Lower'].GetFootprints()}

# Purchasing properties are checked in addition to the existing pin/net rules.
for side, parts in (('Upper', fp), ('Lower', lower_fp)):
    for reference in approved_references(side):
        specification = component_spec(side, reference)
        part = parts[reference]
        assert part.GetValue() == specification['value'], (side, reference, 'Value')
        for key, value in specification['fields'].items():
            assert part.GetFieldText(key) == value, (side, reference, key)
        if 'datasheet' in specification:
            assert part.GetFieldText('Datasheet') == specification['datasheet'], (side, reference, 'Datasheet')

def expected_value(reference, previous):
    specification = component_spec('Upper', reference)
    return specification['value'] if specification else previous

def lower_nets(ref):
    return {pad.GetNumber(): pad.GetNetname().removeprefix('/')
            for pad in lower_fp[ref].Pads() if pad.GetNumber()}

# Powered, open-collector optocouplers: pull up before the series filter so
# the filter cannot form a DC divider or directly load VO with 100 nF.
assert len(lower_fp) == 251
assert not any('LTV-847' in part.GetValue() for part in lower_fp.values())
tlp_bypass_distance_mm = {}
for channel in range(1, 17):
    ref = f'U{20 + channel}'
    part = lower_fp[ref]
    assert part.GetValue() == 'TLP2363'
    assert part.GetFieldText('MPN') == 'TLP2363(TPL,E'
    assert part.GetFPIDAsString() == 'RelayBoard:TLP2363_5pin_SO6'
    assert lower_nets(ref) == {'1': f'Net-(D{100 + channel}-K)', '3': f'DIF{channel}',
                               '4': 'GND', '5': f'OPTO{channel}_RAW', '6': '+3V3'}
    assert lower_nets(f'R{120 + channel}') == {'1': '+3V3', '2': f'OPTO{channel}_RAW'}
    assert lower_nets(f'R{140 + channel}') == {'1': f'OPTO{channel}_RAW', '2': f'IN{channel}'}
    assert lower_nets(f'C{100 + channel}') == {'1': f'IN{channel}', '2': 'GND'}
    assert lower_nets(f'C{120 + channel}') == {'1': '+3V3', '2': 'GND'}
    assert lower_nets(f'R{160 + channel}') == {'1': f'DIF{channel}', '2': f'DI{channel}'}
    assert lower_nets(f'R{180 + channel}') == {'1': f'Net-(D{100 + channel}-K)', '2': f'DIF{channel}'}
    assert lower_nets(f'C{140 + channel}') == {'1': f'DIF{channel}', '2': 'GND'}
    assert lower_nets(f'D{100 + channel}') == {'1': f'Net-(D{100 + channel}-K)', '2': f'DIF{channel}'}
    assert lower_nets(f'D{120 + channel}') == {'1': f'DI{channel}', '2': 'GND'}
    vdd = next(pad for pad in part.Pads() if pad.GetNumber() == '6')
    cap = next(pad for pad in lower_fp[f'C{120 + channel}'].Pads() if pad.GetNumber() == '1')
    distance = math.hypot(vdd.GetPosition().x - cap.GetPosition().x,
                          vdd.GetPosition().y - cap.GetPosition().y) / 1e6
    assert distance < 10, (ref, 'bypass farther than 10 mm', distance)
    tlp_bypass_distance_mm[ref] = round(distance, 3)

assert 'JP1' not in lower_fp
assert not any(item.GetNetname() == '/+5V'
               for item in list(boards['Lower'].GetTracks())
               + [pad for f in lower_fp.values() for pad in f.Pads()])
assert lower_nets('U2') == {'1': '+12V_LOGIC', '2': 'GND', '3': '+3V3_DCDC'}
assert lower_fp['U2'].GetValue() == lower_fp['U2'].GetFieldText('MPN') == 'R-78K3.3-0.5'
assert lower_fp['U2'].GetFPIDAsString() == 'RelayBoard:RECOM_R-78K3.3-0.5_SIP3_P2.54mm'
assert all(pad.GetAttribute() == p.PAD_ATTRIB_PTH for pad in lower_fp['U2'].Pads())
assert 'U8' not in lower_fp
assert lower_nets('FB1') == {'1': '+3V3_DCDC', '2': '+3V3'}
assert lower_fp['FB1'].GetValue() == '220R @100MHz / 2A'
assert lower_fp['FB1'].GetFieldText('MPN') == 'BLM21PG221SN1D'
assert lower_fp['FB1'].GetFieldText('Manufacturer') == 'Murata'
assert lower_fp['FB1'].GetFPIDAsString() == 'RelayBoard:L_0805_PowerFilter'
assert lower_nets('C3') == lower_nets('C6') == {'1': '+3V3_DCDC', '2': 'GND'}
assert lower_nets('C7') == {'1': '+3V3', '2': 'GND'}
assert all(pad.GetNetname().removeprefix('/') not in ('MOD_VBUS', '+5V_TMR', '+5V')
           for part in lower_fp.values() for pad in part.Pads())
assert lower_fp['F1'].GetValue() == '045201.5MRL'
assert lower_fp['F1'].GetFieldText('MPN') == '045201.5MRL'
assert lower_fp['F1'].GetFieldText('Manufacturer') == 'Littelfuse'
# Internal I2C FRAM: fixed 7-bit address 0x50, writes enabled, local bypass.
assert lower_fp['U9'].GetValue() == 'FM24CL64B-GTR'
assert lower_fp['U9'].GetFieldText('MPN') == 'FM24CL64B-GTR'
assert lower_fp['U9'].GetFPIDAsString() == 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'
assert lower_nets('U9') == {'1': 'GND', '2': 'GND', '3': 'GND', '4': 'GND',
                            '5': 'I2C_SDA', '6': 'I2C_SCL', '7': 'GND', '8': '+3V3'}
assert lower_nets('C14') == {'1': '+3V3', '2': 'GND'}
assert lower_fp['C14'].GetValue() == '100nF'
assert lower_fp['C14'].GetFPIDAsString() == 'RelayBoard:C_0805_2012Metric'
fram_vdd = next(pad for pad in lower_fp['U9'].Pads() if pad.GetNumber() == '8')
fram_cap = next(pad for pad in lower_fp['C14'].Pads() if pad.GetNumber() == '1')
assert math.hypot(fram_vdd.GetPosition().x - fram_cap.GetPosition().x,
                  fram_vdd.GetPosition().y - fram_cap.GetPosition().y) <= p.FromMM(5)
for ref in ('C1', 'C11', 'C12'):
    assert lower_nets(ref) == {'1': '+12V_SYS', '2': 'GND'}
    assert lower_fp[ref].GetValue() == '100u / 35V'
    assert lower_fp[ref].GetFieldText('MPN') == '350ARHA101M06X8P00'
    assert lower_fp[ref].GetFieldText('Height_Max') == '9 mm'
assert lower_nets('C8') == {'1': '+12V_LOGIC', '2': 'GND'}
assert lower_fp['C8'].GetValue() == '220u / 35V'
assert lower_nets('D3') == {'1': '+12V_LOGIC_RAW', '2': '+12V_SYS'}
assert lower_nets('R12') == {'1': '+12V_LOGIC_RAW', '2': '+12V_LOGIC'}
assert lower_fp['R12'].GetValue() == '1R / 2W pulse'
assert lower_fp['R12'].GetFieldText('MPN') == 'CRM2512-FX-1R00ELF'
assert lower_fp['R12'].GetFieldText('Manufacturer') == 'Bourns'
assert lower_fp['R12'].GetFieldText('Tolerance') == '1%'
assert lower_fp['R12'].GetFPIDAsString() == 'RelayBoard:R_2512_6332Metric'
assert lower_nets('C13') == {'1': '+12V_LOGIC', '2': 'GND'}
assert lower_fp['C13'].GetValue() == component_spec('Lower', 'C13')['value']
assert lower_fp['C13'].GetFieldText('Voltage') == '50 V'
assert lower_fp['C13'].GetFieldText('Dielectric') == 'X7R'
assert lower_fp['C13'].GetFPIDAsString() == 'RelayBoard:C_0805_2012Metric'
# The RAW net has only the diode cathode and the resistor input.
# A filled-copper/native clearance check is still required to rule out a bypass.
raw_pins={(f.GetReference(),pad.GetNumber()) for f in lower_fp.values() for pad in f.Pads()
          if pad.GetNetname().removeprefix('/')=='+12V_LOGIC_RAW'}
assert raw_pins=={('D3','1'),('R12','1')}
for ref in ('J43', 'J44'):
    assert lower_fp[ref].GetFieldText('MPN') == 'SSW-103-01-L-D'
    supply = 'GND' if ref == 'J43' else '+12V_LOGIC'
    assert lower_nets(ref)['3'] == lower_nets(ref)['4'] == supply

# SOIC-28 physical pin numbers, not symbol display order. GPA7 and GPB7
# are output-only on MCP23017; both already drive relay channels here.
mcp_pin_names = {**{str(i + 1): f'GPB{i}' for i in range(8)},
                 **{str(i + 21): f'GPA{i}' for i in range(8)}}
for ref, offset in [('U5', 0), ('U6', 8)]:
    connections = lower_nets(ref)
    for i in range(7):
        assert connections[str(i + 1)] == f'IN{offset + i + 1}'
        assert connections[str(i + 22)] == f'DRV{offset + i + 1}'
    assert connections['21'] == f'IN{offset + 8}'
    assert connections['8'] == f'DRV{offset + 8}'
    assert connections['28'] == f'DRV{offset + 7}'
    assert all(not connections[pin].startswith('IN') for pin in ('8', '28'))

def nets(ref):
    return {s.GetNumber(): s.GetNetname().removeprefix('/') for s in fp[ref].Pads() if s.GetNumber()}


for ref, mpn, input_net, output_net, ground in [
        ('U3', 'R-78K3.3-1.0', '+12V_LOGIC', '+3V3', 'GND'),
        ('U5', 'R-78K3.3-0.5', '+5V_ISO', '+3V3_ISO', 'GND_ISO'),
        ('U12', 'R-78K3.3-0.5', '+12V_LOGIC', '+3V3_RS485', 'GND'),
        ('U17', 'R-78E5.0-1.0', '+12V_LOGIC', '+5V_TMR', 'GND')]:
    assert fp[ref].GetValue() == mpn and fp[ref].GetFieldText('MPN') == mpn
    assert nets(ref) == {'1': input_net, '2': ground, '3': output_net}
    assert all(pad.GetAttribute() == p.PAD_ATTRIB_PTH for pad in fp[ref].Pads())
for ref in ('L1', 'D8', 'C2', 'C30', 'C31', 'C32', 'R41', 'R42', 'R43', 'R44', 'R45'):
    assert ref not in fp, (ref, 'obsolete TPS54231 component')
assert nets('J1') == {'1':'GND', '2':'GND', '3':'GND', '4':'GND', '5':'I2C_SDA', '6':'I2C_SCL'}
assert len(fp) == 164
assert fp['U17'].GetFPIDAsString() == 'RelayStack:RECOM_R-78E_PSE'
assert fp['U17'].GetFieldText('Manufacturer') == 'RECOM'
assert fp['U17'].GetFieldText('OutputCurrent') == '1 A'
for ref in ('C54', 'C55'):
    assert nets(ref) == {'1': '+12V_LOGIC', '2': 'GND'}
assert nets('C56') == nets('C11') == {'1': '+5V_TMR', '2': 'GND'}
assert all(pad.GetNetname().removeprefix('/') != 'MOD_VBUS' for part in fp.values() for pad in part.Pads())
assert nets('J6')['3'] == nets('J6')['4'] == '+12V_LOGIC'
assert nets('U4')['2'] == '+5V_TMR'

ports = [('J3', 1, 39, '32'), ('J3', 2, 40, '33'), ('J3', 3, 17, '10'),
         ('J3', 4, 18, '11'), ('J3', 5, 1, '39'), ('J3', 6, 2, '38'),
         ('J3', 7, 38, '31'), ('J3', 8, 44, '36')]
cpu = nets('U1')
assert nets('J3') == {**{str(i): f'DATA{i}_ISO' for i in range(1, 9)},
                      '9': '+5V_ISO', '10': 'GND_ISO'}
assert 'KF128-2.54-10P' in fp['J3'].GetFPIDAsString()
assert all(ref not in fp for ref in ('J4', 'J10', 'J11'))
for ref, number, gpio, cpu_pad in ports:
    assert nets(ref)[str(number)] == f'DATA{number}_ISO', (ref, nets(ref))
    assert cpu[cpu_pad] == f'DATA{number}_CPU', (ref, cpu_pad, cpu[cpu_pad])
assert nets('J5') == {'1': '+3V3_ISO', '2': 'SDA_ISO', '3': 'SCL_ISO', '4': 'GND_ISO'}
assert cpu['34'] == 'ISO_SDA_CPU' and cpu['35'] == 'ISO_SCL_CPU'
assert nets('J8') == {'1': '+5V_ISO', '2': 'RS485_A', '3': 'RS485_B', '4': 'GND_ISO'}
assert 'KF128-2.54-4P' in fp['J8'].GetFPIDAsString()
assert cpu['12'] == 'RS485_TX_CPU'   # GPIO8, not reserved PSRAM pins35-37
assert cpu['24'] == 'RS485_RX_CPU'   # GPIO47
assert cpu['25'] == 'RS485_DIR_CPU'  # GPIO48
assert fp['U11'].GetFieldText('MPN') == 'ADM2687EBRIZ'
assert '7.5x12.75mm_P1.27mm' in fp['U11'].GetFPIDAsString()
assert nets('U11') == {
    '1': 'GND', '2': '+3V3_RS485', '3': 'RS485_RX_RAW', '4': 'RS485_DIR',
    '5': 'RS485_DIR', '6': 'RS485_TX', '7': '+3V3_RS485', '8': 'GND',
    '9': 'GND_ISO', '10': 'RS485_VISO_OUT', '11': 'RS485_A', '12': 'RS485_B',
    '13': 'RS485_B', '14': 'RS485_A', '15': 'RS485_VISO', '16': 'GND_ISO'}
assert fp['U12'].GetFieldText('MPN') == 'R-78K3.3-0.5'
assert nets('U12') == {'1': '+12V_LOGIC', '2': 'GND', '3': '+3V3_RS485'}
# R57 is now the DATA7 4.3k pullup, not the abandoned VIN zero-ohm bridge.
assert len(fp) == 164

# iButton panel: direct CPU GPIO, bare LED current limit and protected 12 V.
assert cpu['37'] == 'IB_LED_CPU' and cpu['26'] == 'IB_BUZZ_CPU'
assert cpu['15'] == 'unconnected-(U1-IO3-Pad15)'
assert nets('J9') == {'1':'IB_LED_OUT','2':'IB_BUZZ_OUT','3':'+12V_PANEL'}
# The rear edge is inaccessible inside the enclosure: panel wires exit forward.
assert fp['J9'].GetLayer() == p.F_Cu and abs(fp['J9'].GetOrientationDegrees()) < 1e-6
assert abs(fp['J9'].GetPosition().y - fp['J3'].GetPosition().y) <= p.FromMM(0.01)
assert abs(fp['J9'].GetPosition().y - p.FromMM(118.0)) <= p.FromMM(0.01)
assert fp['U2'].GetPosition().x < fp['J9'].GetPosition().x < fp['J3'].GetPosition().x
assert fp['U16'].GetFieldText('MPN') == 'ULN2001D1013TR'
assert nets('U16') == {**{str(i):'GND' for i in [1,2,3,4,5,8]},
    **{str(17-i):f'unconnected-(U16-OUT{i}-Pad{17-i})' for i in range(1,6)},
    '7':'IB_LED_BASE','6':'IB_BUZZ_BASE','9':'+12V_PANEL','11':'IB_BUZZ_OUT','10':'IB_LED_SINK'}
for ref,value,a,z in [('R71','680R','IB_LED_CPU','IB_LED_BASE'),('R72','680R','IB_BUZZ_CPU','IB_BUZZ_BASE'),
                       ('R73','10k','IB_LED_CPU','GND'),('R74','10k','IB_BUZZ_BASE','GND'),('R75','1k / 0.5W','IB_LED_OUT','IB_LED_SINK')]:
    assert fp[ref].GetValue() == value and nets(ref) == {'1':a,'2':z}
assert nets('F2') == {'1':'+12V_LOGIC','2':'IB_12V_FUSED'}
assert nets('D11') == {'1':'+12V_PANEL','2':'IB_12V_FUSED'}
assert nets('D12') == {'1':'+12V_PANEL','2':'GND'}
for ref in ('C52','C53'):
    assert nets(ref) == {'1':'+12V_PANEL','2':'GND'}

assert '/+12V_RS485' not in upper.GetNetsByName()
assert not any(pad.GetNetname().removeprefix('/') == '+12V_RS485'
               for f in fp.values() for pad in f.Pads())
assert nets('FB1') == {'1': 'RS485_VISO_OUT', '2': 'RS485_VISO'}
assert fp['FB1'].GetFieldText('MPN') == 'BLM21PG221SN1D'
assert nets('D9') == {'1': 'RS485_A', '2': 'RS485_B', '3': 'GND_ISO'}
assert fp['D9'].GetFieldText('MPN') == 'CDSOT23-SM712'
assert nets('R53') == {'1': 'RS485_A', '2': 'RS485_TERM'}
assert fp['R53'].GetValue() == '120R 0.25W'
assert 'R_1206' in fp['R53'].GetFPIDAsString()
assert nets('JP2') == {'1': 'RS485_TERM', '2': 'RS485_B'}
for ref in ('U13', 'U14'):
    assert fp[ref].GetFieldText('MPN') == '74LVC125AD,118'
    assert fp[ref].GetFieldText('Manufacturer') == 'Nexperia'
    assert fp[ref].GetFPIDAsString() == 'Package_SO:SOIC-14_3.9x8.7mm_P1.27mm'
assert nets('U13') == {'1': '+3V3_RS485', '2': 'GND', '3': 'unconnected-(U13-1Y-Pad3)', '4': 'GND', '5': 'GND', '6': 'unconnected-(U13-2Y-Pad6)', '7': 'GND', '8': 'RS485_DIR_BUF', '9': 'RS485_DIR_CPU', '10': 'GND', '11': 'RS485_TX_BUF', '12': 'RS485_TX_CPU', '13': 'GND', '14': '+3V3_RS485'}
assert nets('U14') == {
    '1':'GND', '2':'RS485_RX_RAW', '3':'RS485_RX_BUF', '4':'+3V3', '5':'GND',
    '6':'unconnected-(U14-2Y-Pad6)', '7':'GND', '8':'unconnected-(U14-3Y-Pad8)',
    '9':'GND', '10':'+3V3', '11':'unconnected-(U14-4Y-Pad11)', '12':'GND',
    '13':'+3V3', '14':'+3V3'}
for ref, value, a, b in [
        ('R47','22R','RS485_TX_BUF','RS485_TX'),
        ('R48','22R','RS485_DIR_BUF','RS485_DIR'),
        ('R49','22R','RS485_RX_BUF','RS485_RX_CPU'),
        ('R50','47k','+3V3','RS485_TX_CPU'),
        ('R51','10k','RS485_DIR_CPU','GND'),
        ('R52','10k','RS485_RX_CPU','+3V3'),
        ('R54','47k','+3V3_RS485','RS485_TX'),
        ('R55','47k','RS485_DIR','GND'),
        ('R56','47k','+3V3_RS485','RS485_RX_RAW')]:
    assert nets(ref) == {'1': a, '2': b}
    assert fp[ref].GetValue() == value and fp[ref].GetFieldText('Tolerance') == '1%'
for ref, value, power, ground in [
        ('C37','22uF 35V X5R','+12V_LOGIC','GND'), ('C38','10uF','+3V3_RS485','GND'),
        ('C39','100nF','+3V3_RS485','GND'), ('C40','100nF','+3V3_RS485','GND'),
        ('C41','10uF','RS485_VISO_OUT','GND_ISO'), ('C42','100nF','RS485_VISO_OUT','GND_ISO'),
        ('C43','100nF','RS485_VISO','GND_ISO'), ('C44','10nF','RS485_VISO','GND_ISO'),
        ('C45','10nF','+3V3_RS485','GND'), ('C46','100nF','+3V3_RS485','GND'),
        ('C47','100nF','+3V3','GND')]:
    assert nets(ref) == {'1': power, '2': ground} and fp[ref].GetValue() == expected_value(ref, value)
for ref, mpn, tolerance in [('C37','C3216X5R1V226M160AC','20%'),
                            ('C38',TDK_10UF_MPN,'10%')]:
    assert fp[ref].GetFieldText('MPN') == mpn
    assert fp[ref].GetFieldText('Tolerance') == tolerance
    assert fp[ref].GetFPIDAsString() == 'Capacitor_SMD:C_1206_3216Metric'
assert '+3V3_ISO' not in nets('U11').values()
assert fp['U10'].GetValue() == 'DS3231MZ+'
assert fp['U10'].GetFPIDAsString() == 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'
assert fp['U10'].GetLayer() == p.B_Cu and fp['BT1'].GetLayer() == p.B_Cu
assert nets('U10') == {'1':'unconnected-(U10-32KHZ-Pad1)', '2':'RTC_VCC',
                       '3':'unconnected-(U10-INT{slash}SQW-Pad3)', '4':'unconnected-(U10-RST-Pad4)',
                       '5':'GND', '6':'RTC_VBAT', '7':'I2C_SDA', '8':'I2C_SCL'}
assert nets('BT1') == {'1':'RTC_VBAT', '2':'GND'}
assert 'BatteryHolder_QJ_CR1220-2_C70381' in fp['BT1'].GetFPIDAsString()
assert fp['BT1'].GetFieldText('SupplierPartNumber') == 'C70381'
holder_holes = [s for s in fp['BT1'].Pads() if s.GetAttribute() == p.PAD_ATTRIB_NPTH]
assert len(holder_holes) == 2
assert all(s.GetDrillSize().x == p.FromMM(1.2) and s.GetDrillSize().y == p.FromMM(1.2)
           for s in holder_holes)
assert cpu['4'] == 'I2C_SDA' and cpu['5'] == 'I2C_SCL'
assert nets('R46') == {'1':'+3V3', '2':'RTC_VCC'}
assert fp['R46'].GetValue() == '470R' and fp['R46'].GetFieldText('Tolerance') == '1%'
assert nets('C34') == nets('C36') == {'1':'RTC_VCC', '2':'GND'}
assert fp['C34'].GetValue() == '100nF'
assert fp['C36'].GetFieldText('MPN') == 'C3216X5R1V226M160AC'
assert nets('C35') == {'1':'RTC_VBAT', '2':'GND'} and fp['C35'].GetValue() == '1nF C0G'
assert {(f.GetReference(),s.GetNumber()) for f in fp.values() for s in f.Pads()
        if s.GetNetname() == '/RTC_VBAT'} == {('BT1','1'),('U10','6'),('C35','1')}
for ref, a, b in [('U6', 1, 2), ('U8', 3, 4), ('U9', 5, 6), ('U15', 7, 8)]:
    expected = {'1': '+3V3', '2': f'DATA{a}_CPU', '3': f'DATA{b}_CPU', '4': 'GND',
                '5': 'GND_ISO', '6': f'DATA{b}_IC_ISO', '7': f'DATA{a}_IC_ISO', '8': '+5V_ISO'}
    assert nets(ref) == expected, (ref, nets(ref))
assert nets('U7') == {'1': '+3V3', '2': 'ISO_SDA_CPU', '3': 'ISO_SCL_CPU', '4': 'GND',
                      '5': 'GND_ISO', '6': 'SCL_IC_ISO', '7': 'SDA_IC_ISO', '8': '+3V3_ISO'}
assert sum(f.GetValue() == 'ISO1640BDR' for f in fp.values()) == 5
for ref in ('U6', 'U7', 'U8', 'U9', 'U15'):
    assert fp[ref].GetValue() == 'ISO1640BDR'
    assert fp[ref].GetFPIDAsString() == 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'
    assert fp[ref].GetFieldText('MPN') == 'ISO1640BDR'
for ref in ('R15', 'R16', 'R19', 'R20', 'R33', 'R34', 'R37', 'R38', 'R57', 'R58'):
    assert fp[ref].GetValue() == '4.3k'
    assert fp[ref].GetFieldText('Tolerance') == '1%'
for ref in ('R17', 'R18', 'R21', 'R22', 'R35', 'R36', 'R39', 'R40', 'R59', 'R60'):
    assert fp[ref].GetValue() == '4.7k'
    assert fp[ref].GetFieldText('Tolerance') == '1%'
# DATA7/8 add exactly one ordinary two-channel ISO1640 circuit.
for ref, rail, data in [('R57','+3V3','DATA7_CPU'),('R58','+3V3','DATA8_CPU'),
                       ('R59','+5V_ISO','DATA7_IC_ISO'),('R60','+5V_ISO','DATA8_IC_ISO')]:
    assert nets(ref) == {'1':rail,'2':data}
    assert 'R_0805' in fp[ref].GetFPIDAsString()
for ref, value, rail, ground in [('C48','100nF','+3V3','GND'),('C49','1nF','+3V3','GND'),
                                ('C50','100nF','+5V_ISO','GND_ISO'),('C51','1nF','+5V_ISO','GND_ISO')]:
    assert nets(ref) == {'1':rail,'2':ground} and fp[ref].GetValue()==expected_value(ref, value)
    package = fp[ref].GetFPIDAsString()
    assert 'C_0805' in package or (ref == 'C50' and package == 'RelayStack:C0805_C50_Clearance')
# SRDA pin ordering, floating references and FIELD-only 100R resistors.
from srda_contract import check_srda_contract
srda_errors = check_srda_contract(set(fp), nets, lambda r: fp[r].GetValue(),
    lambda r, k: fp[r].GetFieldText(k), lambda r: fp[r].GetFPIDAsString(), inventory_count=164)
assert not srda_errors, srda_errors
# GPIO44 is the default UART0 RX pad, assigned exclusively to DATA8 here.
assert cpu['36'] == 'DATA8_CPU'
assert cpu['13'] == 'USB_DN_CPU' and cpu['14'] == 'USB_DP_CPU'
assert 'HBXINTAO16PIN_DIP_Vertical' in fp['J2'].GetFPIDAsString()
usb_pads = list(fp['J2'].Pads())
assert len(usb_pads) == 20
assert all(s.GetAttribute() == p.PAD_ATTRIB_PTH for s in usb_pads), 'USB-C must have no SMD pads'
assert nets('J2') == {'A1': 'GND', 'A12': 'GND', 'B1': 'GND', 'B12': 'GND', 'SH': 'GND',
                      'A4': 'USB_VBUS', 'A9': 'USB_VBUS', 'B4': 'USB_VBUS', 'B9': 'USB_VBUS',
                      'A5': 'USB_CC1', 'B5': 'USB_CC2', 'A6': 'USB_DP', 'B6': 'USB_DP',
                      'A7': 'USB_DN', 'B7': 'USB_DN',
                      'A8': 'unconnected-(J2-SBU1-PadA8)',
                      'B8': 'unconnected-(J2-SBU2-PadB8)'}
assert all('TS-1088' in fp[ref].GetFPIDAsString() for ref in ('SW1', 'SW2'))
for k, board in boards.items():
    assert board.GetCopperLayerCount() == 2
    for pad in (s for f in board.GetFootprints() for s in f.Pads()):
        size = pad.GetDrillSize()
        if size.x and size.y:
            assert min(size.x, size.y) >= p.FromMM(.3), (k, pad.GetParent().GetReference(), pad.GetNumber(), size)
for low, up in [('J43', 'J1'), ('J44', 'J6')]:
    lower_fp = next(f for f in boards['Lower'].GetFootprints() if f.GetReference() == low)
    def signature(f):
        return {s.GetNumber(): (s.GetPosition().x, s.GetPosition().y, s.GetNetname()) for s in f.Pads()}
    assert signature(lower_fp) == signature(fp[up])

geometry = {}
for k, board in boards.items():
    layers = defaultdict(list)
    lengths = defaultdict(float)
    widths = []
    for t in board.GetTracks():
        if isinstance(t, p.PCB_VIA):
            assert t.GetDrillValue() >= p.FromMM(0.3), (k, 'via drill below factory limit')
            assert t.GetWidth(p.F_Cu)-t.GetDrillValue() >= p.FromMM(0.3), (k, 'via annulus below 0.15 mm')
            continue
        a, b = t.GetStart(), t.GetEnd()
        dx, dy = abs(a.x-b.x), abs(a.y-b.y)
        if k == 'Upper':
            minimum_width = .175 if str(t.GetNetname()) in {'/ETH_CS_N','/ETH_SCK','/ETH_MOSI','/ETH_MISO'} else .18
            assert t.GetWidth() >= p.FromMM(minimum_width), (t.GetNetname(), 'track below documented signal-class width')
        widths.append(p.ToMM(t.GetWidth()))
        assert dx <= 20 or dy <= 20 or abs(dx-dy) <= 20, (k, t.GetNetname(), a, b)
        layers[t.GetLayer()].append((a.x, a.y, b.x, b.y, t.GetNetname()))
        lengths[t.GetNetname()] += math.hypot(dx,dy) / 1e6
    def orient(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    crossings = []
    for layer, segments in layers.items():
        for i, s in enumerate(segments):
            a,b = s[:2],s[2:4]
            for t in segments[i+1:]:
                c,d = t[:2],t[2:4]
                if orient(a,b,c)*orient(a,b,d)<0 and orient(c,d,a)*orient(c,d,b)<0:
                    crossings.append((board.GetLayerName(layer),s,t))
    assert not crossings, (k, crossings[:5])
    geometry[k] = {'copper_layers': board.GetCopperLayerCount(), 'footprints': len(board.GetFootprints()),
                   'non_45_90_segments': 0, 'strict_track_crossings': 0,
                   'minimum_track_width_mm': min(widths),
                   'usb_trace_lengths_mm': {n: round(v,3) for n,v in lengths.items() if n.startswith('/USB_D')}}
result = {'data_ports': [{'connector': ref, 'gpio': gpio, 'port': number} for ref,number,gpio,_ in ports],
          'i2c_gpio': [41,42], 'uart0_rx_gpio44_reserved_for_DATA8': True, 'bidirectional_isolators': 5, 'matched_stack_contacts': 12, 'geometry': geometry,
          'ibutton_panel': {'LED_gpio':43, 'BUZZER_gpio':45, 'GPIO3_NC':True,
                            'J9_location':'exposed lower/front edge between Ethernet and DATA',
                            'J9_position_mm':[p.ToMM(fp['J9'].GetPosition().x),p.ToMM(fp['J9'].GetPosition().y)],
                            'wire_entry':'+Y, aligned with J3/J8/J5',
                            'ROM_UART_LED_possible_until_GPIO_initialization':True},
          'mcp23017': {'physical_gpio_pin_names': mcp_pin_names,
                      'output_only_pins': ['GPA7', 'GPB7'],
                      'input_mask_hex': '0x7f01', 'relay_mask_hex': '0x80fe',
                      'internal_pullup_mask_hex': '0x0000',
                      'existing_gpio_wiring_preserved': True},
          'input_optocouplers': {'mpn': 'TLP2363(TPL,E', 'count': 16,
                                'input_resistor': '1.2k + 220R; 1% 0.5W0805',
                                'input_pre_filter': '220R / 1uF; TVS on terminal DI',
                                'input_LED_shunt': '4.7k in parallel with LED',
                                'output_pullup': '10k on RAW',
                                'output_filter': '470R / 100nF',
                                'local_bypass': '100nF each',
                                'bypass_pad_distance_mm': tlp_bypass_distance_mm},
          'power': {'Upper.U3': 'R-78K3.3-1.0 / +12V_LOGIC',
                    'Upper.U5': 'R-78K3.3-0.5 / +5V_ISO',
                    'Upper.U12': 'R-78K3.3-0.5 / +12V_LOGIC',
                    'Lower.U2': 'R-78K3.3-0.5 / +12V_LOGIC; FB1 to local +3V3',
                    'Upper.U17': 'R-78E5.0-1.0 / +12V_LOGIC to local +5V_TMR',
                    'left_stack_pins3_4': 'GND', 'left_stack_supply_v': 0, 'right_stack_supply_v': 12,
                    'Lower.F1': 'Littelfuse 045201.5MRL / 1.5A Slo-Blo'},
          'rs485': {'mpn': 'ADM2687EBRIZ', 'uart': 1, 'tx_gpio': 8, 'rx_gpio': 47,
                    'direction_gpio': 48, 'half_duplex': True,
                    'connector': 'J8', 'pin_order': ['5V_ISO','A','B','GND_ISO'],
                    'buffers': '2x Nexperia 74LVC125AD,118; Ioff',
                    'primary_supply': 'U12 / +12V_LOGIC to +3V3_RS485',
                    'field_power_from_TMR': True, 'isoPower_output_not_paralleled': True,
                    'sensor_ports_share_GND_ISO': True, 'switchable_120ohm_termination': True},
          'rtc': {'mpn':'DS3231MZ+', 'i2c_address':'0x68', 'cpu_gpio':[4,5],
                  'holder':'Q&J CR1220-2 / C70381', 'board':'Upper', 'side':'B.Cu',
                  'additional_gpio':0, 'external_charger':False}}
print(json.dumps(result,ensure_ascii=False,indent=2))
