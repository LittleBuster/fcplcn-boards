"""Purchasing groups retain the actual CAD footprints and electrical ratings."""


def component_record(component):
    fields = {field.get("name"): field.text or "" for field in component.findall("fields/field")}
    footprint = component.findtext("footprint", "")
    group = fields.get("BOMGroup", "")
    package = fields.get("BOMPackage", "")
    if bool(group) != bool(package):
        raise ValueError(f"Incomplete BOMGroup/BOMPackage on {component.get('ref')}")
    return {
        "value": component.findtext("value", ""),
        "footprint": footprint, "package": package or footprint, "bom_group": group,
        "datasheet": component.findtext("datasheet", ""),
        "mpn": fields.get("MPN", ""), "manufacturer": fields.get("Manufacturer", ""),
        "tolerance": fields.get("Tolerance", ""),
        "supplier_part_number": fields.get("SupplierPartNumber", ""),
        "source_url": fields.get("SourceURL", ""),
        "power_rating": fields.get("PowerRating", fields.get("Power", "")),
        "voltage": fields.get("Voltage", ""), "dielectric": fields.get("Dielectric", ""),
        "resistor_type": fields.get("ResistorType", ""), "height_max": fields.get("Height_Max", ""),
    }


def component_key(record):
    # Only explicitly assigned purchasing groups may share different CAD pads.
    # Different voltage, dielectric, pulse/power or tolerance never disappear.
    package_key = ("stock", record["bom_group"], record["package"]) if record["bom_group"] else ("cad", record["footprint"])
    return package_key + tuple(record[key] for key in (
        "value", "datasheet", "mpn", "manufacturer", "tolerance", "supplier_part_number",
        "source_url", "power_rating", "voltage", "dielectric", "resistor_type", "height_max",
    ))


EXTRA_COLUMNS = ["package", "bom_group", "power_rating", "voltage", "dielectric", "resistor_type", "height_max", "cad_footprints"]
