"""SVG drawing engine for preliminary HVAC/R diagrams.

This replaces Mermaid rendering because Mermaid parsing can fail with engineering
labels and is not suitable for production-oriented P&ID output.  The drawings
below are intentionally simple SVG schematics: stable in Streamlit, downloadable,
and suitable for inclusion in reports.  They are preliminary engineering
schematics, not fabrication CAD drawings.
"""
from __future__ import annotations

import html


def _svg_wrap(width: int, height: int, body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {width} {height}" role="img" aria-label="Engineering schematic">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#2f3a4a" />
    </marker>
    <style>
      .box {{ fill:#f8fafc; stroke:#2f3a4a; stroke-width:1.8; rx:10; }}
      .equip {{ fill:#eef6ff; stroke:#1f5c99; stroke-width:2; rx:10; }}
      .valve {{ fill:#fff7ed; stroke:#b45309; stroke-width:1.8; }}
      .line {{ stroke:#2f3a4a; stroke-width:2.2; fill:none; marker-end:url(#arrow); }}
      .dash {{ stroke:#64748b; stroke-width:1.8; fill:none; stroke-dasharray:6 5; marker-end:url(#arrow); }}
      .text {{ font-family:Arial, sans-serif; font-size:15px; fill:#111827; }}
      .small {{ font-family:Arial, sans-serif; font-size:12px; fill:#475569; }}
      .title {{ font-family:Arial, sans-serif; font-size:19px; font-weight:700; fill:#111827; }}
    </style>
  </defs>
  {body}
</svg>'''


def _box(x, y, w, h, label, cls="equip", sub=None) -> str:
    esc = html.escape(str(label))
    subtxt = html.escape(str(sub)) if sub else ""
    text_y = y + h/2 - (6 if sub else 0)
    out = [f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="10"/>']
    out.append(f'<text class="text" x="{x+w/2}" y="{text_y}" text-anchor="middle" dominant-baseline="middle">{esc}</text>')
    if sub:
        out.append(f'<text class="small" x="{x+w/2}" y="{y+h/2+16}" text-anchor="middle" dominant-baseline="middle">{subtxt}</text>')
    return "\n".join(out)


def _line(x1, y1, x2, y2, label=None, dash=False) -> str:
    cls = "dash" if dash else "line"
    out = [f'<path class="{cls}" d="M {x1} {y1} L {x2} {y2}"/>']
    if label:
        out.append(f'<text class="small" x="{(x1+x2)/2}" y="{(y1+y2)/2-7}" text-anchor="middle">{html.escape(str(label))}</text>')
    return "\n".join(out)


def refrigerant_circuit_svg(include_hgb: bool = False, include_receiver: bool = True, evaporator_type: str = "DX / S&T evaporator") -> str:
    """Return SVG source for a preliminary refrigeration circuit P&ID."""
    body = ['<text class="title" x="30" y="35">Preliminary refrigerant circuit</text>']
    # top row
    body.append(_box(40, 70, 150, 58, "Compressor", sub="COMP"))
    body.append(_box(270, 70, 150, 58, "Condenser", sub="COND"))
    body.append(_box(500, 70, 150, 58, "Receiver", sub="LR" if include_receiver else "Liquid line"))
    body.append(_box(730, 70, 150, 58, "Filter drier", sub="FD", cls="valve"))
    # bottom row
    body.append(_box(730, 220, 150, 58, "Sight glass", sub="SG", cls="valve"))
    body.append(_box(500, 220, 150, 58, "Liquid solenoid", sub="YV1", cls="valve"))
    body.append(_box(270, 220, 150, 58, "EEV / TXV", sub="Expansion", cls="valve"))
    body.append(_box(40, 220, 150, 58, "Evaporator", sub=evaporator_type))
    # refrigerant lines
    body.append(_line(190, 99, 270, 99, "Hot gas"))
    body.append(_line(420, 99, 500, 99, "Condensed liquid"))
    body.append(_line(650, 99, 730, 99))
    body.append(_line(805, 128, 805, 220))
    body.append(_line(730, 249, 650, 249))
    body.append(_line(500, 249, 420, 249))
    body.append(_line(270, 249, 190, 249, "Low pressure mix"))
    body.append(_line(115, 220, 115, 128, "Suction"))
    if include_hgb:
        body.append(_line(145, 128, 345, 220, "Hot gas bypass", dash=True))
    # utilities
    body.append(_line(345, 45, 345, 70, "Cooling water / air", dash=True))
    body.append(_line(115, 300, 115, 278, "Chilled water / air load", dash=True))
    body.append('<text class="small" x="30" y="345">Note: preliminary schematic only. Add relief valves, service valves, gauges, oil management, strainers and marine class requirements during final P&amp;ID review.</text>')
    return _svg_wrap(930, 370, "\n".join(body))


def control_flow_svg() -> str:
    """Return SVG source for a preliminary chiller control sequence."""
    body = ['<text class="title" x="30" y="35">Preliminary control sequence</text>']
    nodes = [
        (50,70,"Start command","Demand"), (270,70,"Flow proven?","CHW/CW/Air"), (500,70,"Safety chain OK?","HPS/LPS/OL/E-stop"),
        (730,70,"Start auxiliaries","Pump / fan"), (730,210,"Open solenoid","YV1"), (500,210,"Start compressor","Timer + unload"),
        (270,210,"Control superheat","EEV PID"), (50,210,"Monitor limits","HP/LP/Tdisc/amps"),
        (270,335,"Unload / alarm","Approaching limit"), (500,335,"Continue running","Stable operation"),
    ]
    for x,y,l,s in nodes:
        body.append(_box(x,y,150,60,l,sub=s,cls="box"))
    body += [
        _line(200,100,270,100), _line(420,100,500,100), _line(650,100,730,100),
        _line(805,130,805,210), _line(730,240,650,240), _line(500,240,420,240),
        _line(270,240,200,240), _line(125,210,125,130),
        _line(125,270,270,365,"If near limit", dash=True), _line(420,365,500,365,"Recovered"),
        _line(575,335,575,270,"No limit", dash=True),
    ]
    body.append('<text class="small" x="30" y="430">Controller must include anti-short-cycle timers, pump/fan proving, low-superheat cutback, high-head unloading and hardwired safety-chain trips.</text>')
    return _svg_wrap(930, 455, "\n".join(body))


def shell_tube_section_svg(title: str = "Shell-and-tube heat exchanger", flooded: bool = False) -> str:
    body = [f'<text class="title" x="30" y="35">{html.escape(title)}</text>']
    # shell and water boxes
    body.append('<rect x="90" y="95" width="700" height="140" rx="70" fill="#f8fafc" stroke="#2f3a4a" stroke-width="2.2"/>')
    body.append('<rect x="55" y="105" width="80" height="120" rx="8" fill="#eef6ff" stroke="#1f5c99" stroke-width="2"/>')
    body.append('<rect x="745" y="105" width="80" height="120" rx="8" fill="#eef6ff" stroke="#1f5c99" stroke-width="2"/>')
    for y in range(120, 215, 18):
        body.append(f'<line x1="130" y1="{y}" x2="760" y2="{y}" stroke="#2563eb" stroke-width="2"/>')
    for x in range(210, 710, 90):
        body.append(f'<line x1="{x}" y1="100" x2="{x}" y2="230" stroke="#64748b" stroke-width="1.5"/>')
    body.append('<text class="small" x="440" y="255" text-anchor="middle">Tube bundle with baffles/support plates</text>')
    if flooded:
        body.append('<path d="M 115 150 Q 280 130 440 150 T 765 150 L 765 220 L 115 220 Z" fill="#dbeafe" opacity="0.65"/>')
        body.append('<text class="small" x="440" y="145" text-anchor="middle">Flooded refrigerant level / shell-side boiling</text>')
    else:
        body.append('<text class="small" x="440" y="145" text-anchor="middle">Shell-side refrigerant flow / condensation or water/glycol service</text>')
    body.append(_line(15,165,55,165,"Tube-side water/glycol"))
    body.append(_line(825,165,875,165,"Return", dash=False))
    body.append(_line(440,70,440,95,"Shell nozzle in", dash=True))
    body.append(_line(440,235,440,300,"Shell nozzle out", dash=True))
    body.append('<text class="small" x="30" y="330">Mechanical drawings must verify tubesheet thickness, baffle spacing, vibration, nozzle reinforcement and pressure-vessel code requirements.</text>')
    return _svg_wrap(910, 360, "\n".join(body))


def svg_html(svg: str) -> str:
    return f'<div style="width:100%; border:1px solid #e5e7eb; border-radius:10px; padding:12px; background:white;">{svg}</div>'
