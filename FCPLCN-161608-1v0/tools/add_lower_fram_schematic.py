"""Add the lower-board FM24CL64B circuit without regenerating existing CAD.

Only U9, C14, their local labels/wires and a dedicated schematic section are
added. Re-running an already applied addition is a no-op. PCB placement and
routing are separate operations.
"""
from pathlib import Path
import re

from board_paths import board_file, board_dir, board_name
from passive_specifications import SPECS
from schematic import Schematic, Pin, rectangle

ROOT = Path(__file__).resolve().parents[1]
DATASHEET = "https://www.infineon.com/assets/row/public/documents/10/49/infineon-fm24cl64b-64-kbit-8-k-8-serial-i2c-f-ram-datasheet-en.pdf"
SOURCE = "https://www.hqonline.com/product-detail/frams-cypress-fm24cl64b-gtr-2500407054"


def expression_end(text, start):
    """Index after a balanced s-expression, respecting quoted strings."""
    depth = 0
    quoted = escaped = False
    for pos in range(start, len(text)):
        char = text[pos]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return pos + 1
    raise ValueError("Unbalanced KiCad expression")


def main():
    path = board_file(ROOT, "Lower", ".kicad_sch")
    library_path = board_dir(ROOT, "Lower") / "RelayBoard.kicad_sym"
    original = path.read_text()
    original_library = library_path.read_text()
    if '(property "Reference" "U9"' in original:
        assert '(property "Value" "FM24CL64B-GTR"' in original
        assert '(property "Reference" "C14"' in original
        print("Lower FRAM schematic already present; no changes.")
        return
    assert '(property "Reference" "C14"' not in original
    root_uuid = re.search(r'\(uuid "([^\"]+)"\)', original).group(1)
    schema = Schematic(board_name("Lower"), namespace="RelayBoard",
                       uuid_seed="FCPLCN/lower-FRAM-addition-v1")
    schema.root = '"' + root_uuid + '"'
    schema.define(
        "FM24CL64B", "U",
        [Pin("1", "A0", 15.24, 7.62, 180, "input"),
         Pin("2", "A1", 15.24, 2.54, 180, "input"),
         Pin("3", "A2", 15.24, -2.54, 180, "input"),
         Pin("4", "VSS", 15.24, -12.7, 180, "power_in"),
         Pin("5", "SDA", -15.24, 7.62, 0, "bidirectional"),
         Pin("6", "SCL", -15.24, 2.54, 0, "input"),
         Pin("7", "WP", -15.24, -7.62, 0, "input"),
         Pin("8", "VDD", 15.24, 12.7, 180, "power_in")],
        [rectangle((-10.16, -15.24), (10.16, 15.24))],
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="64-Kbit (8192-byte) I2C F-RAM, 2.7-3.65 V, SOIC-8; address 0x50, WP low",
        datasheet=DATASHEET,
    )
    # The existing embedded Supply_Capacitor definition is reused verbatim.
    schema.define("Supply_Capacitor", "C",
                  [Pin("1", "~", 0, 3.81, 270),
                   Pin("2", "~", 0, -3.81, 90)], [],
                  footprint="RelayBoard:C_0805_2012Metric")
    schema.text("14    Энергонезависимая память F-RAM · 8 Кбайт",
                (310.0, 449.58), size=2.25, bold=True)
    pins = schema.place(
        "FM24CL64B", "U9", (378.46, 482.6), value="FM24CL64B-GTR",
        ref_at=(378.46, 464.82), value_at=(378.46, 500.38),
        fields={"MPN": "FM24CL64B-GTR", "Manufacturer": "Infineon",
                "SourceURL": SOURCE, "SupplierPartNumber": "C9829",
                "I2CAddress": "0x50", "MemoryCapacity": "8192 bytes",
                "BOMPackage": "SOIC-8", "BOMGroup": "IC-FRAM-FM24CL64B-GTR-SOIC8",
                "Height_Max": "1.75 mm"},
    )
    nets = {"1": "GND", "2": "GND", "3": "GND", "4": "GND",
            "5": "I2C_SDA", "6": "I2C_SCL", "7": "GND", "8": "+3V3"}
    for number, name in nets.items():
        at = pins[number]
        left = number in ("5", "6", "7")
        end = (at[0] - 12.7 if left else at[0] + 12.7, at[1])
        schema.wire(at, end)
        schema.label(name, end, angle=180 if left else 0, size=1.17)
    cap = schema.place(
        "Supply_Capacitor", "C14", (472.44, 482.6),
        value=SPECS["C100N"]["value"], ref_at=(482.6, 480.06),
        value_at=(482.6, 485.14), fields=SPECS["C100N"]["fields"],
    )
    for number, name, end in (("1", "+3V3", (472.44, 469.9)),
                               ("2", "GND", (472.44, 495.3))):
        schema.wire(cap[number], end)
        schema.label(name, end, size=1.17)
    schema.text("Адрес 0x50; A0–A2 и WP → GND. Питание 3,3 В; C14 рядом с U9.",
                (310.0, 513.08), size=1.17)
    definition = schema.definitions["FM24CL64B"]
    lib_start = original.index("(lib_symbols")
    lib_end = expression_end(original, lib_start)
    embedded = original[:lib_end - 1] + "\n" + definition.sexpr("RelayBoard") + "\n" + original[lib_end - 1:]
    assert embedded.rstrip().endswith(")")
    # This lower project uses explicit 0.254-mm wires; a zero/default width
    # exports invisibly with its existing KiCad drawing defaults.
    elements = [item.replace('(stroke (width 0) (type default))',
                             '(stroke (width 0.254) (type solid))')
                for item in schema.elements]
    result = embedded.rstrip()[:-1] + "\n" + "\n".join(elements) + "\n)\n"
    assert original_library.rstrip().endswith(")")
    local_library = original_library.rstrip()[:-1] + "\n" + definition.sexpr() + "\n)\n"
    assert result.count('(property "Reference" "U9"') == 1
    assert result.count('(property "Reference" "C14"') == 1
    path.write_text(result)
    library_path.write_text(local_library)
    print("Added U9 FM24CL64B-GTR and C14 100nF; existing source blocks preserved.")


if __name__ == "__main__":
    main()
