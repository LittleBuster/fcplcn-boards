"""Small KiCad 9 schematic writer using millimeters and embedded symbols."""
from dataclasses import dataclass
from pathlib import Path
import json
import math
import uuid


def q(value):
    return json.dumps(str(value), ensure_ascii=False)


def mm(value):
    return f"{round(value, 4):g}"


def xy(point):
    return " ".join(map(mm, point))


def pt(x, y):
    return round(x, 4), round(y, 4)


def uid(key):
    return q(uuid.uuid5(uuid.NAMESPACE_URL, f"codex-schematic/{key}"))


def effects(size=1.27, *, hide=False, justify="", bold=False):
    font = f"(font (size {mm(size)} {mm(size)})" + (" (bold yes)" if bold else "") + ")"
    alignment = f" (justify {justify})" if justify else ""
    visibility = " (hide yes)" if hide else ""
    return f"(effects {font}{alignment}{visibility})"


def prop(name, value, location, **style):
    return f"(property {q(name)} {q(value)} (at {xy(location)} 0) {effects(**style)})"


def stroke(width=0):
    return f"(stroke (width {mm(width)}) (type default))"


def rectangle(start, end, *, fill="background", width=0.254):
    return f"(rectangle (start {xy(start)}) (end {xy(end)}) {stroke(width)} (fill (type {fill})))"


def polyline(*points, fill="none", width=0.254):
    vertices = " ".join(f"(xy {xy(point)})" for point in points)
    return f"(polyline (pts {vertices}) {stroke(width)} (fill (type {fill})))"


def circle(center, radius, *, fill="none", width=0.254):
    return f"(circle (center {xy(center)}) (radius {mm(radius)}) {stroke(width)} (fill (type {fill})))"


def arc(start, mid, end, *, width=0.254):
    return f"(arc (start {xy(start)}) (mid {xy(mid)}) (end {xy(end)}) {stroke(width)} (fill (type none)))"


@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    x: float
    y: float
    angle: int = 0
    kind: str = "passive"
    length: float = 2.54
    shape: str = "line"

    def sexpr(self):
        return (
            f"(pin {self.kind} {self.shape} (at {xy((self.x, self.y, self.angle))}) (length {mm(self.length)}) "
            f"(name {q(self.name)} {effects()}) (number {q(self.number)} {effects(1.0)}))"
        )


@dataclass(frozen=True)
class Definition:
    name: str
    reference: str
    pins: tuple
    drawing: tuple
    names: bool = True
    numbers: bool = True
    footprint: str = ""
    description: str = ""
    datasheet: str = ""
    on_board: bool = True

    def sexpr(self, namespace=""):
        identifier = f"{namespace}:{self.name}" if namespace else self.name
        number_setting = "" if self.numbers else " (pin_numbers (hide yes))"
        name_visibility = "" if self.names else " (hide yes)"
        on_board = "yes" if self.on_board else "no"
        definitions = [
            f"(symbol {q(identifier)}{number_setting} (pin_names (offset 0.508){name_visibility}) "
            f"(exclude_from_sim no) (in_bom {on_board}) (on_board {on_board})",
            prop("Reference", self.reference, (0, 3.81)),
            prop("Value", self.name, (0, -3.81)),
            prop("Footprint", self.footprint, (0, 0), hide=True),
            prop("Datasheet", self.datasheet, (0, 0), hide=True),
            prop("Description", self.description, (0, 0), hide=True),
        ]
        if self.drawing:
            definitions.append(f"(symbol {q(self.name + '_0_1')} " + "\n".join(self.drawing) + ")")
        definitions.append(f"(symbol {q(self.name + '_1_1')} " + "\n".join(pin.sexpr() for pin in self.pins) + ")")
        return "\n".join(definitions) + ")"


class Schematic:
    """Pin tails are entered in symbol-local y-up coordinates. Wire points are y-down."""

    def __init__(self, project, *, namespace="RelayBoard", title="", revision="0.1", paper="A3", uuid_seed=None):
        self.project = project
        # Filenames may change; preserve the original UUID namespace for CAD links.
        self.uuid_seed = project if uuid_seed is None else uuid_seed
        self.namespace = namespace
        self.title = title
        self.revision = revision
        self.paper = paper
        self.root = uid(f"{self.uuid_seed}/root")
        self.definitions = {}
        self.elements = []
        self.instances = {}
        self.wires = set()
        self.junctions = set()
        self.no_connects = set()
        self.labels = []

    def _uid(self, key):
        return uid(f"{self.uuid_seed}/{key}")

    def define(self, name, reference, pins, drawing, **options):
        if name in self.definitions:
            raise ValueError(f"Duplicate symbol definition {name}")
        numbers = [str(pin.number) for pin in pins]
        if len(numbers) != len(set(numbers)):
            raise ValueError(f"Duplicate pin number on {name}")
        self.definitions[name] = Definition(name, reference, tuple(pins), tuple(drawing), **options)

    def place(self, name, ref, at, *, value=None, angle=0, ref_at=None, value_at=None,
              hide_ref=False, hide_value=False, footprint=None, datasheet=None, fields=None):
        if ref in self.instances:
            raise ValueError(f"Duplicate reference {ref}")
        symbol = self.definitions[name]
        x, y = at
        ref_at = ref_at if ref_at is not None else (x, y - 3.81)
        value_at = value_at if value_at is not None else (x, y + 3.81)
        footprint = symbol.footprint if footprint is None else footprint
        display_value = symbol.name if value is None else value
        on_board = "yes" if symbol.on_board else "no"
        path = q("/" + self.root.strip('"'))
        parts = [
            f"(symbol (lib_id {q(self.namespace + ':' + name)}) (at {xy((x, y, angle))}) (unit 1)",
            f"(exclude_from_sim no) (in_bom {on_board}) (on_board {on_board}) (dnp no) (uuid {self._uid(ref)})",
            prop("Reference", ref, ref_at, hide=hide_ref),
            prop("Value", display_value, value_at, hide=hide_value),
            prop("Footprint", footprint, at, hide=True),
            prop("Datasheet", symbol.datasheet if datasheet is None else datasheet, at, hide=True),
            prop("Description", symbol.description, at, hide=True),
        ]
        for field_name, field_value in (fields or {}).items():
            parts.append(prop(field_name, field_value, at, hide=True))
        radians = math.radians(angle)
        tails = {}
        for pin in symbol.pins:
            number = str(pin.number)
            parts.append(f"(pin {q(number)} (uuid {self._uid(f'{ref}/pin/{number}')}) )")
            sx = pin.x * math.cos(radians) - pin.y * math.sin(radians)
            sy = pin.x * math.sin(radians) + pin.y * math.cos(radians)
            tails[number] = pt(x + sx, y - sy)
        parts.append(f"(instances (project {q(self.project)} (path {path} (reference {q(ref)}) (unit 1))))")
        self.elements.append("\n".join(parts) + ")")
        self.instances[ref] = tails
        return tails

    def pin(self, ref, number):
        return self.instances[ref][str(number)]

    def wire(self, *points):
        for start, end in zip(points, points[1:]):
            start, end = tuple(start), tuple(end)
            if start == end or (start[0] != end[0] and start[1] != end[1]):
                raise ValueError(f"Wire needs distinct points and a right angle route: {start}, {end}")
            key = tuple(sorted((start, end)))
            if key in self.wires:
                raise ValueError(f"Duplicate wire {key}")
            self.wires.add(key)
            self.elements.append(
                f"(wire (pts (xy {xy(start)}) (xy {xy(end)})) {stroke()} (uuid {self._uid(('wire', key))}))"
            )

    def junction(self, at):
        at = tuple(at)
        if at in self.junctions:
            raise ValueError(f"Duplicate junction {at}")
        self.junctions.add(at)
        self.elements.append(
            f"(junction (at {xy(at)}) (diameter 0) (color 0 0 0 0) (uuid {self._uid(('junction', at))}))"
        )

    def no_connect(self, at):
        at = tuple(at)
        if at in self.no_connects:
            raise ValueError(f"Duplicate no-connect {at}")
        self.no_connects.add(at)
        self.elements.append(f"(no_connect (at {xy(at)}) (uuid {self._uid(('no-connect', at))}))")

    def label(self, name, at, *, angle=0, size=1.27):
        at = tuple(at)
        self.labels.append((name, at))
        justify = "right bottom" if angle in (180, 270) else "left bottom"
        self.elements.append(
            f"(label {q(name)} (at {xy((*at, angle))}) {effects(size, justify=justify)} "
            f"(uuid {self._uid(('label', name, at))}))"
        )

    def line(self, *points, width=0.254):
        vertices = " ".join(f"(xy {xy(point)})" for point in points)
        self.elements.append(
            f"(polyline (pts {vertices}) {stroke(width)} (fill (type none)) "
            f"(uuid {self._uid(('polyline', tuple(points)))}))"
        )

    def text(self, value, at, *, size=1.27, justify="left", bold=False):
        self.elements.append(
            f"(text {q(value)} (at {xy((*at, 0))}) {effects(size, justify=justify, bold=bold)} "
            f"(uuid {self._uid(('text', value, tuple(at)))}))"
        )

    def write(self, path, *, with_library=True):
        path = Path(path)
        if self.project != path.stem:
            raise ValueError(f"Project {self.project} must equal schematic filename stem {path.stem}")
        definitions = "\n".join(item.sexpr(self.namespace) for item in self.definitions.values())
        elements = "\n".join(self.elements)
        path.write_text(
            f"(kicad_sch (version 20250114) (generator {q('codex-schematic')}) (generator_version {q('1.0')})\n"
            f"(uuid {self.root}) (paper {q(self.paper)})\n"
            f"(title_block (title {q(self.title)}) (rev {q(self.revision)}))\n"
            f"(lib_symbols\n{definitions}\n)\n{elements}\n"
            f'(sheet_instances (path "/" (page "1")))\n)\n',
            encoding="utf-8",
        )
        if with_library:
            library = path.with_name(self.namespace + ".kicad_sym")
            library.write_text(
                '(kicad_symbol_lib (version 20241209) (generator "codex-schematic")\n'
                + "\n".join(item.sexpr() for item in self.definitions.values())
                + "\n)\n",
                encoding="utf-8",
            )
            table = path.with_name("sym-lib-table")
            if table.exists():
                raise FileExistsError(f"Refusing to overwrite existing library table {table}")
            table.write_text(
                f'(sym_lib_table (version 7) (lib (name {q(self.namespace)}) (type "KiCad") '
                f'(uri {q("${KIPRJMOD}/" + library.name)}) (options "") (descr "Project symbols")))\n',
                encoding="utf-8",
            )
