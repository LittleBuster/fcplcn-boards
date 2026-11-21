"""Build the Q&J CR1220-2 / LCSC C70381 nominal footprint and assembly model.

The manufacturer's page-5 PCB layout (QJ1220-2SMT, BS-12-B3AA004)
defines both SMT lands and two nonplated locating holes.  Pin numbering is
assigned here: 1 is the positive right contact; 2 is the negative left contact.

Source: https://atta.szlcsc.com/upload/public/pdf/source/20240508/
        105D3BE3DF78AB74B6E639FC10A0C203.pdf
The 3D envelope follows dimensioned nominal geometry.  Small moulding and
spring details are illustrative; the included CR1220 is an assembly visual.
"""
from pathlib import Path
from math import sin, cos, pi

ROOT = Path(__file__).resolve().parents[1]
NAME = "BatteryHolder_QJ_CR1220-2_C70381"
FP = ROOT / "FCPLCN-CPU-08-1v0/RelayStack.pretty" / (NAME + ".kicad_mod")
MODEL = ROOT / "FCPLCN-CPU-08-1v0/3d" / (NAME + ".wrl")
SOURCE = "https://atta.szlcsc.com/upload/public/pdf/source/20240508/105D3BE3DF78AB74B6E639FC10A0C203.pdf"

lines = [f'''(footprint "{NAME}"
  (version 20250114)
  (generator "pcbnew")
  (layer "F.Cu")
  (descr "Q&J CR1220-2, LCSC C70381, QJ1220-2SMT / BS-12-B3AA004. Manufacturer page5 PCB layout; origin coin centre. Pin1 positive atX+7.965mm, pin2 negative atX-8.000mm. Recommended lands4.35x2.30mm and4.04x2.30mm, twoNPTH1.20mm atX-3.60,+3.90mm. Bodydiameter14.8mm, nominalheight4.00mm, nominalleadspan19.46mm. {SOURCE}")
  (tags "battery holder coin CR1220 QJ C70381 SMT")
  (attr smd)
  (property "Reference" "REF**" (at 0 -8.35) (layer "F.SilkS") (hide yes) (effects (font (size 0.8 0.8) (thickness 0.12))))
  (property "Value" "CR1220-2" (at 0 8.35) (layer "F.Fab") (hide yes) (effects (font (size 0.8 0.8) (thickness 0.12))))
  (property "Datasheet" "{SOURCE}" (at 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1))))
  (fp_circle (center 0 0) (end 7.4 0) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
  (fp_circle (center 0 0) (end 6.25 0) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
  (fp_rect (start 5.25 -7.1) (end 7.85 7.1) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
  (fp_rect (start -9.67 -0.9) (end -5.8 0.9) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
  (fp_rect (start 5.81 -0.9) (end 9.79 0.9) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
  (fp_rect (start -10.27 -7.65) (end 10.39 7.65) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))
  (fp_text user "+" (at 9.0 2.1) (layer "F.SilkS") (effects (font (size 0.9 0.9) (thickness 0.15))))
  (fp_text user "-" (at -9.0 2.1) (layer "F.SilkS") (effects (font (size 0.9 0.9) (thickness 0.15))))''']

# The silk arcs leave clearance around both SMT lands.
for lo, hi in ((12, 168), (192, 348)):
    mid = (lo + hi) / 2
    points = [(7.55 * cos(d * pi / 180), 7.55 * sin(d * pi / 180)) for d in (lo, mid, hi)]
    start, middle, end = points
    lines.append(f'  (fp_arc (start {start[0]:.6f} {start[1]:.6f}) (mid {middle[0]:.6f} {middle[1]:.6f}) (end {end[0]:.6f} {end[1]:.6f}) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))')
lines += [
    '  (pad "1" smd rect (at 7.965 0) (size 4.35 2.30) (layers "F.Cu" "F.Paste" "F.Mask"))',
    '  (pad "2" smd rect (at -8 0) (size 4.04 2.30) (layers "F.Cu" "F.Paste" "F.Mask"))',
    '  (pad "" np_thru_hole circle (at -3.6 0) (size 1.2 1.2) (drill 1.2) (layers "*.Cu" "*.Mask"))',
    '  (pad "" np_thru_hole circle (at 3.9 0) (size 1.2 1.2) (drill 1.2) (layers "*.Cu" "*.Mask"))',
    f'  (model "${{KIPRJMOD}}/3d/{NAME}.wrl" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))',
    ')',
]
FP.write_text("\n".join(lines) + "\n")

# KiCad VRML models use 0.1-inch units.  Author in millimetres, invert Y.
parts = []
SCALE = 2.54
BROWN = "0.16 0.075 0.045"
CONTACT = "0.64 0.61 0.49"
SILVER = "0.72 0.75 0.78"
EDGE = "0.40 0.43 0.47"
INK = "0.04 0.045 0.05"

def mesh(points, faces, color, ccw=False):
    coords = ", ".join(" ".join(f"{v/SCALE:.8f}" for v in (x, -y, z)) for x, y, z in points)
    indices = ", ".join(", ".join(map(str, f)) + ", -1" for f in faces)
    winding = 'TRUE' if ccw else 'FALSE'
    return f'Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} shininess .32 }} }} geometry IndexedFaceSet {{ solid FALSE ccw {winding} coord Coordinate {{ point [{coords}] }} coordIndex [{indices}] }} }}'

def box(x, y, z, dx, dy, dz, color):
    points = [(x+ix*dx/2, y+iy*dy/2, z+iz*dz/2) for iz in (-1, 1) for iy in (-1, 1) for ix in (-1, 1)]
    faces = [[0,1,3,2], [4,6,7,5], [0,4,5,1], [2,3,7,6], [0,2,6,4], [1,5,7,3]]
    parts.append(mesh(points, faces, color, ccw=True))

def cylinder(x, y, z0, z1, radius, color, count=96):
    points = [(x+radius*cos(2*pi*i/count), y+radius*sin(2*pi*i/count), z) for z in (z0,z1) for i in range(count)]
    faces = [list(reversed(range(count))), list(range(count, 2*count))]
    faces += [[i,(i+1)%count,(i+1)%count+count,i+count] for i in range(count)]
    parts.append(mesh(points, faces, color))

def ring_segment(ro, ri, z0, z1, start, end, color, count=96):
    angles = [start+(end-start)*i/count for i in range(count+1)]
    points = [(rad*cos(a),rad*sin(a),z) for z in (z0,z1) for rad in (ro,ri) for a in angles]
    n = len(angles)
    faces = []
    for i in range(n-1):
        j = i+1
        faces += [[i,j,j+2*n,i+2*n], [i+n,i+3*n,j+3*n,j+n],
                  [i+2*n,j+2*n,j+3*n,i+3*n], [i,j,j+n,i+n]]
    faces += [[0,2*n,3*n,n], [n-1,2*n-1,4*n-1,3*n-1]]
    parts.append(mesh(points, faces, color))

# Nominal PPS base and walls; small slots and ribs are intentionally simplified.
cylinder(0,0,.20,.85,7.4,BROWN)
ring_segment(7.4,6.45,.85,4.0,-162*pi/180,162*pi/180,BROWN)
box(6.55,0,2.1,2.60,14.20,3.8,BROWN)

# Physical locating pegs: nominal diameters from the bottom view.  Projection
# below the seating plane is an explicitly nominal visual, not dimensioned.
cylinder(-3.6,0,-.2,.2,.375,BROWN,32)
cylinder(3.9,0,-.2,.2,.500,BROWN,32)

# Independent contact tails follow the physical 19.46mm span, not land sizes.
box((-9.67-5.8)/2,0,.10,9.67-5.8,1.8,.20,CONTACT)
box((5.81+9.79)/2,0,.10,9.79-5.81,1.8,.20,CONTACT)
box(-7.1,0,.55,.20,1.8,.90,CONTACT)
box(-1.3,0,.90,11.6,2.7,.20,CONTACT)
box(7.33,0,1.55,.20,1.8,2.9,CONTACT)
box(6.0,0,3.05,2.7,12.2,.20,CONTACT)

# Installed primary CR1220: 12.5mm diameter, 2.0mm thickness.  It is below the
# 4.00mm holder top envelope.  The positive face remains visible.
cylinder(0,0,.90,2.90,6.25,EDGE)
cylinder(0,0,1.05,2.91,6.13,SILVER)
box(0,0,2.922,1.8,.22,.018,INK)
box(0,0,2.922,.22,1.8,.018,INK)

# A small deterministic solid marking, supported by native KiCad's VRML reader.
glyphs = {
    'C': ['01110','10001','10000','10000','10000','10001','01110'],
    'R': ['11110','10001','10001','11110','10100','10010','10001'],
    '1': ['00100','01100','00100','00100','00100','00100','01110'],
    '2': ['01110','10001','00001','00010','00100','01000','11111'],
    '0': ['01110','10001','10011','10101','11001','10001','01110'],
    '3': ['11110','00001','00001','01110','00001','00001','11110'],
    'V': ['10001','10001','10001','10001','10001','01010','00100'],
}
def marking(text, cy, pitch=.14):
    width = (6*len(text)-1)*pitch
    x0 = -width/2
    for i,char in enumerate(text):
        for row,bits in enumerate(glyphs[char]):
            for col,bit in enumerate(bits):
                if bit=='1':
                    box(x0+(6*i+col+.5)*pitch, cy+(row-3)*pitch, 2.924,pitch*.83,pitch*.83,.018,INK)
marking('CR1220',-2.25)
marking('3V',2.25)

header = '''#VRML V2.0 utf8
# Q&J CR1220-2, LCSC C70381 / BS-12-B3AA004 / QJ1220-2SMT.
# Source page5 manufacturer drawing; exact footprint and nominal model envelope.
# Origin coin centre.  Local+X=positive terminal, -X=negative terminal.
# Overall physical leads X-9.67..+9.79mm, body diameter14.8mm, height4.00mm.
# Peg projection0.20mm and small spring/rib details are illustrative.
# Included CR1220 primary coin12.5x2.0mm is an installed-assembly visual.
'''
MODEL.write_text(header + "\n".join(parts) + "\n")
print(FP)
print(MODEL)
