"""Regenerate the Upper schematic and local symbol library from this project.

Run with Python 3 from any working directory. PCB placement/routing is maintained
separately in the KiCad PCB; component UUIDs remain deterministic by reference.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schematic import Pin, Schematic, pt, rectangle, polyline, circle
from passive_specifications import component_spec

project = "FCPLCN-CPU-08-1v0"
namespace = "RelayStack"
project_root = Path(__file__).resolve().parents[1]
folder = project_root / "FCPLCN-CPU-08-1v0"
pretty = folder / f"{namespace}.pretty"
models = folder / "3d"
pretty.mkdir(parents=True, exist_ok=True)
models.mkdir(exist_ok=True)
schema = Schematic(project, namespace=namespace, title="FCPLCN-CPU-08-1v0", revision="1v0", uuid_seed="WiFi-Relay-16-Upper", paper="A2")

RES = "Resistor_SMD:R_0805_2012Metric"
CAP = "Capacitor_SMD:C_0805_2012Metric"
CAP_LARGE = "Capacitor_SMD:C_1206_3216Metric"
G = "GND"
GI = "GND_ISO"
V5 = "+5V_TMR"
V12 = "+12V_LOGIC"
V3 = "+3V3"
VI5 = "+5V_ISO"
VI3 = "+3V3_ISO"

def box(name, ref, left, right, footprint, *, width=20.32, datasheet=""):
    def pins(rows, x, angle):
        top = (len(rows) - 1) * 2.54 / 2
        return [Pin(num, label, x, top - i * 2.54, angle, kind)
                for i, (num, label, kind) in enumerate(rows)]

    half = width / 2
    height = max(len(left), len(right)) * 2.54 / 2 + 1.27
    schema.define(name, ref, pins(left, -half-2.54, 0) + pins(right, half+2.54, 180),
                  (rectangle((-half, height), (half, -height)),),
                  footprint=footprint, datasheet=datasheet)
    return height

def rows(pairs, kind="passive"):
    return [(num, name, kind) for num, name in pairs]

def component(symbol, ref, at, signals, *, height=None, value=None, footprint=None, distance=5.08, datasheet=None, fields=None):
    x, y = at
    def note_position(delta):
        return (x, y - height - delta) if height else None

    schema.place(symbol, ref, at, value=value, footprint=footprint, datasheet=datasheet, fields=fields,
                 ref_at=note_position(3.81), value_at=note_position(1.27))
    for pin in schema.definitions[symbol].pins:
        num = str(pin.number)
        tail = schema.pin(ref, num)
        if num not in signals:
            schema.no_connect(tail)
            continue
        direction = -1 if pin.x < 0 else 1
        end = pt(tail[0] + direction * distance, tail[1])
        schema.wire(tail, end)
        schema.label(signals[num], end, angle=180 if direction < 0 else 0, size=1.03)

def passive(symbol, ref, value, x, y, a, b, *, footprint=None, datasheet=None, fields=None, separate_text=False):
    # Purchasing specifications affect metadata only; keep schematic geometry and nets.
    spec = component_spec("Upper", ref)
    if spec:
        value = spec["value"]
        fields = {**(fields or {}), **spec["fields"]}
        if "datasheet" in spec:
            datasheet = spec["datasheet"]
    schema.place(symbol, ref, (x,y), value=value, footprint=footprint, datasheet=datasheet, fields=fields,
                 ref_at=(x,y-3.0) if separate_text else (x-3.3,y-2.2),
                 value_at=(x,y+3.0) if separate_text else (x+4.2,y-2.2))
    for n, net, delta in [(1,a,-3.81),(2,b,3.81)]:
        at = schema.pin(ref,n)
        end = pt(at[0]+delta,at[1])
        schema.wire(at,end)
        schema.label(net,end,angle=180 if delta < 0 else 0,size=1.0)

def power_passive(*args, **kwargs):
    passive(*args, **kwargs, separate_text=True)

def flag(ref, x, y, net):
    schema.place("PWR_FLAG", ref, (x,y), hide_ref=True, hide_value=True)
    pin = schema.pin(ref,1)
    end = pt(pin[0],pin[1]+2.54)
    schema.wire(pin,end)
    schema.label(net,end,size=1.0)

def heading(name, x, y, width):
    schema.text(name, (x,y), size=2.05, bold=True)
    schema.line((x,y+2.35),(x+width,y+2.35),width=0.25)

schema.define("R", "R", (Pin("1","~",-3.81,0,0,length=1.27), Pin("2","~",3.81,0,180,length=1.27)),
              (rectangle((-2.54,0.8),(2.54,-0.8),fill="none"),), names=False, numbers=False, footprint=RES)
schema.define("C", "C", (Pin("1","~",-3.81,0,0,length=3.175), Pin("2","~",3.81,0,180,length=3.175)),
              (polyline((-0.635,-1.52),(-0.635,1.52)), polyline((0.635,-1.52),(0.635,1.52))),
              names=False, numbers=False, footprint=CAP)
schema.define("L", "L", (Pin("1","~",-3.81,0,0,length=1.27), Pin("2","~",3.81,0,180,length=1.27)),
              (polyline((-2.54,0),(-2.54,0.6),(-1.905,1.27),(-1.27,0.6),(-0.635,1.27),(0,0.6),
                        (0.635,1.27),(1.27,0.6),(1.905,1.27),(2.54,0.6),(2.54,0)),),
              names=False, numbers=False, footprint="Inductor_SMD:L_Bourns_SRP5030T")
schema.define("D_Schottky", "D", (Pin("1","K",-3.81,0,0,length=2.54), Pin("2","A",3.81,0,180,length=2.54)),
              (polyline((1.27,-1.27),(-1.27,0),(1.27,1.27),(1.27,-1.27)),
               polyline((-1.9,1.27),(-1.27,1.27),(-1.27,-1.27),(-0.635,-1.27))),
              names=False, numbers=False, footprint="Diode_SMD:D_SMA",
              datasheet="https://www.diodes.com/datasheet/download/B340A.pdf")
schema.define("SW", "SW", (Pin("1","~",-3.81,0,0,length=2.54), Pin("2","~",3.81,0,180,length=2.54)),
              (circle((-1.27,0),0.275),circle((1.27,0),0.275),polyline((-1.65,0.85),(1.65,0.85)),
               polyline((0,0.85),(0,1.75))), names=False, numbers=False, footprint="RelayStack:SW_SPST_TS-1088-xR020",
              datasheet="https://lcsc.com/datasheet/lcsc_datasheet_2504101957_XUNPU-TS-1088-AR02016_C720477.pdf")
schema.define("PWR_FLAG", "#FLG", (Pin("1","~",0,0,90,"power_out",0),),
              (polyline((0,0),(0,1.27),(-1.02,2.03),(0,2.79),(1.02,2.03),(0,1.27)),),
              names=False, numbers=False, on_board=False)

wroom_pins = {
    "1":"GND","2":"3V3","3":"EN","4":"IO4","5":"IO5","6":"IO6","7":"IO7","8":"IO15",
    "9":"IO16","10":"IO17","11":"IO18","12":"IO8","13":"IO19","14":"IO20","15":"IO3","16":"IO46",
    "17":"IO9","18":"IO10","19":"IO11","20":"IO12","21":"IO13","22":"IO14","23":"IO21",
    "24":"IO47","25":"IO48","26":"IO45","27":"IO0","28":"IO35","29":"IO36","30":"IO37",
    "31":"IO38","32":"IO39","33":"IO40","34":"IO41","35":"IO42","36":"RXD0","37":"TXD0",
    "38":"IO2","39":"IO1","40":"GND","41":"EPAD"
}
used_wroom = {
    "1":G, "2":V3, "3":"ESP_EN", "10":"DATA3_CPU", "11":"DATA4_CPU", "39":"DATA5_CPU", "38":"DATA6_CPU", "4":"I2C_SDA", "5":"I2C_SCL", "6":"MCP_RESET_N", "7":"NET_LED", "8":"STATUS_LED", "9":"ALARM_LED",
    "13":"USB_DN_CPU", "14":"USB_DP_CPU", "17":"ETH_CS_CPU", "18":"ETH_SCK_CPU", "19":"ETH_MOSI_CPU",
    "20":"ETH_MISO_CPU", "21":"ETH_INT_N", "22":"ETH_RST_N", "23":"USB_VBUS_SENSE", "27":"ESP_BOOT",
    "31":"DATA7_CPU", "36":"DATA8_CPU", "32":"DATA1_CPU", "33":"DATA2_CPU", "34":"ISO_SDA_CPU", "35":"ISO_SCL_CPU", "40":G, "41":G, "12":"RS485_TX_CPU", "24":"RS485_RX_CPU", "25":"RS485_DIR_CPU"
}
wroom_types = {"1":"power_in","2":"power_in","3":"input","40":"power_in","41":"power_in",
               "4":"bidirectional","5":"bidirectional","6":"output","7":"output","8":"output","9":"output",
               "13":"bidirectional","14":"bidirectional","17":"output","18":"output","19":"output",
               "20":"input","21":"input","22":"output","23":"input","27":"input","32":"bidirectional",
               "33":"bidirectional","34":"bidirectional","35":"bidirectional","12":"output","24":"input","25":"output"}
left_nums = list(range(1,8)) + [12,13,14,15,16] + list(range(17,24)) + [40,41]
right_nums = [32,33,34,35,27] + list(range(8,12)) + list(range(24,27)) + list(range(28,32)) + list(range(36,40))
def gpio_rows(numbers):
    return [(str(n),wroom_pins[str(n)],wroom_types.get(str(n),"bidirectional")) for n in numbers]
h = box("ESP32-S3-WROOM-1U","U",gpio_rows(left_nums),gpio_rows(right_nums),f"{namespace}:ESP32-S3-WROOM-1U_PTH030",
        width=30.48,datasheet="https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf")
heading("ESP32-S3 · external 2.4 GHz antenna",14.0,19,103)
component("ESP32-S3-WROOM-1U","U1",(68.58,62.23),used_wroom,height=h,fields={"MPN":"ESP32-S3-WROOM-1U-N16R8","Manufacturer":"Espressif Systems"})
passive("C","C5","10uF",43.18,99.06,V3,G,footprint=CAP_LARGE)
passive("C","C6","100nF",91.44,99.06,V3,G)
schema.text("Native USB serial/JTAG · no external JTAG on GPIO39–42", (14,105), size=1.12)

h=box("W5500-Lite","U",rows([("2.1","GND"),("2.2","3V3"),("2.3","3V3"),("2.4","NC")])
      +[("2.5","RST_N","input"),("2.6","MISO","output")],
      rows([("1.1","GND"),("1.2","GND")])+[("1.3","MOSI","input"),("1.4","SCK","input"),("1.5","CS_N","input"),("1.6","INT_N","output")],
      f"{namespace}:W5500_Lite_2x6",datasheet="https://www.pusr.com/download/ES1/USR-ES1_sch.pdf")
heading("W5500 Lite · RJ45 toward DI terminals",125.73,19,129)
component("W5500-Lite","U2",(163.83,45.72),{
    "2.1":G,"2.2":V3,"2.3":V3,"2.5":"ETH_RST_F","2.6":"ETH_MISO",
    "1.1":G,"1.2":G,"1.3":"ETH_MOSI","1.4":"ETH_SCK","1.5":"ETH_CS_N","1.6":"ETH_INT_N",
},height=h)
passive("C","C8","10uF",147.32,62.23,V3,G,footprint=CAP_LARGE)
passive("C","C9","100nF",180.34,62.23,V3,G)
passive("R","R3","1k",223.52,40.64,"ETH_RST_N",G)
passive("R","R4","470",223.52,50.8,"ETH_RST_N","ETH_RST_F")
passive("C","C10","10nF",223.52,62.23,"ETH_RST_F",G)
for ref, y, a, b in [
    ("R5",73.66,"ETH_CS_CPU","ETH_CS_N"),("R6",81.28,"ETH_SCK_CPU","ETH_SCK"),
    ("R7",88.9,"ETH_MOSI_CPU","ETH_MOSI"),("R8",96.52,"ETH_MISO","ETH_MISO_CPU")
]:
    passive("R",ref,"22",180.34,y,a,b)
schema.text("Assert reset for ≥1 ms. Wait ≥2 ms before SPI.", (125.73,105), size=1.12)

h=box("USB_C_HBXINTAO_16PIN_DIP","J",rows([("A1","GND"),("A4","VBUS"),("A5","CC1"),("A6","DP1"),("A7","DN1"),
                         ("A8","SBU1"),("A9","VBUS"),("A12","GND"),("SH","Shield")]),
      rows([("B1","GND"),("B4","VBUS"),("B5","CC2"),("B6","DP2"),("B7","DN2"),("B8","SBU2"),("B9","VBUS"),("B12","GND")]),
      f"{namespace}:USB_C_Receptacle_HBXINTAO16PIN_DIP_Vertical",width=22.86,
      datasheet="https://connectorscn.com/wp-content/uploads/2026/10/b16-detail-5-4.webp")
heading("USB-C · all through-hole · service / programming",266.7,19,135)
component("USB_C_HBXINTAO_16PIN_DIP","J2",(297.18,45.72),{
    "A1":G,"A4":"USB_VBUS","A5":"USB_CC1","A6":"USB_DP","A7":"USB_DN","A9":"USB_VBUS","A12":G,"SH":G,
    "B1":G,"B4":"USB_VBUS","B5":"USB_CC2","B6":"USB_DP","B7":"USB_DN","B9":"USB_VBUS","B12":G,
},height=h,value="HBXINTAO 16PIN DIP",fields={
    "MPN":"16PIN", "Manufacturer":"HBXINTAO", "SupplierPartNumber":"1005004175942555 / SKU 12000028287569580",
    "SourceURL":"https://aliexpress.ru/item/1005004175942555.html?sku_id=12000028287569580"})
srda_datasheet="https://www.littelfuse.com/assetdocs/tvs-diode-array-spa-srda05-datasheet?assetguid=5e6854f4-4140-4034-b7b2-d3793470da22"
h_esd=box("SRDA05-4BTG","D",rows([("1","IO1"),("4","IO2"),("6","IO3"),("7","IO4")]),
          rows([("2","REF1"),("3","REF1"),("5","REF2"),("8","REF2")]),
          "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",width=15.24,datasheet=srda_datasheet)
def srda(ref, at, channels, ground, reference):
    signals={"2":reference,"3":reference,"5":ground,"8":ground}
    signals.update(dict(zip(("1","4","6","7"),channels)))
    component("SRDA05-4BTG",ref,at,signals,height=h_esd,
              footprint="RelayStack:SOIC8_SRDA_USB_Clearance" if ref=="D1" else None,
              fields={"MPN":"SRDA05-4BTG","Manufacturer":"Littelfuse"})
def ic_field(net):
    assert net.endswith("_ISO")
    return net[:-4]+"_IC_ISO"
def field_series(ref, net, x, y):
    passive("R",ref,"100R",x,y,net,ic_field(net),
            fields={"MPN":"CRCW0805100RFKTAHP","Manufacturer":"Vishay","Tolerance":"1%","PowerRating":"0.5 W","ResistorType":"Pulse-withstanding"},
            datasheet="https://www.vishay.com/docs/20115/crcwhp.pdf")
srda("D1",(373.38,46.99),(G,G,"USB_DN","USB_DP"),G,"TVS_USB_REF")
for ref,val,x,y,a,b in [
    ("R9","5.1k",298.45,67.31,"USB_CC1",G),("R10","5.1k",298.45,76.2,"USB_CC2",G),
    ("R11","22",298.45,85.09,"USB_DN","USB_DN_CPU"),("R12","22",298.45,93.98,"USB_DP","USB_DP_CPU"),
    ("R13","68k",370.84,67.31,"USB_VBUS","USB_VBUS_SENSE"),("R14","100k",370.84,76.2,"USB_VBUS_SENSE",G)
]:
    passive("R",ref,val,x,y,a,b)
schema.text("Power from base board. USB VBUS used only for sensing.", (266.7,105), size=1.12)

# Three-pin switching modules replace the discrete main buck and isolated LDO.
r78_footprint = f"{namespace}:RECOM_R-78K3.3-1.0_SIP3_P2.54mm"
r78_datasheet = "https://recom-power.com/pdf/Innoline/R-78K-1.0.pdf"
h_r78=box("R-78K","U",[("1","VIN","power_in"),("2","GND","power_in")],
          [("3","VOUT","power_out")],r78_footprint,width=25.4,datasheet=r78_datasheet)
# Local, nonisolated 5 V supply feeds the TMR input only. No 5 V stack rail.
h_r78e=box("R-78E5V","U",[("1","VIN","power_in"),("2","GND","power_in")],
           [("3","VOUT","power_out")],f"{namespace}:RECOM_R-78E_PSE",width=25.4,
           datasheet="https://recom-power.com/pdf/Innoline/R-78E-1.0.pdf")
heading("Local TMR supply · protected 12 V to 5 V / 1 A",425.45,810.96,152.4)
component("R-78E5V","U17",(499.11,833.12),{"1":V12,"2":G,"3":V5},height=h_r78e,
          value="R-78E5.0-1.0",fields={"MPN":"R-78E5.0-1.0","Manufacturer":"RECOM",
          "InputVoltage":"8–28 V", "OutputCurrent":"1 A"})
power_passive("C","C54","10uF",447.04,857.25,V12,G,footprint=CAP_LARGE)
power_passive("C","C55","100nF",497.84,857.25,V12,G)
power_passive("C","C56","100nF",548.64,857.25,V5,G)
schema.text("C11 is the local 5 V bulk bypass at TMR input U4.", (425.45,880.11), size=1.1)
schema.text("Left stack pins 1–4 are GND; 5 V and 3.3 V stay local.", (425.45,887.73), size=1.1)
heading("Main power · protected 12 V to 3.3 V / 1 A",425.45,218.44,152.4)
component("R-78K","U3",(499.11,240.03),{"1":V12,"2":G,"3":V3},height=h_r78,
          value="R-78K3.3-1.0",fields={"MPN":"R-78K3.3-1.0","Manufacturer":"RECOM",
          "InputVoltage":"4.5–36 V", "OutputCurrent":"1 A"})
power_passive("C","C1","10uF 35V",447.04,261.62,V12,G,footprint=CAP_LARGE,
          fields={"Voltage":"35 V"})
cout_datasheet="https://product.tdk.com/en/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c3216x5r1v226m160ac.pdf"
for cref, x in [("C3",447.04),("C4",497.84)]:
    power_passive("C",cref,"22uF 35V X5R",x,279.4,V3,G,footprint=CAP_LARGE,
            datasheet=cout_datasheet,
            fields={"MPN":"C3216X5R1V226M160AC","Manufacturer":"TDK","Tolerance":"20%"})
power_passive("C","C33","100nF 50V",548.64,261.62,V12,G,fields={"Voltage":"50 V"})
schema.text("Independent 12 V main and RS-485 branches; 5 V feeds TMR.", (425.45,304.8), size=1.1)
schema.text("Keep input / output decoupling close to the R-78K module.", (425.45,312.42), size=1.1)
schema.text("Budget: main 3.3 V 902 mA; module output rated 1 A.", (425.45,320.04), size=1.1)
flag("#FLG02",497.84,337.82,G)
flag("#FLG03",548.64,337.82,V12)

h=box("StackBus-2x3","J",
      rows([("1","GND"),("3","VIN"),("5","SIG A")]),
      rows([("2","GND"),("4","VIN"),("6","SIG B")]),
      f"{namespace}:StackHeader_2x03_P2.54mm_Bottom",width=25.4)
heading("Main board interface · reset and boot",125.73,115,129)
component("StackBus-2x3","J1",(166.37,132.08),
          {"1":G,"2":G,"3":G,"4":G,"5":"I2C_SDA","6":"I2C_SCL"},
          height=h,value="LEFT · GND / I2C")
component("StackBus-2x3","J6",(166.37,154.94),
          {"1":G,"2":G,"3":V12,"4":V12,"5":"MCP_RESET_N","6":G},
          height=h,value="RIGHT · 12V / CTRL")
passive("R","R1","10k",223.52,133.35,V3,"ESP_EN")
passive("C","C7","1uF",223.52,142.24,"ESP_EN",G)
passive("SW","SW1","RESET",223.52,151.13,"ESP_EN",G)
passive("R","R2","10k",223.52,165.1,V3,"ESP_BOOT")
passive("SW","SW2","BOOT",223.52,173.99,"ESP_BOOT",G)
schema.text("Base board powers MCP23017 and provides the I²C pull-ups.", (125.73,187), size=1.12)

h=box("TMR-1-0511","U",[("2","+VIN","power_in"),("1","−VIN","power_in")],
      [("4","+VOUT","power_out"),("6","−VOUT","power_out")],f"{namespace}:TMR1_SIP6",width=25.4,
      datasheet="https://www.tracopower.com/sites/default/files/products/datasheets/tmr1_datasheet.pdf")
heading("Sensor power · isolated 5 V and 3.3 V",266.7,115,135)
component("TMR-1-0511","U4",(304.8,138.43),{"2":V5,"1":G,"4":VI5,"6":GI},height=h)
component("R-78K","U5",(370.84,138.43),{"1":VI5,"2":GI,"3":VI3},height=h_r78,
          value="R-78K3.3-0.5",footprint=f"{namespace}:RECOM_R-78K3.3-0.5_SIP3_P2.54mm",datasheet="https://recom-power.com/pdf/Innoline/R-78K-0.5.pdf",
          fields={"MPN":"R-78K3.3-0.5","Manufacturer":"RECOM", "InputVoltage":"4.5–36 V", "OutputCurrent":"0.5 A"})
passive("C","C11","10uF",298.45,157.48,V5,G,footprint=CAP_LARGE)
passive("C","C12","10uF",349.25,157.48,VI5,GI,footprint=CAP_LARGE)
passive("C","C13","10uF",349.25,166.37,VI3,GI,footprint=CAP_LARGE)
schema.text("Keep the isolated ground separate across the stack.", (266.7,187), size=1.12)

h_iso=box("ISO1640BDR","U",[("1","VCC1","power_in"),("2","SDA1","bidirectional"),
         ("3","SCL1","bidirectional"),("4","GND1","power_in")],
         [("8","VCC2","power_in"),("7","SDA2","bidirectional"),
         ("6","SCL2","bidirectional"),("5","GND2","power_in")],"Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
         width=25.4,datasheet="https://www.ti.com/lit/ds/symlink/iso1640.pdf")
for n, name, labels in [
    (3,"DATA-Terminal",[("1","5V"),("2","DATA"),("3","GND")]),
    (4,"I2C-Terminal",[("1","3V3"),("2","SDA"),("3","SCL"),("4","GND")])
]:
    box(name,"J",rows(labels),[],f"{namespace}:KF128-2.54-{n}P",width=12.7)
heading("DATA1/2 isolation · shared 10-pin terminal",14.0,199,194)
heading("Isolated I²C · 3.3 V field bus",214.63,199,187)

for section, unit, x, cpu1, cpu2, field1, field2, field_voltage, r0, c0 in [
    ("DATA","U6",66.04,"DATA1_CPU","DATA2_CPU","DATA1_ISO","DATA2_ISO",VI5,15,14),
    ("I2C","U7",266.7,"ISO_SDA_CPU","ISO_SCL_CPU","SDA_ISO","SCL_ISO",VI3,19,18)
]:
    component("ISO1640BDR",unit,(x,222.25),
              {"1":V3,"2":cpu1,"3":cpu2,"4":G,"5":GI,"6":ic_field(field2),"7":ic_field(field1),"8":field_voltage},height=h_iso,
              fields={"MPN":"ISO1640BDR", "Manufacturer":"Texas Instruments"})
    if section == "DATA":
        srda("D2",(x+57.15,213.36),tuple(f"DATA{i}_ISO" for i in range(1,5)),GI,"TVS_DATA14_REF_ISO")
    else:
        srda("D3",(x+57.15,222.25),("SDA_ISO","SCL_ISO",GI,GI),GI,"TVS_I2C_REF_ISO")
    for index,net in enumerate((field1,field2)):
        field_series(f"R{61+index if section=='DATA' else 69+index}",net,x+78.74,255.27+index*7.62)
    for index,(net,voltage) in enumerate([(cpu1,V3),(cpu2,V3),(ic_field(field1),field_voltage),(ic_field(field2),field_voltage)]):
        px=x-25.4 + (index//2)*48.26
        py=240.03 + (index%2)*7.62
        passive("R",f"R{r0+index}","4.3k" if index<2 else "4.7k",px,py,voltage,net,
                fields={"Tolerance":"1%" if index<2 else "5%"})
    for index,(voltage,ground) in enumerate([(V3,G),(V3,G),(field_voltage,GI),(field_voltage,GI)]):
        px=x-25.4 + (index//2)*(38.1 if section == "I2C" else 48.26)
        py=255.27 + (index%2)*7.62
        passive("C",f"C{c0+index}","100nF" if index%2==0 else "1nF",px,py,voltage,ground)

h_data10=box("DATA-Terminal-10P","J",rows([(str(i),f"DATA{i}") for i in range(1,9)]+[("9","5V"),("10","GND")]),[],f"{namespace}:KF128-2.54-10P",width=22.86)
component("DATA-Terminal-10P","J3",(177.8,232.41),{**{str(i):f"DATA{i}_ISO" for i in range(1,9)},"9":VI5,"10":GI},height=h_data10,value="DATA1–8 / 5V / GND")
component("I2C-Terminal","J5",(383.54,222.25),{"1":VI3,"2":"SDA_ISO","3":"SCL_ISO","4":GI},height=6.35,value="I²C")
schema.text("Use 3-wire, externally powered sensors and open-drain GPIO.", (14.0,272), size=1.12)
schema.text("TVS on connector side; 100R then isolator + 4.7k pull-up.", (14.0,277), size=1.12)
schema.text("The field bus and base-board I²C use separate GPIO pairs.", (214.63,272), size=1.12)


# Additional isolated DATA channels, routed to direct ESP32 GPIO17/18, GPIO1/2 and GPIO38/44.
heading("Additional isolated DATA ports · GPIO17 / GPIO18",14.0,301,194)
heading("Additional isolated DATA ports · GPIO1 / GPIO2",214.63,301,187)
heading("DATA7/8 isolation · GPIO38 / GPIO44",425.45,343,152.4)
for unit, x, cpu1, cpu2, field1, field2, r0, c0 in [
    ("U8",66.04,"DATA3_CPU","DATA4_CPU","DATA3_ISO","DATA4_ISO",33,22),
    ("U9",266.7,"DATA5_CPU","DATA6_CPU","DATA5_ISO","DATA6_ISO",37,26),
    ("U15",476.25,"DATA7_CPU","DATA8_CPU","DATA7_ISO","DATA8_ISO",57,48)
]:
    dy = 33.02 if unit == "U15" else 0.0
    component("ISO1640BDR",unit,(x,323.85+dy),
              {"1":V3,"2":cpu1,"3":cpu2,"4":G,"5":GI,"6":ic_field(field2),"7":ic_field(field1),"8":VI5},height=h_iso,
              fields={"MPN":"ISO1640BDR", "Manufacturer":"Texas Instruments"})
    if unit == "U9":
        srda("D6",(x+57.15,323.85),tuple(f"DATA{i}_ISO" for i in range(5,9)),GI,"TVS_DATA58_REF_ISO")
    for index,net in enumerate((field1,field2)):
        series_base={"U8":63,"U9":65,"U15":67}[unit]
        field_series(f"R{series_base+index}",net,x+78.74,356.87+dy+index*7.62)
    for index,(net,voltage) in enumerate([(cpu1,V3),(cpu2,V3),(ic_field(field1),VI5),(ic_field(field2),VI5)]):
        px=x-25.4 + (index//2)*48.26
        py=341.63 + (index%2)*7.62 + dy
        passive("R",f"R{r0+index}","4.3k" if index<2 else "4.7k",px,py,voltage,net,
                fields={"Tolerance":"1%" if index<2 else "5%"})
    for index,(voltage,ground) in enumerate([(V3,G),(V3,G),(VI5,GI),(VI5,GI)]):
        px=x-25.4 + (index//2)*48.26
        py=356.87 + (index%2)*7.62 + dy
        passive("C",f"C{c0+index}","100nF" if index%2==0 else "1nF",px,py,voltage,ground,
                footprint="RelayStack:C0805_C50_Clearance" if c0+index==50 else None)
schema.text("GPIO44 is DATA8; keep UART0 RX disabled.", (425.45,405), size=1.12)
schema.text("SRDA REF1 pins 2/3: local floating node; never connect to supply.", (14.0,374), size=1.12)
schema.text("REF2 pins 5/8: local GND. FIELD TVS uses GND_ISO only.", (14.0,379), size=1.12)


heading("Front-panel indicators",425.45,19,152.4)
h_led=box("PanelLED-1x5","J",rows([("1","NET"),("2","PWR"),("3","STATUS"),("4","ALARM"),("5","GND")]),
          [],"Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",width=30.48)
component("PanelLED-1x5","J7",(464.82,43.18),
          {"1":"LED_NET_OUT","2":"LED_PWR_OUT","3":"LED_STATUS_OUT","4":"LED_ALARM_OUT","5":G},
          height=h_led,value="NET / PWR / STATUS / ALARM / GND")
h_bjt=box("BC807-40","Q",[("1","B","input"),("2","E","passive")],
          [("3","C","passive")],"Package_TO_SOT_SMD:SOT-23",width=20.32,
          datasheet="https://assets.nexperia.com/documents/data-sheet/BC807_SER.pdf")
for n,signal,y in [(1,"NET",99.06),(2,"STATUS",137.16),(3,"ALARM",175.26)]:
    component("BC807-40",f"Q{n}",(499.11,y),
              {"1":f"LED_{signal}_BASE","2":V3,"3":f"LED_{signal}_DRIVE"},height=h_bjt)
    passive("R",f"R{26+n}","4.7k",438.15,y,f"{signal}_LED",f"LED_{signal}_BASE")
    passive("R",f"R{29+n}","100k",438.15,y+11.43,f"LED_{signal}_BASE",V3)
for n,signal,y in [(23,"NET",29.21),(24,"PWR",40.64),(25,"STATUS",52.07),(26,"ALARM",63.5)]:
    passive("R",f"R{n}","470R",551.18,y,V3 if signal == "PWR" else f"LED_{signal}_DRIVE",f"LED_{signal}_OUT")
srda("D4",(556.26,119.38),("LED_NET_OUT","LED_STATUS_OUT","LED_ALARM_OUT","LED_PWR_OUT"),G,"TVS_LED_REF")
schema.text("PWR follows 3.3 V. Other LEDs are active LOW at GPIO7 / 15 / 16.",(425.45,194.31),size=1.1)
schema.text("LED anodes use NET / PWR / STATUS / ALARM, all cathodes use GND.",(425.45,201.93),size=1.1)

# Local time survives loss of board power. This is the primary I2C bus shared
# with the base-board MCP23017 devices; it is not the isolated sensor bus.
heading("Battery-backed RTC · DS3231MZ+ / CR1220",14.0,115,103.0)
h_rtc=box("DS3231MZ+","U",[("8","SCL","input"),("7","SDA","bidirectional"),
          ("1","32KHZ","open_collector"),("3","INT/SQW","open_collector")],
          [("2","VCC","power_in"),("6","VBAT","power_in"),
           ("4","RST","bidirectional"),("5","GND","power_in")],
          "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",width=25.4,
          datasheet="https://www.analog.com/media/en/technical-documentation/data-sheets/DS3231M.pdf")
component("DS3231MZ+","U10",(50.8,143.51),
          {"2":"RTC_VCC","5":G,"6":"RTC_VBAT","7":"I2C_SDA","8":"I2C_SCL"},height=h_rtc,
          fields={"MPN":"DS3231MZ+","Manufacturer":"Analog Devices"})
h_battery=box("CR1220-2","BT",[("1","+","power_out")],[("2","−","passive")],
              f"{namespace}:BatteryHolder_QJ_CR1220-2_C70381",width=17.78,
              datasheet="https://atta.szlcsc.com/upload/public/pdf/source/20240508/105D3BE3DF78AB74B6E639FC10A0C203.pdf")
component("CR1220-2","BT1",(100.33,143.51),{"1":"RTC_VBAT","2":G},height=h_battery,
          fields={"MPN":"CR1220-2","Manufacturer":"Q&J","SupplierPartNumber":"C70381",
                  "SourceURL":"https://jlcpcb.com/partdetail/QJ-CR12202/C70381"})
passive("C","C34","100nF",38.1,165.1,"RTC_VCC",G,footprint=CAP_LARGE)
passive("R","R46","470R",87.63,165.1,V3,"RTC_VCC",fields={"Tolerance":"1%"})
passive("C","C35","1nF C0G",38.1,179.07,"RTC_VBAT",G)
power_passive("C","C36","22uF 35V X5R",87.63,179.07,"RTC_VCC",G,footprint=CAP_LARGE,datasheet=cout_datasheet,
        fields={"MPN":"C3216X5R1V226M160AC","Manufacturer":"TDK","Tolerance":"20%"})
flag("#FLG04",110.49,124.46,"RTC_VCC")
schema.text("0x68; main I²C. CR1220 primary cell; no charger.",(14.0,190.5),size=1.1)


# Dedicated RS-485 supply keeps the existing main 3.3 V current budget intact.
V485="+3V3_RS485"
heading("RS-485 · ADM2687E · UART1 / GPIO8 TX, GPIO47 RX, GPIO48 DIR",14,411,566)
h_485=box("ADM2687E","U",[("1","GND1","power_in"),("2","VCC","power_in"),("3","RxD","output"),("4","RE_N","input"),("5","DE","input"),("6","TxD","input"),("7","VCC","power_in"),("8","GND1","power_in")],
 [("16","GND2","power_in"),("15","VISOIN","power_in"),("14","A","input"),("13","B","input"),("12","Z","tri_state"),("11","Y","tri_state"),("10","VISOOUT","power_out"),("9","GND2","power_in")],
 f"{namespace}:ADM2687E_SOIC_IC_16_7.5x12.75mm_P1.27mm",width=33.02,datasheet="https://www.analog.com/media/en/technical-documentation/data-sheets/adm2682e-adm2687e.pdf")
component("ADM2687E","U11",(91.44,445.77),{"1":G,"2":V485,"3":"RS485_RX_RAW","4":"RS485_DIR","5":"RS485_DIR","6":"RS485_TX","7":V485,"8":G,
 "9":GI,"10":"RS485_VISO_OUT","11":"RS485_A","12":"RS485_B","13":"RS485_B","14":"RS485_A","15":"RS485_VISO","16":GI},height=h_485,fields={"MPN":"ADM2687EBRIZ","Manufacturer":"Analog Devices"})
component("R-78K","U12",(267.97,445.77),{"1":V12,"2":G,"3":V485},height=h_r78,
          value="R-78K3.3-0.5",footprint=f"{namespace}:RECOM_R-78K3.3-0.5_SIP3_P2.54mm",datasheet="https://recom-power.com/pdf/Innoline/R-78K-0.5.pdf",
          fields={"MPN":"R-78K3.3-0.5","Manufacturer":"RECOM", "InputVoltage":"4.5–36 V", "OutputCurrent":"0.5 A"})
h_buf=box("74LVC125AD","U",[("1","1OE_N","input"),("2","1A","input"),("4","2OE_N","input"),("5","2A","input"),("7","GND","power_in"),("9","3A","input"),("12","4A","input")],
 [("14","VCC","power_in"),("3","1Y","tri_state"),("6","2Y","tri_state"),("8","3Y","tri_state"),("10","3OE_N","input"),("11","4Y","tri_state"),("13","4OE_N","input")],
 "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",width=25.4,datasheet="https://assets.nexperia.com/documents/data-sheet/74LVC125A.pdf")
component("74LVC125AD","U13",(201.93,445.77),{'1': '+3V3_RS485', '2': 'GND', '4': 'GND', '5': 'GND', '7': 'GND', '8': 'RS485_DIR_BUF', '9': 'RS485_DIR_CPU', '10': 'GND', '11': 'RS485_TX_BUF', '12': 'RS485_TX_CPU', '13': 'GND', '14': '+3V3_RS485'},height=h_buf,value="74LVC125AD,118",fields={"MPN":"74LVC125AD,118","Manufacturer":"Nexperia"})
component("74LVC125AD","U14",(345.44,445.77),{"1":G,"2":"RS485_RX_RAW","3":"RS485_RX_BUF","4":V3,"5":G,"7":G,"9":G,"10":V3,"12":G,"13":V3,"14":V3},height=h_buf,value="74LVC125AD,118",fields={"MPN":"74LVC125AD,118","Manufacturer":"Nexperia"})
h_j485=box("RS485-Terminal-4P","J",rows([("1","5V_ISO"),("2","A / D+"),("3","B / D-"),("4","GND_ISO")]),[],f"{namespace}:KF128-2.54-4P",width=27.94)
component("RS485-Terminal-4P","J8",(537.21,445.77),{"1":VI5,"2":"RS485_A","3":"RS485_B","4":GI},height=h_j485,value="RS-485 / 5V A B G")
h_smtvs=box("SM712","D",rows([("1","A"),("2","B")]),rows([("3","GND")]),"Package_TO_SOT_SMD:SOT-23",width=15.24,datasheet="https://www.bourns.com/docs/product-datasheets/cdsot23-sm712.pdf")
component("SM712","D9",(417.83,445.77),{"1":"RS485_A","2":"RS485_B","3":GI},height=h_smtvs,fields={"MPN":"CDSOT23-SM712","Manufacturer":"Bourns"})
for ref,value,x,y,a,b,tol in [
 ("R47","22R",48.26,487.68,"RS485_TX_BUF","RS485_TX","1%"),
 ("R48","22R",163.83,487.68,"RS485_DIR_BUF","RS485_DIR","1%"),
 ("R49","22R",279.4,487.68,"RS485_RX_BUF","RS485_RX_CPU","1%"),
 ("R50","47k",48.26,505.46,V3,"RS485_TX_CPU","1%"),
 ("R51","10k",163.83,505.46,"RS485_DIR_CPU",G,"1%"),
 ("R52","10k",279.4,505.46,"RS485_RX_CPU",V3,"1%"),
 ("R53","120R 0.25W",420.37,487.68,"RS485_A","RS485_TERM","1%"),
 ("R54","47k",48.26,568.96,V485,"RS485_TX","1%"),
 ("R55","47k",163.83,568.96,"RS485_DIR",G,"1%"),
 ("R56","47k",279.4,568.96,V485,"RS485_RX_RAW","1%")]:
    power_passive("R",ref,value,x,y,a,b,footprint="Resistor_SMD:R_1206_3216Metric" if ref=="R53" else RES,fields={"Tolerance":tol})
h_jp=box("Jumper-2P","JP",rows([("1","1")]),rows([("2","2")]),"Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",width=12.7)
component("Jumper-2P","JP2",(539.75,487.68),{"1":"RS485_TERM","2":"RS485_B"},height=h_jp,value="TERM / normally open")
for ref,value,x,y,a,b in [
 ("C37","22uF 35V X5R",48.26,528.32,V12,G),("C38","10uF",163.83,528.32,V485,G),
 ("C39","100nF",279.4,528.32,V485,G),("C40","100nF",394.97,528.32,V485,G),
 ("C41","10uF",48.26,548.64,"RS485_VISO_OUT",GI),("C42","100nF",163.83,548.64,"RS485_VISO_OUT",GI),
 ("C43","100nF",279.4,548.64,"RS485_VISO",GI),("C44","10nF",394.97,548.64,"RS485_VISO",GI)]:
    cap_fields={"MPN":"C3216X5R1V226M160AC","Manufacturer":"TDK","Tolerance":"20%"} if ref=="C37" else None
    cap_ds=cout_datasheet if ref=="C37" else None
    power_passive("C",ref,value,x,y,a,b,footprint=CAP_LARGE if ref in ("C37","C38","C41") else CAP,datasheet=cap_ds,fields=cap_fields)
power_passive("L","FB1","220R @100MHz / 2A",516.89,528.32,"RS485_VISO_OUT","RS485_VISO",footprint="Inductor_SMD:L_0805_2012Metric",datasheet="https://www.murata.com/en-eu/api/pdfdownloadapi?cate=cgsubChipFerriBead&partno=BLM21PG221SN1D",fields={"MPN":"BLM21PG221SN1D","Manufacturer":"Murata"})
for ref,value,x,a in [("C45","10nF",48.26,V485),("C46","100nF",163.83,V485),("C47","100nF",279.4,V3)]:
    power_passive("C",ref,value,x,588.01,a,G)
schema.text("ADM2687E pin10 VISOOUT feeds pin15 VISOIN only; never parallel with sensor 3V3_ISO.",(14,604),size=1.15)
schema.text("GND2 shares GND_ISO. Terminal 5V comes from TMR. Fit TERM only at a bus end.",(14,610),size=1.15)
schema.text("Nexperia Ioff buffers prevent backfeed between independent 3.3V rails. DIR defaults LOW.",(14,616),size=1.15)

flag("#FLG05",516.89,548.64,"RS485_VISO")


library = folder / "sym-lib-table"
if library.exists():
    library.unlink()
schema.write(folder/f"{project}.kicad_sch")
(folder/"fp-lib-table").write_text('(fp_lib_table\n  (version 7)\n  (lib (name "RelayStack")(type "KiCad")(uri "${KIPRJMOD}/RelayStack.pretty")(options "")(descr "Stack interconnect and field connectors"))\n)\n')


path = folder / f"{project}.kicad_sch"
path.write_text(path.read_text().replace('(paper "A2")', '(paper "User" 594 630)'))

# Preserve the added iButton panel circuit on regeneration.
from add_ibutton_panel_schematic import apply as add_ibutton_panel
add_ibutton_panel(project_root)

# Keep the local 5 V block below the existing iButton circuit.
path.write_text(path.read_text().replace('(paper "User" 594 800)', '(paper "User" 594 920)'))
