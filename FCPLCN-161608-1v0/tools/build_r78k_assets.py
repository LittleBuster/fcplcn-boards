"""RECOM R-78K SIP3 source-derived nominal mechanical assets.
No CAD project mutation. Nominal body 11.5 x 7.55 x 10.2; worst envelope in provenance.
Coordinates: PCB top z=0; pin1=(0,0), pin2=(2.54,0), pin3=(5.08,0).
"""
from pathlib import Path
import hashlib,json
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, required=True, help='Staging directory containing RECOM-R-78K-0.5.pdf and RECOM-R-78K-1.0.pdf')
OUT=parser.parse_args().output_dir.resolve()
OUT.mkdir(exist_ok=True)
X0,X1,Y0,Y1=-3.21,8.29,-5.55,2.0
font={
'R':['11110','10001','10001','11110','10100','10010','10001'],
'E':['11111','10000','10000','11110','10000','10000','11111'],
'C':['01111','10000','10000','10000','10000','10000','01111'],
'O':['01110','10001','10001','10001','10001','10001','01110'],
'M':['10001','11011','10101','10101','10001','10001','10001'],
'3':['11110','00001','00001','01110','00001','00001','11110'],
'V':['10001','10001','10001','10001','10001','01010','00100'],
'0':['01110','10001','10011','10101','11001','10001','01110'],
'1':['00100','01100','00100','00100','00100','00100','01110'],
'5':['11111','10000','10000','11110','00001','00001','11110'],
'A':['01110','10001','10001','11111','10001','10001','10001'],
'.':['00000','00000','00000','00000','00000','00110','00110'],
' ':['00000']*7}
def f(n): return f'{n:.8g}'
def model(current):
 parts=['#VRML V2.0 utf8',
 '# RECOM R-78K3.3-'+current+' nominal dimensions from manufacturer drawing.',
 '# Body 11.5x7.55x10.2 mm, feet included; pin pitch 2.54 mm, square lead 0.64 mm, tail 4.1 mm.',
 '# Coordinates match footprint pin1 origin; PCB top is z=0. Model does not include generic dimensional tolerance.',
 '# Source https://recom-power.com/pdf/Innoline/R-78K-'+current+'.pdf',
 '# White nominal identification text is a visual aid; actual supplier legend may vary.']
 def box(x,y,z,sx,sy,sz,col):
  parts.append(f'Transform {{ translation {f(x/2.54)} {f(-y/2.54)} {f(z/2.54)} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {col} }} }} geometry Box {{ size {f(sx/2.54)} {f(sy/2.54)} {f(sz/2.54)} }} }} ] }}')
 box(2.54,(Y0+Y1)/2,5.35,11.5,7.55,9.7,'.035 .038 .042')
 for x in (X0+.25,X1-.25):box(x,(Y0+Y1)/2,.25,.5,7.55,.5,'.035 .038 .042')
 for x in (0,2.54,5.08):box(x,0,-1.8,.64,.64,4.6,'.73 .75 .77')
 def text(s,y,px):
  width=(6*len(s)-1)*px
  start=2.54-width/2
  for i,ch in enumerate(s):
   for row,line in enumerate(font[ch]):
    for col,val in enumerate(line):
     if val=='1':box(start+(i*6+col+.5)*px,y+(row+.5)*px,10.207,px*.87,px*.87,.014,'.82 .84 .82')
 text('RECOM',-4.55,.25)
 text('3V3 '+current+'A',-1.75,.17)
 return '\n'.join(parts)+'\n'
def fp(current):
 name='RECOM_R-78K3.3-'+current+'_SIP3_P2.54mm'
 modelname='RECOM_R-78K3.3-'+current+'.wrl'
 pieces=[f'(footprint "{name}" (version 20260206) (generator "pcbnew") (layer "F.Cu")',
 f' (descr "RECOM R-78K3.3-{current}, input4.5-36V, output3.3V, SIP3 11.5x7.55x10.2mm nominal; maximum body12.0x7.8x10.7mm; squarelead0.64+/-0.1mm, pitch2.54. Manufacturer drawing https://recom-power.com/pdf/Innoline/R-78K-{current}.pdf")',
 ' (tags "RECOM R-78K SIP3 switching regulator 2.54mm")',
 ' (property "Reference" "REF**" (at 2.54 -7.0) (layer "F.SilkS") (effects (font (size 1.3 1.3) (thickness 0.15))))',
 f' (property "Value" "R-78K3.3-{current}" (at 2.54 3.5) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
 f' (property "Datasheet" "https://recom-power.com/pdf/Innoline/R-78K-{current}.pdf" (at 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1) (thickness 0.15))))',
 ' (attr through_hole)',
 ' (fp_rect (start -3.71 -6.55) (end 9.29 2.75) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))',
 f' (fp_rect (start {X0} {Y0}) (end {X1} {Y1}) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))',
 ' (fp_line (start -3.21 1.0) (end -2.21 2.0) (stroke (width 0.1) (type solid)) (layer "F.Fab"))',
 ' (fp_rect (start -3.4 -5.74) (end 8.48 2.19) (stroke (width 0.15) (type solid)) (fill none) (layer "F.SilkS"))',
 ' (fp_text user "${REFERENCE}" (at 2.54 -2.7) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))']
 for i,x in enumerate((0,2.54,5.08),1):
  shape='rect' if i==1 else 'circle'
  pieces.append(f' (pad "{i}" thru_hole {shape} (at {x} 0) (size 1.9 1.9) (drill 1.2) (layers "*.Cu" "*.Mask") (remove_unused_layers no))')
 pieces.append(f' (model "${{KIPRJMOD}}/3d/{modelname}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))')
 pieces.append(')')
 return name,'\n'.join(pieces)+'\n'
provenance={
'manufacturer':'RECOM','series':['R-78K-0.5','R-78K-1.0'],
'nominal_body_mm':{'x_min':X0,'x_max':X1,'y_min':Y0,'y_max':Y1,'z_min':0,'z_max':10.2},
'maximum_body_mm':{'x_min':-3.46,'x_max':9.04,'y_min':-6.3,'y_max':2.5,'z_max':10.7},
'maximum_body_note':'Conservative independent limits include total L/W tolerance and pin-to-case3.21+/-0.25,2.0+/-0.5 location tolerances. Maximum envelope is swept rather than symmetric about nominalbody. Keep all adjacentpartsoutsidecourtyard.',
'generic_tolerances_mm':{'one_decimal':.5,'two_decimal':.25},
'lead_square_nominal_mm':.64,'lead_square_max_mm':.74,'lead_max_diagonal_mm':2**.5*.74,
'lead_tail_nominal_mm':4.1,'lead_tail_max_mm':4.6,
'footprint_finished_hole_mm':1.2,'footprint_pad_mm':1.9,'annular_ring_mm':.35,
'pinning':{'1':'+Vin','2':'GND','3':'+Vout'},'pin_xy_mm':[[0,0],[2.54,0],[5.08,0]],
'case_height_max_mm':10.7,
'mounting_note':'Mount flush to the two manufacturer 0.5mm moulded feet, included in total case height. All three R78K modules (U3/U5/U12) are installed on Upper only; Lower retains its LDO by user height constraint. Verify protruding solder tails against the Lower components using check_r78_clearance.py.',
'placement_in_this_revision':{'Upper.U3':'R-78K3.3-1.0','Upper.U5':'R-78K3.3-0.5','Upper.U12':'R-78K3.3-0.5','Lower':'Existing LDO retained by user height constraint'},
'input_voltage_range_v':[4.5,36],'output_voltage_v':3.3,
'capacitive_load_max_note':'No maximum capacitive load value specified in these two reviewed R-78K datasheets. Retain local decoupling and validate startup/transients; do not copy 220uF constraint from different R-78 series.',
'sources':[], 'assets':{},
'visual_only_details':['Identification text','Casefoot width .5mm (foot height .5mm is sourced)','Square pin ends omit tip bevel']}
for c in ['0.5','1.0']:
 file=OUT/f'RECOM_R-78K3.3-{c}.wrl';file.write_text(model(c));
 name,txt=fp(c);(OUT/f'{name}.kicad_mod').write_text(txt)
 source=OUT/f'RECOM-R-78K-{c}.pdf'
 provenance['sources'].append({'mpn':f'R-78K3.3-{c}','url':f'https://recom-power.com/pdf/Innoline/R-78K-{c}.pdf','file':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'rated_current_a':float(c)})
 for a in [file,OUT/f'{name}.kicad_mod']:
  provenance['assets'][a.name]=hashlib.sha256(a.read_bytes()).hexdigest()
(OUT/'RECOM-R78K-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(json.dumps({'out':str(OUT),'assets':list(provenance['assets'])},indent=2))
