from pathlib import Path
import uuid,json,hashlib
ROOT=Path(__file__).resolve().parents[1];board=ROOT/'FCPLCN-RLY-1616-1v0'
name='TLP2363_5pin_SO6'
uid=lambda k:str(uuid.uuid5(uuid.NAMESPACE_URL,'fcplcn/tlp2363/'+k))
lines=[f'(footprint "{name}"',' (version 20260206) (generator "pcbnew") (generator_version "10.0") (layer "F.Cu")', ' (descr "Toshiba TLP2363 11-4L1S five-pin SO6, manufacturer land pattern 0.8x1.2mm, row pitch6.3mm, lead pitch1.27mm. Local courtyard8.0x4.5mm includes maximum3.95mm body length.")',f' (property "Reference" "REF**" (at 0 -3 0) (layer "F.SilkS") (hide yes) (uuid "{uid("ref")}") (effects (font (size 1.3 1.3) (thickness 0.15))))',f' (property "Value" "TLP2363" (at 0 3 0) (layer "F.Fab") (hide yes) (uuid "{uid("value")}") (effects (font (size 1.3 1.3) (thickness 0.15))))',' (attr smd)',f' (fp_rect (start -4 -2.25) (end 4 2.25) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{uid("court")}"))',f' (fp_rect (start -2.4 -1.975) (end 2.4 1.975) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab") (uuid "{uid("fab")}"))']
for n,y in [('top',-2.15),('bottom',2.15)]:lines.append(f' (fp_line (start -2.4 {y}) (end 2.4 {y}) (stroke (width 0.15) (type solid)) (layer "F.SilkS") (uuid "{uid(n)}"))')
# Pin one marker remains visible outside the lead and clear of the solder-mask aperture.
lines.append(f' (fp_circle (center -3.15 -2.05) (end -3.05 -2.05) (stroke (width 0.1) (type solid)) (fill solid) (layer "F.SilkS") (uuid "{uid("p1silk")}"))')
lines.append(f' (fp_line (start -2.4 -1.225) (end -1.65 -1.975) (stroke (width 0.1) (type solid)) (layer "F.Fab") (uuid "{uid("p1fab")}"))')
for pin,x,y in [(1,-3.15,-1.27),(3,-3.15,1.27),(4,3.15,1.27),(5,3.15,0),(6,3.15,-1.27)]:
 lines.append(f' (pad "{pin}" smd roundrect (at {x} {y}) (size 1.2 0.8) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.125) (uuid "{uid("pad"+str(pin))}"))')
lines.extend([' (embedded_fonts no)',f' (model "${{KIPRJMOD}}/3d/{name}.wrl" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))',')'])
(board/'RelayBoard.pretty'/f'{name}.kicad_mod').write_text('\n'.join(lines)+'\n')
# VRML native KiCad coordinate unit is2.54mm. Use conservative maximum envelope.
scale=1/2.54
v=['#VRML V2.0 utf8','# Toshiba TLP2363 11-4L1S; source Toshiba datasheet pages13/18. Max-body model.']
def box(x,y,z,sx,sy,sz,color):
 v.append(f'Transform {{ translation {x*scale:g} {y*scale:g} {z*scale:g} children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry Box {{ size {sx*scale:g} {sy*scale:g} {sz*scale:g} }} }} ] }}')
box(0,0,1.175,4.8,3.95,2.05,'0.08 0.08 0.085')
for x,y in [(-3.15,1.27),(-3.15,-1.27),(3.15,-1.27),(3.15,0),(3.15,1.27)]:
 box(x,y,.18,1.1,.4,.16,'0.78 0.78 0.76')
 box((2.52 if x>0 else -2.52),y,.46,.26,.4,.55,'0.78 0.78 0.76')
# Pin1 marker: top of package at local upper-left; VRML Y is inverted from PCB.
v.append(f'Transform {{ translation {-1.75*scale:g} {1.30*scale:g} {2.191*scale:g} rotation 1 0 0 1.5707963 children [ Shape {{ appearance Appearance {{ material Material {{ diffuseColor 0.82 0.78 0.65 }} }} geometry Cylinder {{ radius {0.22*scale:g} height {0.018*scale:g} }} }} ] }}')
(board/'3d'/f'{name}.wrl').write_text('\n'.join(v)+'\n')
(board/'3d'/'TLP2363-provenance.json').write_text(json.dumps({'part':'TLP2363','package':'11-4L1S / 5pin SO6','source':'https://toshiba.semicon-storage.com/info/TLP2363_datasheet_en_20251218.pdf?did=67887&prodName=TLP2363','land_pattern_page':13,'package_page':18,'body_max_mm':[4.8,3.95,2.2],'overall_lead_span_max_mm':7.4,'land_pad_mm':[1.2,.8],'land_row_pitch_mm':6.3,'lead_pitch_mm':1.27,'footprint_courtyard_mm':[8,4.5],'model':'Native VRML geometry based on maximum envelope, not vendor STEP','model_sha256':hashlib.sha256((board/'3d'/f'{name}.wrl').read_bytes()).hexdigest(),'model_maximum_marker_top_mm':2.2,'pin1_marker':'Visible F.SilkS dot outside pin1 land and flush 3D top marker'},indent=2)+'\n')
print('TLP2363 footprint and native max-envelope model built')
