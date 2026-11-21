"""Build a conservative APAQ ARHA 100 uF / 35 V radial capacitor asset.

MPN: 350ARHA101M06X8P00, LCSC C217555.
Official source: https://www.apaq.com.tw/Templates/att/ARHA_20241121.pdf?lng=en
06X8: nominal diameter 6.3 mm, maximum diameter 6.8 mm; L=8.0 mm,
alpha=-0.5..+1.0 mm, so the complete case length is at most 9.0 mm.
The model is seated directly on the PCB, without an added spacer or lead lift.
Small can details are illustrative; the overall body uses MAXIMUM dimensions.

Only the library footprint and VRML are written. No PCB or schematic is edited.
"""
from math import cos, sin, pi
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "CP_APAQ_ARHA_D6.3mm_P2.5mm_H9max"
MODEL_NAME = "APAQ_350ARHA101M06X8P00_H9max"
SOURCE = "https://www.apaq.com.tw/Templates/att/ARHA_20241121.pdf?lng=en"
FP = ROOT / "FCPLCN-RLY-1616-1v0/RelayBoard.pretty" / (NAME + ".kicad_mod")
MODEL = ROOT / "FCPLCN-RLY-1616-1v0/3d" / (MODEL_NAME + ".wrl")
FP.parent.mkdir(parents=True, exist_ok=True)
MODEL.parent.mkdir(parents=True, exist_ok=True)

# Origin is the positive lead. Nominal body centre is halfway between leads.
# Courtyard diameter: 6.8 maximum body + 0.25 clearance on each side = 7.3 mm.
footprint = f'''(footprint "{NAME}"
  (version 20260206)
  (generator "pcbnew")
  (generator_version "10.0")
  (layer "F.Cu")
  (descr "APAQ 350ARHA101M06X8P00 / C217555. Polymer 100uF 35V +/-20%, 5000h at105C. NominalD6.3, maxD6.8, maxseatedcaseH9.0 without spacer, pitch2.5, leadD0.6+/-0.05. Pad1PLUS, pad2MINUS. {SOURCE}")
  (tags "APAQ ARHA polymer radial capacitor 100uF 35V low profile Hmax9 C217555")
  (property "Reference" "REF**" (at 1.25 -4.8 0) (layer "F.SilkS") (effects (font (size 1.3 1.3) (thickness 0.15))))
  (property "Value" "100uF 35V" (at 1.25 4.3 0) (layer "F.Fab") (hide yes) (effects (font (size 0.8 0.8) (thickness 0.12))))
  (property "Datasheet" "{SOURCE}" (at 0 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1))))
  (property "Description" "APAQ ARHA 100uF 35V; max6.8x9.0mm; positive lead1" (at 0 0 0) (layer "F.Fab") (hide yes) (effects (font (size 1 1))))
  (attr through_hole)
  (fp_circle (center 1.25 0) (end 4.4 0) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
  (fp_circle (center 1.25 0) (end 4.75 0) (stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS"))
  (fp_circle (center 1.25 0) (end 4.9 0) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))
  (fp_text user "+" (at 0 -1.9) (layer "F.SilkS") (effects (font (size 1.3 1.3) (thickness 0.15))))
  (fp_text user "+" (at -0.9 -1.7) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))
  (pad "1" thru_hole rect (at 0 0) (size 1.6 1.6) (drill 0.8) (layers "*.Cu" "*.Mask") (remove_unused_layers no))
  (pad "2" thru_hole circle (at 2.5 0) (size 1.6 1.6) (drill 0.8) (layers "*.Cu" "*.Mask") (remove_unused_layers no))
  (model "${{KIPRJMOD}}/3d/{MODEL_NAME}.wrl" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
)
'''
FP.write_text(footprint)

# Native KiCad VRML units are tenths of an inch. Invert Y for the PCB frame.
SCALE = 2.54
parts = []
SILVER = "0.67 0.70 0.74"
EDGE = "0.43 0.46 0.51"
BLACK = "0.025 0.03 0.035"
LEAD = "0.72 0.74 0.77"


def mesh(points, faces, color):
    coords = ", ".join(" ".join(f"{v/SCALE:.9f}" for v in (x, -y, z))
                       for x, y, z in points)
    indices = ", ".join(", ".join(map(str, f)) + ", -1" for f in faces)
    parts.append(f'Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} shininess .35 }} }} geometry IndexedFaceSet {{ solid FALSE ccw FALSE coord Coordinate {{ point [{coords}] }} coordIndex [{indices}] }} }}')


def cylinder(x, y, z0, z1, radius, color, count=96):
    points = [(x + radius*cos(2*pi*i/count), y + radius*sin(2*pi*i/count), z)
              for z in (z0, z1) for i in range(count)]
    faces = [list(reversed(range(count))), list(range(count, 2*count))]
    faces += [[i, (i+1)%count, (i+1)%count+count, i+count]
              for i in range(count)]
    mesh(points, faces, color)


def can_sector(start, end, color, count=96):
    """A closed angular can sector, with its complete top at Z=9.0 mm."""
    angles = [start + (end-start)*i/count for i in range(count+1)]
    # Include axis extrema exactly so the conservative model is 6.8 mm on
    # both plan axes, rather than a slightly inscribed polygon in Y.
    angles = sorted(set(angles + [a*pi/2 for a in range(-4, 9)
                                  if start <= a*pi/2 <= end]))
    n = len(angles)
    ring = [(1.25+3.4*cos(a), 3.4*sin(a), z) for z in (.2, 9.0)
            for a in angles]
    points = ring + [(1.25, 0, .2), (1.25, 0, 9.0)]
    bottom, top = 2*n, 2*n+1
    faces = []
    for i in range(n-1):
        faces += [[i, i+1, i+1+n, i+n], [bottom, i+1, i],
                  [top, i+n, i+1+n]]
    faces += [[bottom, 0, n, top], [n-1, bottom, top, 2*n-1]]
    mesh(points, faces, color)


# Direct seating plane is Z=0. The base is included in the maximum 9.0 mm.
cylinder(1.25, 0, 0, .25, 3.05, BLACK)
can_sector(-50*pi/180, 50*pi/180, BLACK)  # negative stripe faces lead2 (+X)
can_sector(50*pi/180, 310*pi/180, SILVER)

# Nominal round leads, cut to 3 mm below the seating plane for assembly view.
for x in (0, 2.5):
    cylinder(x, 0, -3.0, .25, .3, LEAD, 32)

MODEL.write_text(
    '#VRML V2.0 utf8\n'
    '# APAQ350ARHA101M06X8P00/C217555 conservative MAXIMUM body model.\n'
    '# NominalD6.3, maximumD6.8, maximumseatedcaseH9.0, leadpitch2.5mm.\n'
    '# No additional lead lift or spacer; positivelead1atX0, negativelead2atX2.5.\n'
    '# Black sector is the negative polarity marking.\n'
    '# Source: ' + SOURCE + '\n' + '\n'.join(parts) + '\n')

print(FP)
print(MODEL)
