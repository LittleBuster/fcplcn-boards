"""Apply the lower local-3V3 power revision without regenerating other circuits.

Preserves all existing component UUIDs except the removed U8. New FB1 UUID is
deterministic. PCB work remains separate. Re-running the completed edit is a no-op.
"""
from pathlib import Path
import json
import re
from add_lower_fram_schematic import expression_end
from board_paths import board_file, board_dir, board_name
from schematic import Schematic, Pin, rectangle, polyline, q, prop

ROOT=Path(__file__).resolve().parents[1]
KDS='https://recom-power.com/pdf/Innoline/R-78K-0.5.pdf'
MDS='https://www.murata.com/en-eu/api/pdfdownloadapi?cate=cgsubChipFerriBead&partno=BLM21PG221SN1D'

def sections(text, prefix):
    for m in re.finditer(re.escape(prefix),text):
        end=expression_end(text,m.start())
        yield m.start(),end,text[m.start():end]

def component(text,ref):
    matches=[x for x in sections(text,'(symbol (lib_id ')if '(property "Reference" '+q(ref)+' 'in x[2]]
    assert len(matches)==1,(ref,len(matches))
    return matches[0]

def replace_property(block,name,value):
    match=re.search(r'\(property '+re.escape(q(name))+r' "(?:\\.|[^"\\])*"',block)
    if match:
        return block[:match.start()]+'(property '+q(name)+' '+q(value)+block[match.end():]
    at=re.search(r'\(at ([^)]*)\)',block)[1].split()[:2]
    entry=prop(name,value,tuple(map(float,at)),hide=True)
    pos=block.index('(pin ')
    return block[:pos]+entry+' '+block[pos:]

def ensure_filtered_power_flag(path, library):
    text=path.read_text()
    if '(property "Reference" "#FLG3V3"' in text:
        return
    lib=library.read_text()
    root=re.search(r'\(uuid "([^\"]+)"',text)[1]
    sch=Schematic(board_name('Lower'),namespace='RelayBoard',uuid_seed='FCPLCN/lower-power-split-v1')
    sch.root=q(root)
    sch.define('Filtered_Power_Source','#FLG',[Pin('1','~',0,0,90,'power_out',0)],
        [polyline((0,0),(0,1.27),(-1.02,2.03),(0,2.79),(1.02,2.03),(0,1.27))],
        names=False,numbers=False,on_board=False)
    sch.place('Filtered_Power_Source','#FLG3V3',(474.98,129.54),hide_ref=True,hide_value=True)
    sch.wire((474.98,129.54),(474.98,134.62))
    sch.label('+3V3',(474.98,134.62),size=1.0)
    pos=text.index('(lib_symbols')+len('(lib_symbols')
    text=text[:pos]+'\n'+sch.definitions['Filtered_Power_Source'].sexpr('RelayBoard')+'\n'+text[pos:]
    text=text.rstrip()[:-1]+'\n'+'\n'.join(sch.elements)+'\n)\n'
    lib=lib.rstrip()[:-1]+'\n'+sch.definitions['Filtered_Power_Source'].sexpr()+'\n)\n'
    path.write_text(text);library.write_text(lib)

def edit():
    path=board_file(ROOT,'Lower','.kicad_sch');library=board_dir(ROOT,'Lower')/'RelayBoard.kicad_sym'
    text=path.read_text();lib=library.read_text()
    old_desc='pins 1/2 GND, 3/4 PWR (J43=5V, J44=12V), 5/6 signals'
    new_desc='pins1/2 GND; pins3/4: J43=GND, J44=12V_LOGIC; pins5/6 signals'
    text=text.replace(old_desc,new_desc).replace('Питание верхней платы приходит от нижней через J43/J44.','Защищённые 12 В верхней платы приходят через J44; J43 передаёт I²C и GND.')
    lib=lib.replace(old_desc,new_desc)
    path.write_text(text);library.write_text(lib)
    if '(property "Reference" "FB1"'in text:
        assert '(property "Reference" "U8"'not in text
        assert 'MOD_VBUS'not in text
        assert '(property "Value" "R-78K3.3-0.5"'in text
        ensure_filtered_power_flag(path,library)
        print('Lower power split already applied.');return
    assert text.count('(property "Reference" "U8"')==1
    root=re.search(r'\(uuid "([^\"]+)"',text)[1]
    # All old 5V nodes on Lower become the converter RAW3V3 output; the two
    # former power contacts are separately grounded below.
    text=text.replace('MOD_VBUS','+3V3_DCDC')
    start,end,u8=component(text,'U8')
    loc=list(map(float,re.search(r'\(at ([^)]*)\)',u8)[1].split()))
    assert loc==[414.02,129.54,0.0],loc
    tails={(402.59,129.54),(425.45,129.54),(402.59,134.62)}
    remove=[(start,end)];endpoints=set()
    for a,b,wire in sections(text,'(wire '):
        pts=[tuple(map(float,s.split()))for s in re.findall(r'\(xy ([^)]*)\)',wire)]
        if set(pts)&tails:
            assert len(pts)==2
            remove.append((a,b));endpoints.update(set(pts)-tails)
    assert len(remove)==4,remove
    for a,b,label in sections(text,'(label '):
        loc=tuple(map(float,re.search(r'\(at ([^)]*)\)',label)[1].split()[:2]))
        if loc in endpoints:remove.append((a,b))
    assert len(remove)==7,remove
    for a,b in sorted(remove,reverse=True):text=text[:a]+text[b:]
    # Replace the 3-pin supply symbol in both embedded and source libraries.
    text=text.replace('R-78E5.0-1.0','R-78K3.3-0.5').replace('RelayBoard:RECOM_R-78E_PSE','RelayBoard:RECOM_R-78K3.3-0.5_SIP3_P2.54mm').replace('https://recom-power.com/pdf/Innoline/R-78E-1.0.pdf',KDS)
    lib=lib.replace('R-78E5.0-1.0','R-78K3.3-0.5').replace('RelayBoard:RECOM_R-78E_PSE','RelayBoard:RECOM_R-78K3.3-0.5_SIP3_P2.54mm').replace('https://recom-power.com/pdf/Innoline/R-78E-1.0.pdf',KDS)
    a,b,u2=component(text,'U2')
    for name,value in [('MPN','R-78K3.3-0.5'),('Manufacturer','RECOM'),('InputVoltage','4.5–36 V'),('OutputCurrent','0.5 A')]:u2=replace_property(u2,name,value)
    text=text[:a]+u2+text[b:]
    # Left header3/4 label endpoints are those connected to its two PWR pins.
    _,_,j43=component(text,'J43');at=list(map(float,re.search(r'\(at ([^)]*)\)',j43)[1].split()))
    assert at==[69.85,137.16,0.0],at
    contact_tails={(57.15,137.16),(82.55,137.16)};ends=set()
    for _,_,wire in sections(text,'(wire '):
        pts=[tuple(map(float,s.split()))for s in re.findall(r'\(xy ([^)]*)\)',wire)]
        if set(pts)&contact_tails:ends.update(set(pts)-contact_tails)
    edits=[]
    for a,b,label in sections(text,'(label '):
        loc=tuple(map(float,re.search(r'\(at ([^)]*)\)',label)[1].split()[:2]))
        if loc in ends:
            assert label.startswith('(label "+3V3_DCDC"'),label
            edits.append((a,b,label.replace('(label "+3V3_DCDC"','(label "GND"',1)))
    assert len(edits)==2,edits
    for a,b,new in sorted(edits,reverse=True):text=text[:a]+new+text[b:]
    text=text.replace('Питание верхней платы и U8 подаётся постоянно от выхода 5 В.','U2: локальные 3,3 В от +12V_LOGIC. Верхние 5 В формируются на CPU-плате.')
    text=text.replace('11    Питание 3,3 В для MCP23017','11    Фильтр локальных 3,3 В · FB1 / C7')
    text=text.replace('J43: контакты 3/4 = 5 В; J44: контакты 3/4 = +12V_LOGIC.','J43: контакты 1–4 = GND, 5/6 = I²C; J44: контакты 3/4 = +12V_LOGIC.')
    # The new ferrite replaces the removed regulator in the same logical block.
    sch=Schematic(board_name('Lower'),namespace='RelayBoard',uuid_seed='FCPLCN/lower-power-split-v1')
    sch.root=q(root)
    sch.define('Power_Ferrite_Bead','FB',[Pin('1','~',-10.16,0,0),Pin('2','~',10.16,0,180)],
        [rectangle((-5.08,-1.52),(5.08,1.52),fill='none'),polyline((-3.81,-2.54),(3.81,2.54))],
        names=False,footprint='RelayBoard:L_0805_PowerFilter',datasheet=MDS)
    sch.place('Power_Ferrite_Bead','FB1',(414.02,129.54),value='220R @100MHz / 2A',
        ref_at=(414.02,121.92),value_at=(414.02,124.46),fields={'MPN':'BLM21PG221SN1D','Manufacturer':'Murata'})
    for pin,net,delta in [('1','+3V3_DCDC',-7.62),('2','+3V3',7.62)]:
        at=sch.pin('FB1',pin);end=(round(at[0]+delta,4),at[1]);sch.wire(at,end);sch.label(net,end,angle=180 if delta<0 else 0,size=1.17)
    sch.text('FB1: низкое DCR; C3/C6 до фильтра, C7 и локальные 100 нФ после фильтра.',(370.84,151.13),size=1.03)
    definitions='\n'.join(d.sexpr('RelayBoard')for d in sch.definitions.values())
    pos=text.index('(lib_symbols')+len('(lib_symbols');text=text[:pos]+'\n'+definitions+'\n'+text[pos:]
    assert text.rstrip().endswith(')');text=text.rstrip()[:-1]+'\n'+'\n'.join(sch.elements)+'\n)\n'
    lib=lib.rstrip()[:-1]+'\n'+'\n'.join(d.sexpr()for d in sch.definitions.values())+'\n)\n'
    path.write_text(text);library.write_text(lib)
    ensure_filtered_power_flag(path,library)
    print('Lower local3V3 converter + ferrite schema applied; other circuits retained.')

if __name__=='__main__':edit()
