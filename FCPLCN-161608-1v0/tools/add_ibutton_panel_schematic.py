"""Add two ULN2001 panel outputs while preserving all existing schematic blocks."""
from pathlib import Path
import argparse
import re
from schematic import Schematic, Pin, rectangle, polyline
from add_lower_fram_schematic import expression_end


def migrate_gpio43(path, original):
    """Use the available UART0 TX pin for the indicator; preserve GPIO3 as NC."""
    if '(label "IB_LED_CPU" (at 91.44 81.28' in original:
        return
    for prefix in ('(wire (pts (xy 50.8 62.23) (xy 45.72 62.23))',
                   '(label "IB_LED_CPU" (at 45.72 62.23'):
        start=original.index(prefix)
        end=expression_end(original,start)
        original=original[:start]+original[end:]
    original,n=re.subn(r'\(no_connect \(at 86\.36 81\.28\) \(uuid "[^"]+"\)\)','',original)
    assert n==1,n
    s=Schematic(path.stem,namespace='RelayStack',uuid_seed='FCPLCn/iButton-GPIO43-v1')
    s.root='"'+re.search(r'\(uuid "([^\"]+)"\)',original).group(1)+'"'
    s.wire((86.36,81.28),(91.44,81.28))
    s.label('IB_LED_CPU',(91.44,81.28),angle=0,size=1.03)
    old_nc='(no_connect (at 50.8 62.23) (uuid "6232113c-bb1f-588d-852d-27e3b12f0878"))'
    original=original.rstrip()[:-1]+'\n'+old_nc+'\n'+'\n'.join(s.elements)+'\n)\n'
    original=original.replace('GPIO3 LED / GPIO45 BUZZER: HIGH = ON; 10k pull-downs ensure LOW on reset. Default eFuses required.',
      'GPIO43 LED / GPIO45 BUZZER: HIGH = ON. GPIO43 is ROM UART TX; firmware must configure it as GPIO.')
    original=original.replace('Panel 12V is nominal; allow approximately 8.5-12V across buzzer including rail and Darlington drops.',
      'Panel 12V is nominal; approximately 8.5-9V across buzzer at full design load including series drops.')
    path.write_text(original)


def migrate_driver_channels(path):
    """Use adjacent channels 7/6 near the terminal, preserving the circuit."""
    original = path.read_text()
    if '(label "IB_LED_BASE" (at 304.8 693.42' in original:
        assert '(label "IB_BUZZ_BASE" (at 304.8 690.88' in original
        return
    for before, after in [
        ('(label "IB_LED_BASE" (at 304.8 678.18', '(label "GND" (at 304.8 678.18'),
        ('(label "IB_BUZZ_BASE" (at 304.8 680.72', '(label "GND" (at 304.8 680.72'),
        ('(label "GND" (at 304.8 690.88', '(label "IB_BUZZ_BASE" (at 304.8 690.88'),
        ('(label "GND" (at 304.8 693.42', '(label "IB_LED_BASE" (at 304.8 693.42'),
    ]:
        assert original.count(before) == 1, before
        original = original.replace(before, after)
    for prefix in (
        '(no_connect (at 347.98 693.42)', '(no_connect (at 347.98 690.88)',
        '(wire (pts (xy 347.98 680.72) (xy 355.6 680.72))',
        '(label "IB_BUZZ_OUT" (at 355.6 680.72',
        '(wire (pts (xy 347.98 678.18) (xy 355.6 678.18))',
        '(label "IB_LED_SINK" (at 355.6 678.18',
    ):
        start = original.index(prefix)
        end = expression_end(original, start)
        original = original[:start] + original[end:]
    s = Schematic(path.stem, namespace='RelayStack', uuid_seed='FCPLCn/iButton-channels-7-6-v1')
    s.root = '"' + re.search(r'\(uuid "([^\"]+)"\)', original).group(1) + '"'
    for y, net in ((693.42, 'IB_LED_SINK'), (690.88, 'IB_BUZZ_OUT')):
        s.wire((347.98, y), (355.6, y))
        s.label(net, (355.6, y), angle=0, size=1.03)
    for y in (678.18, 680.72):
        s.no_connect((347.98, y))
    path.write_text(original.rstrip()[:-1] + '\n' + '\n'.join(s.elements) + '\n)\n')


def migrate_buzzer_pulldown(path):
    """Pull down the buzzer base; the CPU sees 680R + 10k at reset."""
    text = path.read_text()
    before = '(label "IB_BUZZ_CPU" (at 163.83 688.34'
    after = '(label "IB_BUZZ_BASE" (at 163.83 688.34'
    if before not in text:
        assert after in text
        return
    assert text.count(before) == 1
    text = text.replace(before, after)
    note = 'GPIO43 LED / GPIO45 BUZZER: HIGH = ON. GPIO43 is ROM UART TX; firmware must configure it as GPIO.'
    assert text.count(note) == 1
    text = text.replace(note, note + ' GPIO45 reset pull-down: R72+R74=10.68k.')
    path.write_text(text)


def apply(root):
    folder = Path(root) / 'FCPLCN-CPU-08-1v0'
    path = folder / (folder.name + '.kicad_sch')
    lib = folder / 'RelayStack.kicad_sym'
    original = path.read_text()
    if '(property "Reference" "U16"' in original:
        assert 'ULN2001D1013TR' in original
        migrate_gpio43(path,original)
        migrate_driver_channels(path)
        migrate_buzzer_pulldown(path)
        return
    s = Schematic(folder.name, namespace='RelayStack', uuid_seed='FCPLCn/iButton-panel-v1')
    s.root = '"' + re.search(r'\(uuid "([^"]+)"\)', original).group(1) + '"'
    resistor = [Pin('1', '~', -3.81, 0), Pin('2', '~', 3.81, 0, 180)]
    for name in ('R', 'C', 'D_Schottky'):
        s.define(name, 'R' if name == 'R' else 'C' if name == 'C' else 'D', resistor, [])
    pins = [Pin(str(i), 'IN' + str(i), -17.78, (4-i)*2.54, 0, 'input') for i in range(1,8)]
    pins += [Pin(str(17-i), 'OUT' + str(i), 17.78, (4-i)*2.54, 180, 'open_collector') for i in range(1,8)]
    pins += [Pin('8', 'GND', -17.78, -12.7, 0, 'power_in'), Pin('9', 'COM', 17.78, -12.7, 180, 'passive')]
    s.define('ULN2001', 'U', pins, [rectangle((-15.24,-15.24),(15.24,12.7))],
             footprint='Package_SO:SOIC-16_3.9x9.9mm_P1.27mm',
             datasheet='https://www.st.com/resource/en/datasheet/uln2001.pdf',
             description='Seven Darlington low-side drivers; external input resistors; two used, five spare disabled')
    s.define('iButton-Panel', 'J', [Pin('1','LED-',-12.7,2.54),Pin('2','BUZZER-',-12.7,0),Pin('3','+12V',-12.7,-2.54)],
             [rectangle((-10.16,-5.08),(10.16,5.08))], footprint='RelayStack:KF128-2.54-3P')
    s.define('Panel-TVS', 'D', [Pin('1','K',-3.81,0),Pin('2','A',3.81,0,180)],
             [polyline((1.27,-1.27),(-1.27,0),(1.27,1.27),(1.27,-1.27)),polyline((-1.9,1.27),(-1.27,1.27),(-1.27,-1.27),(-.635,-1.27))],
             footprint='Diode_SMD:D_SMA',datasheet='https://www.littelfuse.com/assetdocs/tvs-diodes-smaj-datasheet?assetguid=13c2a823-03b8-4d1f-9ddc-9b44670aed9d')
    def connect(ref, nets):
        for num, net in nets.items():
            tail=s.pin(ref,num)
            if net is None:
                s.no_connect(tail)
            else:
                delta=-7.62 if tail[0] < positions[ref][0] else 7.62
                end=(round(tail[0]+delta,4),tail[1]);s.wire(tail,end);s.label(net,end,angle=180 if delta<0 else 0,size=1.03)
    positions={}
    def part(symbol,ref,xy,value,nets,footprint=None,fields=None):
        positions[ref]=xy
        fields = dict(fields or {}); ds = fields.pop('Datasheet', None)
        s.place(symbol,ref,xy,value=value,footprint=footprint,fields=fields,datasheet=ds,ref_at=(xy[0],xy[1]-(20 if symbol=='ULN2001' else 12 if symbol=='iButton-Panel' else 4)),value_at=(xy[0],xy[1]-(16 if symbol=='ULN2001' else 8) if symbol in ('ULN2001','iButton-Panel') else xy[1]+4))
        connect(ref,nets)
    s.text('iButton panel: bare LED and 12 V buzzer / two direct CPU GPIO', (14,640),size=2.05,bold=True)
    s.line((14,643),(578,643))
    part('ULN2001','U16',(330.2,685.8),'ULN2001D1013TR',
         {**{str(i):'GND' for i in [1,2,3,4,5,8]},**{str(i):None for i in range(12,17)},
          '7':'IB_LED_BASE','6':'IB_BUZZ_BASE','9':'+12V_PANEL','11':'IB_BUZZ_OUT','10':'IB_LED_SINK'},
         fields={'MPN':'ULN2001D1013TR','Manufacturer':'STMicroelectronics','Height_Max':'1.75 mm'})
    part('iButton-Panel','J9',(530.86,665.48),'iButton LED / BUZZER / +12V',
         {'1':'IB_LED_OUT','2':'IB_BUZZ_OUT','3':'+12V_PANEL'},
         fields={'MPN':'KF128-2.54-3P','Manufacturer':'Cixi Kefa','Pitch':'2.54 mm'})
    res='Resistor_SMD:R_0805_2012Metric';cap='Capacitor_SMD:C_0805_2012Metric'
    for ref,value,x,y,a,b in [('R71','680R',55.88,665.48,'IB_LED_CPU','IB_LED_BASE'),
                             ('R72','680R',55.88,688.34,'IB_BUZZ_CPU','IB_BUZZ_BASE'),
                             ('R73','10k',175.26,665.48,'IB_LED_CPU','GND'),
                             ('R74','10k',175.26,688.34,'IB_BUZZ_BASE','GND')]:
        part('R',ref,(x,y),value,{'1':a,'2':b},res,{'Tolerance':'1%','PowerRating':'0.125 W','BOMPackage':'0805','BOMGroup':f'R-0805-{value}-1pct-125mW'})
    part('R','R75',(447.04,688.34),'1k / 0.5W',{'1':'IB_LED_OUT','2':'IB_LED_SINK'},res,
         {'Datasheet':'https://industrial.panasonic.com/cdbs/www-data/pdf/RDO0000/AOA0000C331.pdf','MPN':'ERJ-P06F1001V','Manufacturer':'Panasonic','Tolerance':'1%','PowerRating':'0.5 W','BOMPackage':'0805','BOMGroup':'R-0805-1k-1pct-500mW-Panasonic'})
    part('R','F2',(55.88,726.44),'PTC 0.2A / 30V',{'1':'+12V_LOGIC','2':'IB_12V_FUSED'},'Fuse:Fuse_1206_3216Metric',
         {'MPN':'MF-NSMF020X-2','Manufacturer':'Bourns','Datasheet':'https://www.bourns.com/docs/product-datasheets/mf-nsmf.pdf'})
    part('D_Schottky','D11',(175.26,726.44),'SS14',{'1':'+12V_PANEL','2':'IB_12V_FUSED'},'Diode_SMD:D_SMA',
         {'Datasheet':'https://www.vishay.com/docs/88746/ss12.pdf','MPN':'SS14-E3/61T','Manufacturer':'Vishay'})
    part('C','C52',(292.1,726.44),'22uF / 35V',{'1':'+12V_PANEL','2':'GND'},'Capacitor_SMD:C_1206_3216Metric',
         {'MPN':'C3216X5R1V226M160AC','Manufacturer':'TDK','Voltage':'35 V','Dielectric':'X5R','Tolerance':'20%'})
    part('C','C53',(406.4,726.44),'100nF',{'1':'+12V_PANEL','2':'GND'},cap,
         {'Voltage':'50 V','Dielectric':'X7R','Tolerance':'10%','BOMPackage':'0805','BOMGroup':'C-0805-100nF-50V-X7R-10pct'})
    part('Panel-TVS','D12',(530.86,726.44),'SMAJ15A',{'1':'+12V_PANEL','2':'GND'},fields={'MPN':'SMAJ15A','Manufacturer':'Littelfuse'})
    s.text('GPIO43 LED / GPIO45 BUZZER: HIGH = ON. GPIO43 is ROM UART TX; firmware must configure it as GPIO. GPIO45 reset pull-down: R72+R74=10.68k.',(14,754),size=1.15)
    s.text('Bare LED: anode +12V_PANEL, cathode LED-. Buzzer: +12V_PANEL / BUZZER-. Design buzzer load <=100mA.',(14,762),size=1.15)
    s.text('Panel 12V is nominal; approximately 8.5-9V across buzzer at full design load including series drops.',(14,770),size=1.15)
    s.text('iButton socket DATA/GND_ISO must remain separate from LED/buzzer wiring and MAIN GND.',(14,778),size=1.15)
    # Replace only two no-connect flags, preserving every existing symbol and wire.
    for at,name in [((86.36,81.28),'IB_LED_CPU'),((86.36,66.04),'IB_BUZZ_CPU')]:
        pattern=r'\(no_connect \(at '+str(at[0])+r' '+str(at[1])+r'\) \(uuid "[^"]+"\)\)'
        original,n=re.subn(pattern,'',original)
        assert n == 1,(name,n)
        end=(round(at[0]+(-5.08 if at[0]<60 else 5.08),4),at[1]);s.wire(at,end);s.label(name,end,angle=180 if at[0]<60 else 0,size=1.03)
    defs=[s.definitions[n] for n in ('ULN2001','iButton-Panel','Panel-TVS')]
    end=expression_end(original,original.index('(lib_symbols'))
    original=original[:end-1]+'\n'+'\n'.join(d.sexpr('RelayStack') for d in defs)+'\n'+original[end-1:]
    result=original.rstrip()[:-1]+'\n'+'\n'.join(s.elements)+'\n)\n'
    result=result.replace('(paper "User" 594 630)','(paper "User" 594 800)')
    path.write_text(result)
    text=lib.read_text();lib.write_text(text.rstrip()[:-1]+'\n'+'\n'.join(d.sexpr() for d in defs)+'\n)\n')


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args();apply(args.project_root)
