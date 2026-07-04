def refrigerant_mermaid(include_hgb=False, include_receiver=True):
    lines=["flowchart LR","COMP[Compressor] --> COND[Condenser]","COND --> LR[Liquid Receiver]" if include_receiver else "COND --> LL[Liquid Line]","LR --> FD[Filter Drier]" if include_receiver else "LL --> FD[Filter Drier]","FD --> SG[Sight Glass]","SG --> SOL[Liquid Solenoid]","SOL --> EEV[EEV/TXV]","EEV --> EVAP[Evaporator]","EVAP --> COMP","COND -. water in/out .- WATER[Condenser Water]","EVAP -. chilled water/air .- LOAD[Load]"]
    if include_hgb: lines.append("COMP --> HGB[Hot Gas Bypass] --> EVAP")
    return "\n".join(lines)

def control_mermaid():
    return """flowchart TD
START[Start command] --> FLOW{Water/Air flow OK?}
FLOW -- No --> AL1[Alarm no flow]
FLOW -- Yes --> SAFE{Safety chain OK?}
SAFE -- No --> AL2[Safety alarm]
SAFE -- Yes --> PUMP[Start pump/fan]
PUMP --> SOL[Open liquid solenoid]
SOL --> COMP[Start compressor after delay]
COMP --> EEV[Control EEV superheat]
EEV --> MON[Monitor HP LP Tdischarge current]
MON --> LIM{Approaching limit?}
LIM -- Yes --> UNLOAD[Unload/reduce capacity/alarm]
LIM -- No --> RUN[Continue running]
"""



def mermaid_html(diagram: str, title: str = "Mermaid diagram") -> str:
    """Return HTML that renders Mermaid in Streamlit components.

    st.code(..., language='mermaid') only shows Mermaid source text in Streamlit.
    This helper loads Mermaid JS and renders the diagram inside an iframe component.
    """
    safe_diagram = (diagram or "").replace("`", "&#96;")
    return f"""
    <div style=\"font-family: Arial, sans-serif;\">
      <div class=\"mermaid\">
{safe_diagram}
      </div>
      <script src=\"https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js\"></script>
      <script>
        mermaid.initialize({{ startOnLoad: true, securityLevel: 'loose', theme: 'default' }});
      </script>
      <noscript>{title}: JavaScript is required to render this Mermaid diagram.</noscript>
    </div>
    """
