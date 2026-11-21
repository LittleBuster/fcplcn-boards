#!/usr/bin/env python3
"""Generate the documentation's functional diagrams without changing KiCad files."""
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


def save(name, height, title, description, content):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" '
           f'viewBox="0 0 1600 {height}" role="img" aria-labelledby="title desc">'
           f'<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>'
           f'<rect width="1600" height="{height}" rx="28" fill="{COLORS["background"]}"/>'
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


if __name__ == "__main__":
    architecture()
    input_channel()
