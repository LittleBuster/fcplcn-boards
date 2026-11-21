"""Approved common purchasing specifications; PCB footprint names stay intact.

The reference whitelist deliberately excludes RTC C34/C36, the 0805 10 uF
capacitors, pulse resistors and the other unmodified circuit-specific parts.
"""
from copy import deepcopy

TDK_10UF_MPN = "C3216X7R1V106K160AC"
TDK_10UF_DATASHEET = "https://product.tdk.com/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c3216x7r1v106k160ac.pdf"


def resistor(value):
    return {"value": value, "fields": {
        "BOMGroup": f"R-0805-{value}-1pct-125mW", "BOMPackage": "0805",
        "Tolerance": "1%", "PowerRating": "0.125 W",
    }}


SPECS = {
    "R22": resistor("22R"),
    "R470": resistor("470R"),
    "R10K": resistor("10k"),
    "R4K7": resistor("4.7k"),
    "R1K5HP": {"value": "1.5k", "datasheet": "https://www.vishay.com/docs/20115/crcwhp.pdf", "fields": {
        "BOMGroup": "R-0805-1.5k-1pct-500mW-Vishay-HP", "BOMPackage": "0805",
        "MPN": "CRCW08051K50FKTAHP", "Manufacturer": "Vishay",
        "Tolerance": "1%", "PowerRating": "0.5 W",
    }},
    "R1K2HP": {"value": "1.2k", "datasheet": "https://www.vishay.com/docs/20115/crcwhp.pdf", "fields": {
        "BOMGroup": "R-0805-1.2k-1pct-500mW-Vishay-HP", "BOMPackage": "0805",
        "MPN": "CRCW08051K20FKTAHP", "Manufacturer": "Vishay",
        "Tolerance": "1%", "PowerRating": "0.5 W",
    }},
    "R220HP": {"value": "220R", "datasheet": "https://www.vishay.com/docs/20115/crcwhp.pdf", "fields": {
        "BOMGroup": "R-0805-220R-1pct-500mW-Vishay-HP", "BOMPackage": "0805",
        "MPN": "CRCW0805220RFKTAHP", "Manufacturer": "Vishay",
        "Tolerance": "1%", "PowerRating": "0.5 W",
    }},
    "C1N": {"value": "1nF C0G", "fields": {
        "BOMGroup": "C-0805-1nF-50V-C0G-5pct", "BOMPackage": "0805",
        "Tolerance": "5%", "Voltage": "50 V", "Dielectric": "C0G",
    }},
    "C10N": {"value": "10nF", "fields": {
        "BOMGroup": "C-0805-10nF-50V-X7R-10pct", "BOMPackage": "0805",
        "Tolerance": "10%", "Voltage": "50 V", "Dielectric": "X7R",
    }},
    "C100N": {"value": "100nF", "fields": {
        "BOMGroup": "C-0805-100nF-50V-X7R-10pct", "BOMPackage": "0805",
        "Tolerance": "10%", "Voltage": "50 V", "Dielectric": "X7R",
    }},
    "C1U": {"value": "1uF", "datasheet": "https://product.tdk.com/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c2012x7r1h105k125ab.pdf", "fields": {
        "BOMGroup": "C-0805-1uF-50V-X7R-10pct-TDK", "BOMPackage": "0805",
        "MPN": "C2012X7R1H105K125AB", "Manufacturer": "TDK",
        "Tolerance": "10%", "Voltage": "50 V", "Dielectric": "X7R", "Height_Max": "1.45 mm",
    }},
    "C10U": {"value": "10uF", "datasheet": TDK_10UF_DATASHEET, "fields": {
        "BOMGroup": "C-1206-10uF-35V-X7R-10pct-TDK", "BOMPackage": "1206",
        "MPN": TDK_10UF_MPN, "Manufacturer": "TDK", "Tolerance": "10%",
        "Voltage": "35 V", "Dielectric": "X7R", "Height_Max": "1.8 mm",
    }},
}

REFERENCE_GROUPS = {
    "Upper": {
        "R22": "R5 R6 R7 R8 R11 R12 R47 R48 R49",
        "R470": "R4 R23 R24 R25 R26 R46",
        "R10K": "R1 R2 R51 R52",
        "R4K7": "R17 R18 R21 R22 R27 R28 R29 R35 R36 R39 R40 R59 R60",
        "C1N": "C15 C17 C19 C21 C23 C25 C27 C29 C35 C49 C51",
        "C10N": "C10 C44 C45",
        "C100N": "C6 C9 C14 C16 C18 C20 C22 C24 C26 C28 C33 C39 C40 C42 C43 C46 C47 C48 C50",
        "C10U": "C1 C5 C8 C11 C12 C13 C38 C41",
    },
    "Lower": {
        "R470": "R10 R11 " + " ".join(f"R{i}" for i in range(141, 157)),
        "R1K2HP": " ".join(f"R{i}" for i in range(101, 117)),
        "R220HP": " ".join(f"R{i}" for i in range(161, 177)),
        "R10K": "R4 " + " ".join(f"R{i}" for i in range(121, 137)),
        "R4K7": "R2 R3 " + " ".join(f"R{i}" for i in range(181, 197)),
        "C10N": "C9 C10",
        "C100N": "C4 C5 C13 C14 " + " ".join(f"C{i}" for i in range(101, 117))
            + " " + " ".join(f"C{i}" for i in range(121, 137)),
        "C10U": "C2 C3",
        "C1U": " ".join(f"C{i}" for i in range(141, 157)),
    },
}


def component_spec(board, reference):
    """Return a private copy so generator callers cannot mutate the catalog."""
    for group, references in REFERENCE_GROUPS.get(board, {}).items():
        if reference in references.split():
            return deepcopy(SPECS[group])
    return None


def approved_references(board):
    return {ref for refs in REFERENCE_GROUPS.get(board, {}).values() for ref in refs.split()}
