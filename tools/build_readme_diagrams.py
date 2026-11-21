#!/usr/bin/env python3
"""Generate functional SVG diagrams without changing KiCad files.

The power diagram also has a PNG preview. After regenerating its SVG, render it
with rsvg-convert or the existing FCPLCN-161608-1v0/tools/svg_to_png.swift helper.
"""
from pathlib import Path
import re
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "docs" / "readme"
COLORS = {
    "background": "#0c1522", "panel": "#152235", "border": "#344c68",
    "text": "#edf3fc", "muted": "#adbed3", "blue": "#8ab9ff",
    "green": "#88ddba", "amber": "#f4ce86",
}


def text(x, y, label, size=22, color="text", weight=400, anchor="start"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{COLORS[color]}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(label)}</text>')


def box(x, y, width, height, title, lines, accent="blue", title_size=25):
    parts = [f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="20" '
             f'fill="{COLORS["panel"]}" stroke="{COLORS[accent]}" stroke-opacity=".6"/>',
             text(x + 24, y + 42, title, title_size, accent, 700)]
    for index, line in enumerate(lines):
        parts.append(text(x + 24, y + 78 + index * 28, line, 20, "muted"))
    return "\n".join(parts)


def arrow(path, color="blue", both=False):
    # Explicit heads render consistently in browsers and macOS SVG previews.
    match = re.fullmatch(r"M(\d+) (\d+) ([HV])(\d+)", path)
    if not match:
        raise ValueError("Documentation arrows must be straight horizontal/vertical paths")
    x, y, direction, end = match.groups()
    x, y, end = int(x), int(y), int(end)
    end_x, end_y = (end, y) if direction == "H" else (x, end)
    parts = [f'<path d="{path}" fill="none" stroke="{COLORS[color]}" stroke-width="3"/>']
    if direction == "H":
        heads = [(end_x - 8, y, 1)] + ([(x + 8, y, -1)] if both else [])
        for hx, hy, sign in heads:
            parts.append(f'<path d="M{hx - 12 * sign} {hy - 7}L{hx} {hy}L{hx - 12 * sign} {hy + 7}Z" fill="{COLORS[color]}"/>')
    else:
        heads = [(x, end_y - 8, 1)] + ([(x, y + 8, -1)] if both else [])
        for hx, hy, sign in heads:
            parts.append(f'<path d="M{hx - 7} {hy - 12 * sign}L{hx} {hy}L{hx + 7} {hy - 12 * sign}Z" fill="{COLORS[color]}"/>')
    return "".join(parts)


def save(name, height, title, description, content, radius=28):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" '
           f'viewBox="0 0 1600 {height}" role="img" aria-labelledby="title desc">'
           f'<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>'
           f'<rect width="1600" height="{height}" rx="{radius}" fill="{COLORS["background"]}"/>'
           f'<g font-family="Inter,Segoe UI,Arial,sans-serif">{content}</g></svg>')
    DESTINATION.mkdir(parents=True, exist_ok=True)
    (DESTINATION / name).write_text(svg + "\n", encoding="utf-8")


def architecture():
    parts = [text(60, 62, "FCPLCn / FCPLCN-161608-1v0", 20, "blue", 700),
             text(60, 115, "Две платы. Один автономный PLC.", 40, weight=700),
             text(60, 150, "Функциональные связи • 16 реле · 16 входов · 8 DATA-линий", 21, "muted")]
    # Paths are drawn before the panels; no line obscures a label.
    parts += [arrow("M360 267 H450", both=True),
              arrow("M700 350 V490", both=True),
              arrow("M360 588 H450", "amber"),
              arrow("M950 267 H1080", "green", both=True)]
    parts += [box(60, 205, 300, 125, "Домашняя сеть", ["Ethernet / Wi-Fi", "MQTT → Linux-хаб"]),
              box(450, 205, 500, 145, "FCPLCN-CPU-08-1v0", ["ESP32-S3 N16R8 · W5500", "RTC DS3231MZ+ · 0x68"]),
              text(724, 405, "I²C · GPIO4/5", 22, "blue"),
              text(724, 438, "MCP RESET · GPIO6", 20, "muted"),
              box(450, 490, 500, 190, "FCPLCN-RLY-1616-1v0", ["MCP23017 · 0x20 / 0x21", "16 реле COM/NO · 16 входов DI", "FRAM 8 КиБ · 0x50"]),
              box(60, 525, 300, 125, "Питание 12 В DC", ["Вход J1 нижней платы", "Питание обеих плат"], "amber"),
              box(1080, 205, 460, 300, "Полевая сторона", ["DATA1…8 · питание 5V_ISO", "I²C · питание 3V3_ISO", "RS-485 · A / B / GND_ISO", "", "Общая земля GND_ISO"], "green"),
              text(1016, 320, "Барьер", 18, "green", anchor="middle"),
              text(1080, 550, "ISO1640 / ADM2687E", 24, "green", 700),
              text(1080, 587, "DATA, I²C и RS-485 разделяют", 21, "muted"),
              text(1080, 618, "одну GND_ISO; это один домен.", 21, "muted"),
              text(60, 745, "Основная GND: CPU, расширители, FRAM и дискретные входы.", 23, "muted"),
              text(60, 785, "К облаку подключается Linux-хаб; PLC сохраняет локальную логику управления.", 23, "muted")]
    save("hardware-architecture.svg", 830, "Функциональная схема двух плат FCPLCn",
         "CPU соединяется с нижней платой по внутренней I2C и reset. Внешние DATA, I2C и RS485 имеют общую изолированную землю.", "".join(parts))


def input_channel():
    parts = [text(50, 62, "FCPLCn / ДИСКРЕТНЫЕ ВХОДЫ", 20, "blue", 700),
             text(50, 115, "Сухой контакт → цифровой уровень", 39, weight=700),
             text(50, 153, "Канал 1 из 16 · установившиеся состояния · функциональная схема", 22, "muted")]
    for start in (295, 600, 905, 1210):
        parts.append(arrow(f"M{start} 266 H{start + 60}"))
    parts += [box(50, 195, 245, 155, "Контакт", ["DI1 ↔ GND", "Замкнут / разомкнут"]),
              box(355, 195, 245, 155, "Входной RC", ["R161 · 220 Ом", "C141 · 1 мкФ"]),
              box(660, 195, 245, 155, "TLP2363", ["Цепь LED: 12 В", "R101 · 1,2 кОм", "Шунт: 4,7 кОм"]),
              box(965, 195, 245, 155, "Выходной RC", ["R141 · 470 Ом", "C101 · 100 нФ"]),
              box(1270, 195, 280, 155, "MCP23017", ["U5 · адрес 0x20", "IN1 → GPB0"]),
              text(50, 410, "Контакт замкнут → LOW", 28, "green", 700),
              text(820, 410, "Контакт разомкнут → HIGH", 28, "blue", 700),
              text(50, 464, "DI, TLP2363 и MCP23017 используют общую GND. DI — вход для сухого контакта.", 23, "muted"),
              text(50, 505, "TVS и обратный диод показаны в полной принципиальной схеме нижней платы.", 22, "muted")]
    save("input-channel.svg", 550, "Функциональная схема дискретного входа FCPLCn",
         "Цепочка сухой контакт, входной RC, TLP2363, выходной RC, MCP23017. Земля общая; замыкание соответствует LOW.", "".join(parts))


def power_domains():
    parts = [text(60, 62, "FCPLCn / ПИТАНИЕ", 20, "blue", 700),
             text(60, 115, "От 12 В до полевых портов", 40, weight=700),
             text(60, 153, "Источники питания двух плат и граница общей GND_ISO", 22, "muted"),
             '<rect x="525" y="785" width="1050" height="455" rx="24" '
             'fill="#102826" stroke="#88ddba" stroke-opacity=".6" stroke-dasharray="8 8"/>']

    def wire(path, color="amber"):
        return f'<path d="{path}" fill="none" stroke="{COLORS[color]}" stroke-width="3"/>'

    # Branches are placed in the gaps between panels, before their labels.
    parts += [arrow("M460 285 H560", "amber"),
              wire("M510 285 V185 H1315"), arrow("M1315 185 V215", "amber"),
              wire("M770 355 V430 M260 430 H1315"),
              arrow("M260 430 V480", "amber"),
              arrow("M770 430 V480", "amber"),
              arrow("M1315 430 V480", "amber"),
              wire("M770 640 V750 H260"),
              arrow("M260 750 V835", "amber"),
              wire("M770 750 V785"), arrow("M770 785 V835", "green"),
              arrow("M980 907 H1090", "green"),
              arrow("M770 980 V1070", "green"),
              arrow("M980 1142 H1090", "green")]
    parts += [box(60, 215, 400, 140, "12 В DC · RLY J1",
                  ["F1 1,5 А → D1 SS34", "+12V_SYS · TVS D2 SMBJ15A"], "amber"),
              box(560, 215, 420, 140, "Ветка логики",
                  ["D3 B340B + R12 1 Ом / 2 Вт", "+12V_LOGIC"], "amber"),
              box(1090, 215, 450, 140, "Нагрузки 12 В",
                  ["Катушки K1…K16", "Входные цепи LED TLP2363"], "amber"),
              text(60, 405, "+12V_LOGIC → три источника", 22, "amber"),
              box(60, 480, 400, 160, "+3V3 · CPU U3",
                  ["R-78K3.3-1.0 · 1 А", "ESP32-S3, W5500 и RTC"]),
              box(560, 480, 420, 160, "MOD_VBUS · 5 В",
                  ["RLY U2 · R-78E5.0-1.0", "Общий источник 5 В · 1 А"]),
              box(1090, 480, 450, 160, "+3V3_RS485 · CPU U12",
                  ["R-78K3.3-0.5 · 500 мА", "Основная сторона ADM2687E"]),
              text(60, 705, "ОСНОВНАЯ GND", 22, "blue", 700),
              text(60, 737, "CPU, реле, DI и память", 20, "muted"),
              text(1090, 705, "isoPower ADM2687E", 22, "blue", 700),
              text(1090, 737, "Питает сам трансивер, не порт J8", 20, "muted"),
              box(60, 835, 400, 145, "3,3 В · RLY U8",
                  ["TLV1117LV33", "MCP23017 и FRAM"]),
              text(1090, 814, "ПОЛЕВОЙ ДОМЕН · GND_ISO", 20, "green", 700),
              box(560, 835, 420, 145, "5V_ISO · CPU U4",
                  ["TMR-1-0511 · 1 Вт / 200 мА", "Изолированный источник 5 В"], "green"),
              box(1090, 835, 450, 145, "Питание внешних портов",
                  ["DATA: J3, контакт 9", "RS-485: J8, контакт 1"], "green", 24),
              box(560, 1070, 420, 145, "3V3_ISO · CPU U5",
                  ["R-78K3.3-0.5 · 500 мА", "Мощность ограничена TMR"], "green"),
              box(1090, 1070, 450, 145, "Внешняя I²C · J5",
                  ["Контакт 1: 3V3_ISO", "SDA / SCL: подтяжки к 3,3 В"], "green"),
              text(60, 1300, "DATA, внешняя I²C и RS-485 используют одну общую GND_ISO.", 24, "green", 700),
              text(60, 1342, "Внешние полевые устройства: 120 мА суммарно, с учётом обеих шин питания.", 23, "muted"),
              text(60, 1384, "Основная GND и GND_ISO — разные домены; дискретные входы относятся к основной GND.", 23, "muted")]
    save("power-domains.svg", 1435, "Питание и домены земли FCPLCn",
         "12 В после защиты питают реле и ветку логики. Три преобразователя питают CPU, общие 5 В и RS485. От 5 В питаются нижние 3,3 В и изолированный TMR. TMR питает DATA, контакт питания RS485 и преобразователь внешней I2C. Полевые порты имеют общую GND_ISO.", "".join(parts), radius=0)


if __name__ == "__main__":
    architecture()
    input_channel()
    power_domains()
