"""Source-derived ADM2687E RI-16-2 and eight-pole KF128 assets. Regenerate with --output-dir DIRECTORY."""
from pathlib import Path
import math,json,hashlib,argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output-dir",type=Path,required=True,help="Staging directory, copy source PDFs here before regeneration")
OUT=parser.parse_args().output_dir.resolve()
OUT.mkdir(parents=True,exist_ok=True)
def num(n):return f'{n:.8g}'
def box(x,y,z,sx,sy,sz,color):
 return f'Transform {{ translation {num(x/2.54)} {num(-y/2.54)} {num(z/2.54)} children [Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Box {{ size {num(sx/2.54)} {num(sy/2.54)} {num(sz/2.54)} }} }}] }}'
def cylinder(x,y,z,radius,height,color,sides=24):
 pts=[]
 for zz in [-height/2,height/2]:
  for i in range(sides):
   a=2*math.pi*i/sides;pts.append((radius*math.cos(a)/2.54,radius*math.sin(a)/2.54,zz/2.54))
 faces=[list(range(sides-1,-1,-1)),list(range(sides,2*sides))]
 faces +=[[i,(i+1)%sides,(i+1)%sides+sides,i+sides]for i in range(sides)]
 return f'Transform {{ translation {num(x/2.54)} {num(-y/2.54)} {num(z/2.54)} children [Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry IndexedFaceSet {{ coord Coordinate {{ point ['+', '.join(' '.join(num(v)for v in p)for p in pts)+'] } coordIndex ['+', '.join(', '.join(map(str,f))+', -1'for f in faces)+'] } }] }'

def header(name,descr,refxy):
 return [f'(footprint "{name}" (version 20260206) (generator "pcbnew") (layer "F.Cu")',f' (descr "{descr}")',f' (property "Reference" "REF**" (at {refxy[0]} {refxy[1]}) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',f' (property "Value" "{name}" (at 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1) (thickness 0.15))))']

name='KF128-2.54-8P';rows=header(name,'KEFA KF128 8-pole; pitch2.54; nominal length20.32 +/-0.40; depth6.30; wire-entry +Y; same pad geometry as existing3P/4P',(8.89,-4.25))
rows+=[' (attr through_hole)',
 ' (fp_rect (start -1.72 -3.5) (end 19.5 3.6) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))',
 ' (fp_rect (start -1.27 -3.0) (end 19.05 3.3) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))',
 ' (fp_line (start -1.27 -2.0) (end -0.27 -3.0) (stroke (width 0.1) (type solid)) (layer "F.Fab"))',
 ' (fp_line (start -1.52 -3.18) (end 19.3 -3.18) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))\n (fp_line (start -1.52 -3.18) (end -1.52 0.9) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))\n (fp_line (start 19.3 -3.18) (end 19.3 0.9) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))']
for i in range(8):
 shape='roundrect'if i==0 else'oval';extra=' (roundrect_rratio 0.22)'if i==0 else''
 rows.append(f' (pad "{i+1}" thru_hole {shape} (at {i*2.54:.2f} 0) (size 1.9 2.15) (drill 1.3) (layers "*.Cu" "*.Mask") (remove_unused_layers no){extra})')
rows+=[' (model "${KIPRJMOD}/3d/KF128-8P.wrl" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))',')']
(OUT/f'{name}.kicad_mod').write_text('\n'.join(rows)+'\n')
model=['#VRML V2.0 utf8','# KF128-8P. Existing project convention models maximum LENGTH20.72 but nominal depth6.3,height8.8.',' # Nominal length20.32 +/-0.40; pad1 origin; wire entry toward +Y. Screw and port detail visual only.']
model+=[box(8.89,.15,4.4,20.72,6.3,8.8,'.035 .32 .15')]
for i in range(8):
 x=i*2.54
 model +=[cylinder(x,0,8.83,.845,.1,'.72 .73 .75'),box(x,0,8.9,.16,1.28,.04,'.10 .12 .14'),box(x,3.31,2.48,1.47,.06,2.05,'.017 .09 .043'),box(x,0,-1.7,.8,.5,3.6,'.72 .73 .75')]
(OUT/'KF128-8P.wrl').write_text('\n'.join(model)+'\n')

name='ADM2687E_SOIC_IC_16_7.5x12.75mm_P1.27mm'
rows=header(name,'Analog Devices ADM2687EBRIZ RI-16-2 SOIC_IC; body7.5x12.75; leadspan10.31; maxH2.64; IPC-style enlarged hand-solder lands from manufacturer dimension drawing',(0,-7.65))
rows+=[' (attr smd)',
 ' (fp_rect (start -6.15 -6.75) (end 6.15 6.75) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))',
 ' (fp_rect (start -3.75 -6.375) (end 3.75 6.375) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))',
 ' (fp_line (start -3.75 -5.375) (end -2.75 -6.375) (stroke (width 0.1) (type solid)) (layer "F.Fab"))',
 ' (fp_rect (start -3.95 -6.575) (end 3.95 6.575) (stroke (width 0.15) (type solid)) (fill none) (layer "F.SilkS"))',
 ' (fp_circle (center -4.5 -5.5) (end -4.3 -5.5) (stroke (width 0.15) (type solid)) (fill none) (layer "F.SilkS"))',
 ' (property "Datasheet" "https://www.analog.com/media/en/technical-documentation/data-sheets/adm2682e-adm2687e.pdf" (at 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1) (thickness 0.15))))']
for i in range(8):
 y=-4.445+i*1.27
 for pin,x in [(i+1,-5.15),(16-i,5.15)]:
  rows.append(f' (pad "{pin}" smd roundrect (at {x} {y:.3f}) (size 1.5 0.65) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25))')
rows+=[' (model "${KIPRJMOD}/3d/ADM2687E_RI-16-2.wrl" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))',')']
(OUT/f'{name}.kicad_mod').write_text('\n'.join(rows)+'\n')

model=['#VRML V2.0 utf8','# ADM2687E RI-16-2 nominal source-derived envelope. Body7.50x12.75, leadspan10.31, H2.54.','# Lead shape/mark detail simplified; authoritative dimensions in ADI package drawing.']
model+=[box(0,0,1.36,7.5,12.75,2.36,'.045 .045 .045'),cylinder(-2.8,-5.5,2.547,.32,.018,'.20 .20 .20')]
for i in range(8):
 y=-4.445+i*1.27
 for sign in [-1,1]:
  # Gull-wing outline in XZ, extruded through nominal lead width0.42.
  shape=[(3.7,1.45),(3.95,1.45),(4.395,.28),(5.155,.28),(5.155,0),(4.285,0),(3.8,1.17),(3.7,1.17)]
  pts=[(sign*x/2.54,-(y+dy)/2.54,z/2.54)for dy in [-.21,.21]for x,z in shape]
  faces=[list(range(7,-1,-1)),list(range(8,16))]+[[j,(j+1)%8,(j+1)%8+8,j+8]for j in range(8)]
  model.append('Shape { appearance Appearance { material Material { diffuseColor .72 .73 .75 } } geometry IndexedFaceSet { solid FALSE coord Coordinate { point ['+', '.join(' '.join(num(v)for v in p)for p in pts)+'] } coordIndex ['+', '.join(', '.join(map(str,f))+', -1'for f in faces)+'] } }')
(OUT/'ADM2687E_RI-16-2.wrl').write_text('\n'.join(model)+'\n')
sources=[{'name':'ADI RI-16-2','url':'https://mds.analog.com/api/public/content/ri_16_2.pdf','local_file':'ADI-RI-16-2.pdf'}, {'name':'ADM2687E RevD','url':'https://www.analog.com/media/en/technical-documentation/data-sheets/adm2682e-adm2687e.pdf','local_file':'ADM2682E-ADM2687E-RevD.pdf'}, {'name':'KEFA KF128','url':'https://shopcdnalpha.grainajz.com/category/348983/2332/c1956744e66148f29d61bba375d3dac9/KF128-2.54.pdf'}]
for s in sources:
 f=OUT/s.get('local_file','')
 if f.is_file():s['sha256']=hashlib.sha256(f.read_bytes()).hexdigest()
 elif 'local_file' in s:s['local_file_not_downloaded']=s.pop('local_file')
prov={'sources':sources,'ADM2687E':{'manufacturer':'Analog Devices','MPN':'ADM2687EBRIZ','nominal_body_mm':[7.5,12.75,2.54],'maximum_body_mm':[7.6,12.95,2.64],'nominal_lead_span_mm':10.31,'maximum_lead_span_mm':10.55,'pitch_mm':1.27,'pad_center_x_mm':[-5.15,5.15],'pad_size_mm':[1.5,.65],'minimum_opposing_pad_gap_mm':8.8,'land_pattern_note':'Engineering land pattern visually checked against RI-16-2: nominal heel5.155-.76=4.395mm; landinner4.4mm. Opposing landgap8.8mm. Not a vendor-recommended footprint and not a whole-board5kV isolation certification.'},'KF128_8P':{'pitch_mm':2.54,'pin_span_mm':17.78,'nominal_body_length_mm':20.32,'maximum_body_length_mm':20.72,'model_body_length_mm':20.72,'nominal_depth_mm':6.3,'nominal_height_mm':8.8,'nominal_tail_mm':3.5,'tail_tolerance_mm':.3,'model_tail_mm':3.5,'pin_cross_section_mm':[.8,.5],'finished_drill_mm':1.3,'pad_size_mm':[1.9,2.15],'body_y_relative_pinrow_mm':[-3.0,3.3],'nominal_front_for_pinrow_Y118_mm':121.3},'assets':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in OUT.glob('*')if p.suffix in ['.kicad_mod','.wrl']}}
(OUT/'RS485-assets-provenance.json').write_text(json.dumps(prov,indent=2)+'\n')
print('Built',sorted(prov['assets']))
