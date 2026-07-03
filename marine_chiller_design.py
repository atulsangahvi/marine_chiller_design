
import re
import math
from dataclasses import dataclass, asdict
from io import BytesIO

import pandas as pd
import streamlit as st

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


# -----------------------------
# Authentication
# -----------------------------
def check_password() -> bool:
    """Password is stored in .streamlit/secrets.toml as APP_PASSWORD='your-password'."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("Marine Chiller Design Checker")
    pwd = st.text_input("Password", type="password")
    app_pwd = st.secrets.get("APP_PASSWORD", "")

    if st.button("Login"):
        if app_pwd and pwd == app_pwd:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    return False


# -----------------------------
# Utility calculations
# -----------------------------
def water_flow_m3h(q_kw: float, delta_t_k: float, cp_kj_kgk: float = 4.186, rho_kg_m3: float = 1000.0) -> float:
    if delta_t_k <= 0:
        return 0.0
    kg_s = q_kw / (cp_kj_kgk * delta_t_k)
    return kg_s * 3600.0 / rho_kg_m3


def pipe_velocity_m_s(flow_m3h: float, dn_mm: float) -> float:
    if flow_m3h <= 0 or dn_mm <= 0:
        return 0.0
    area = math.pi * (dn_mm / 1000.0) ** 2 / 4.0
    return (flow_m3h / 3600.0) / area


def pressure_drop_to_temp_equiv(delta_p_kpa: float, kpa_per_k: float) -> float:
    if kpa_per_k <= 0:
        return 0.0
    return delta_p_kpa / kpa_per_k


def status_from_limits(value, low=None, high=None, warn_low=None, warn_high=None):
    if low is not None and value < low:
        return "FAIL"
    if high is not None and value > high:
        return "FAIL"
    if warn_low is not None and value < warn_low:
        return "WARNING"
    if warn_high is not None and value > warn_high:
        return "WARNING"
    return "OK"


def parse_pdf_text(uploaded_file) -> str:
    if uploaded_file is None or fitz is None:
        return ""
    data = uploaded_file.read()
    uploaded_file.seek(0)
    doc = fitz.open(stream=data, filetype="pdf")
    text = []
    for page in doc:
        text.append(page.get_text())
    return "\n".join(text)


def find_number(patterns, text, default=None):
    for pat in patterns:
        m = re.search(pat, text, flags=re.I | re.M)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                pass
    return default


def parse_compressor_pdf(text: str) -> dict:
    return {
        "model": (re.search(r"(RC2-\d+[A-Z]|CSH\d+-\d+[A-Z]?)", text, re.I).group(1) if re.search(r"(RC2-\d+[A-Z]|CSH\d+-\d+[A-Z]?)", text, re.I) else ""),
        "refrigerant": (re.search(r"Refrigerant\s*:?\s*(R\d+[A-Za-z0-9]*)", text, re.I).group(1) if re.search(r"Refrigerant\s*:?\s*(R\d+[A-Za-z0-9]*)", text, re.I) else ""),
        "cooling_capacity_kw": find_number([r"Cooling capacity\s*:?\s*([\d,.]+)\s*kW", r"Capacity\s*:?\s*([\d,.]+)\s*kW"], text),
        "power_input_kw": find_number([r"Power input\s*:?\s*([\d,.]+)\s*kW"], text),
        "condenser_capacity_kw": find_number([r"Condenser capacity\s*:?\s*([\d,.]+)\s*kW"], text),
        "current_a": find_number([r"Current.*?\s([\d,.]+)\s*A"], text),
        "mass_flow_kg_h": find_number([r"Mass flow LP\s*:?\s*([\d,.]+)\s*kg/h", r"Mass flow rate\s*:?\s*([\d,.]+)\s*kg/h"], text),
        "discharge_temp_c": find_number([r"Disch\.?\s*temp.*?:?\s*([\d,.]+)\s*Deg", r"Discharge gas temp.*?\s*([\d,.]+)\s*°C"], text),
        "sst_c": find_number([r"Evaporating SST\s*:?\s*([\-\d,.]+)\s*°?C", r"Evaporating SST\s*:?\s*([\-\d,.]+)\s*Deg"], text),
        "sct_c": find_number([r"Condensing S[CD]T\s*:?\s*([\-\d,.]+)\s*°?C", r"Condensing SCT\s*:?\s*([\-\d,.]+)\s*Deg"], text),
    }


def parse_condenser_pdf(text: str) -> dict:
    return {
        "capacity_kw": find_number([r"Condenser capacity\s*:?\s*([\d,.]+)\s*kW", r"Heat rejection\s*:?\s*([\d,.]+)\s*kW"], text),
        "water_flow_m3h": find_number([r"Vol(?:ume)?\.?\s*flow.*?\s*([\d,.]+)\s*m³/h", r"Flow.*?\s*([\d,.]+)\s*m3/h"], text),
        "water_dp_kpa": find_number([r"Pressure drop\s*:?\s*([\d,.]+)\s*kPa"], text),
        "water_dp_bar": find_number([r"Pressure drop\s*:?\s*([\d,.]+)\s*bar"], text),
        "water_velocity_ms": find_number([r"Fluid velocity\s*:?\s*([\d,.]+)\s*m", r"velocity\s*:?\s*([\d,.]+)\s*m/s"], text),
        "water_in_c": find_number([r"Water inlet temp\.?\s*:?\s*([\d,.]+)"], text),
        "water_out_c": find_number([r"Water outlet temp\.?\s*:?\s*([\d,.]+)"], text),
    }


def parse_evaporator_pdf(text: str) -> dict:
    return {
        "capacity_kw": find_number([r"Required capacity\s*:?\s*([\d,.]+)\s*kW", r"Evaporator capacity\s*:?\s*([\d,.]+)\s*kW"], text),
        "fluid_flow_m3h": find_number([r"Volumetric flow rate\s*:?\s*([\d,.]+)\s*m³/h"], text),
        "fluid_dp_kpa": find_number([r"Pressure drop\s*:?\s*([\d,.]+)\s*kPa"], text),
        "refrigerant_dp_kpa_excl": find_number([r"Pressure drop \(excl\..*?\)\s*([\d,.]+)\s*kPa"], text),
        "refrigerant_dp_kpa_incl": find_number([r"Pressure drop \(incl\..*?\)\s*([\d,.]+)\s*kPa"], text),
        "superheat_k": find_number([r"Useful superheat\s*:?\s*([\d,.]+)\s*K"], text),
        "mass_flow_kg_h": find_number([r"Mass flow rate\s*:?\s*([\d,.]+)\s*kg/h"], text),
        "vapor_velocity_ms": find_number([r"Velocity \(vapor\)\s*:?\s*([\d,.]+)\s*m/s"], text),
    }


# -----------------------------
# Design logic
# -----------------------------
def evaluate_design(inputs, comp, cond, evap):
    rows = []
    q_kw = inputs["cooling_capacity_kw"]
    chw_flow = water_flow_m3h(q_kw, inputs["chw_in_c"] - inputs["chw_out_c"], inputs["chw_cp"], inputs["chw_rho"])
    cond_kw = comp.get("condenser_capacity_kw") or (q_kw + (comp.get("power_input_kw") or q_kw * 0.3))
    sw_flow = water_flow_m3h(cond_kw, inputs["sw_out_c"] - inputs["sw_in_c"], inputs["sw_cp"], inputs["sw_rho"])

    sw_vel = pipe_velocity_m_s(sw_flow, inputs["sw_pipe_dn"])
    chw_vel = pipe_velocity_m_s(chw_flow, inputs["chw_pipe_dn"])

    suction_dp_total = inputs["evap_ref_dp_kpa"] + inputs["suction_pipe_dp_kpa"] + inputs["suction_filter_dp_kpa"]
    discharge_dp_total = inputs["discharge_pipe_dp_kpa"] + inputs["discharge_valve_dp_kpa"]
    liquid_dp_total = inputs["liquid_line_dp_kpa"] + inputs["filter_drier_dp_kpa"] + inputs["solenoid_dp_kpa"]

    suction_k = pressure_drop_to_temp_equiv(suction_dp_total, inputs["suction_kpa_per_k"])
    discharge_k = pressure_drop_to_temp_equiv(discharge_dp_total, inputs["discharge_kpa_per_k"])
    liquid_k = pressure_drop_to_temp_equiv(liquid_dp_total, inputs["liquid_kpa_per_k"])

    eff_sst = inputs["sst_c"] - suction_k
    eff_sct = inputs["sct_c"] + discharge_k
    remaining_subcool = inputs["subcooling_k"] - liquid_k

    min_load_kw = q_kw * inputs["compressor_min_capacity_pct"] / 100.0
    low_load_problem = inputs["min_site_load_kw"] < min_load_kw

    def add(check, value, status, note):
        rows.append({"Check": check, "Value": value, "Status": status, "Engineering note": note})

    add("Chilled water flow", f"{chw_flow:.1f} m³/h", "OK", "Calculated from cooling capacity and CHW delta-T.")
    add("Seawater flow", f"{sw_flow:.1f} m³/h", "OK", "Calculated from condenser heat rejection and seawater delta-T.")
    add("Chilled water pipe velocity", f"{chw_vel:.2f} m/s", status_from_limits(chw_vel, low=0.6, high=3.0, warn_high=2.5), "Typical target 1–2.5 m/s.")
    add("Seawater pipe velocity", f"{sw_vel:.2f} m/s", status_from_limits(sw_vel, low=1.0, high=3.0, warn_high=2.5), "Marine seawater target often 1.5–2.5 m/s.")
    add("Effective compressor SST", f"{eff_sst:.2f} °C", "OK" if eff_sst >= inputs["sst_min_c"] else "WARNING", "Suction pressure drop reduces SST seen by compressor.")
    add("Effective compressor SCT", f"{eff_sct:.2f} °C", "OK" if eff_sct <= inputs["sct_max_c"] else "WARNING", "Discharge pressure drop increases SCT seen by compressor.")
    add("Remaining subcooling at EEV", f"{remaining_subcool:.2f} K", "OK" if remaining_subcool >= 2.0 else "FAIL", "Need remaining liquid subcooling to avoid flash gas before EEV.")
    add("Low load stability", f"Site min {inputs['min_site_load_kw']:.0f} kW vs compressor min {min_load_kw:.0f} kW", "WARNING" if low_load_problem else "OK", "If site load is below compressor minimum, hot gas bypass or buffer/bypass is required.")
    add("Liquid injection", "Required" if inputs["discharge_temp_c"] > inputs["liquid_injection_threshold_c"] else "Provision only", "WARNING" if inputs["discharge_temp_c"] > inputs["liquid_injection_threshold_c"] else "OK", "Use if discharge temperature is high or compressor software demands it.")
    add("Oil cooler", "Required" if inputs["oil_cooler_required"] else "Provision only", "WARNING" if inputs["oil_cooler_required"] else "OK", "Use if compressor software/manual or oil temperature requires it.")
    add("Suction accumulator", "Required" if inputs["evaporator_type"] == "DX - shell side refrigerant" else "Optional/not required", "WARNING" if inputs["evaporator_type"] == "DX - shell side refrigerant" else "OK", "Normally not required for tube-side DX with good EEV control; consider for floodback risk.")
    add("Liquid receiver", "Recommended", "OK", "Recommended for marine service and pump-down/maintenance.")

    needs = {
        "hot_gas_bypass": low_load_problem,
        "water_bypass": inputs["variable_chw_flow"],
        "seawater_bypass": inputs["low_seawater_operation"],
        "liquid_injection": inputs["discharge_temp_c"] > inputs["liquid_injection_threshold_c"],
        "oil_cooler": inputs["oil_cooler_required"],
        "suction_accumulator": inputs["evaporator_type"] == "DX - shell side refrigerant" and inputs["floodback_risk"],
        "economizer": inputs["use_economizer"],
    }

    overall = "OK"
    if any(r["Status"] == "FAIL" for r in rows):
        overall = "FAIL"
    elif any(r["Status"] == "WARNING" for r in rows):
        overall = "WARNING"

    computed = {
        "chw_flow_m3h": chw_flow,
        "sw_flow_m3h": sw_flow,
        "eff_sst_c": eff_sst,
        "eff_sct_c": eff_sct,
        "remaining_subcool_k": remaining_subcool,
        "overall": overall,
    }
    return pd.DataFrame(rows), needs, computed


def make_bom(needs, inputs):
    items = [
        ("Compressor", "Semi-hermetic screw", "As selected from uploaded datasheet", 1),
        ("Condenser", "Shell-and-tube seawater condenser", "R134a shell side, seawater tube side, titanium/CuNi tubes", 1),
        ("Evaporator", "DX shell-and-tube evaporator", "R134a tube side, chilled water/glycol shell side", 1),
        ("Liquid receiver", "Pressure vessel", "Sized for service charge/pump-down", 1),
        ("Electronic expansion valve", "EEV with controller", "Sized for refrigerant mass flow and pressure drop", 1),
        ("Filter drier", "Replaceable core type", "Liquid line", 1),
        ("Sight glass", "Moisture indicator", "Liquid line", 1),
        ("Liquid solenoid valve", "Normally closed", "Before EEV", 1),
        ("Suction stop valve", "Refrigerant stop valve", "Compressor suction size", 1),
        ("Discharge stop valve", "Refrigerant stop valve", "Compressor discharge size", 1),
        ("Discharge check valve", "Check valve", "After compressor", 1),
        ("Safety relief valves", "Dual relief preferred", "High side and low side", 2),
        ("Pressure transmitters", "4–20 mA", "HP and LP", 2),
        ("Temperature sensors", "PT100/NTC", "CHW in/out, SW in/out, suction, discharge, liquid", 7),
        ("Flow switches", "Paddle/electronic", "Chilled water and seawater", 2),
        ("Gas detector", "HFC refrigerant detector", "Machinery space", 1),
    ]
    if needs["hot_gas_bypass"]:
        items.append(("Hot gas bypass", "Modulating bypass valve", "Discharge to evaporator/suction for low load", 1))
    if needs["water_bypass"]:
        items.append(("Chilled water bypass", "2-way/3-way valve", "Maintain evaporator minimum flow", 1))
    if needs["seawater_bypass"]:
        items.append(("Seawater regulating/bypass valve", "Pressure/temperature control", "Maintain minimum condensing pressure", 1))
    if needs["liquid_injection"]:
        items.append(("Liquid injection kit", "Solenoid + expansion/nozzle", "Motor/chamber cooling", 1))
    if needs["oil_cooler"]:
        items.append(("Oil cooler", "Plate or shell-and-tube", "Water/seawater cooled oil cooler", 1))
    if needs["suction_accumulator"]:
        items.append(("Suction accumulator", "Vertical accumulator", "Before compressor suction", 1))
    if needs["economizer"]:
        items.append(("Economizer subcooler", "Plate heat exchanger + EEV", "Connect to ECO port", 1))
    return pd.DataFrame(items, columns=["Item", "Type", "Specification / duty", "Qty"])


def p_and_id_mermaid(needs):
    lines = [
        "flowchart LR",
        "C[Compressor] --> DSV[Discharge stop valve]",
        "DSV --> CV[Check valve]",
        "CV --> COND[Seawater condenser]",
        "COND --> LR[Liquid receiver]",
        "LR --> LSV[Liquid shut-off valve]",
        "LSV --> FD[Filter drier]",
        "FD --> SG[Sight glass]",
        "SG --> SOL[Liquid solenoid]",
        "SOL --> EEV[EEV]",
        "EEV --> EVAP[DX evaporator]",
        "EVAP --> SF[Suction strainer/filter]",
        "SF --> SSV[Suction stop valve]",
        "SSV --> C",
        "COND -. seawater in/out .- SW[Seawater circuit]",
        "EVAP -. chilled water in/out .- CHW[Chilled water circuit]",
        "C -. HP/LP/PTC/oil protections .- CTRL[Control panel]",
    ]
    if needs["hot_gas_bypass"]:
        lines.append("DSV --> HGBV[Hot gas bypass valve] --> EVAP")
    if needs["liquid_injection"]:
        lines.append("SG --> LIQINJ[Liquid injection valve] --> C")
    if needs["oil_cooler"]:
        lines.append("C --> OC[Oil cooler] --> C")
    if needs["economizer"]:
        lines.append("SG --> ECOHX[Economizer subcooler] --> EEV")
        lines.append("ECOHX --> ECOPORT[Compressor ECO port] --> C")
    if needs["suction_accumulator"]:
        lines.append("EVAP --> ACC[Suction accumulator] --> SF")
    return "\n".join(lines)


def control_mermaid(needs):
    lines = [
        "flowchart TD",
        "START[Start command] --> FLOW{CHW and seawater flow OK?}",
        "FLOW -- No --> ALARM1[Alarm: no flow]",
        "FLOW -- Yes --> PRESS{HP/LP normal?}",
        "PRESS -- No --> ALARM2[Alarm: pressure fault]",
        "PRESS -- Yes --> OIL{Oil level/protection OK?}",
        "OIL -- No --> ALARM3[Alarm: oil fault]",
        "OIL -- Yes --> SOL[Open liquid solenoid]",
        "SOL --> UNLOAD[Start compressor unloaded]",
        "UNLOAD --> EEV[Control EEV by superheat]",
        "EEV --> LOAD[Load compressor by capacity steps/slide valve]",
        "LOAD --> MON[Monitor current, discharge temp, superheat, subcooling]",
        "MON --> SAFE{Any trip condition?}",
        "SAFE -- Yes --> STOP[Unload, stop, alarm]",
        "SAFE -- No --> RUN[Continue running]",
    ]
    if needs["hot_gas_bypass"]:
        lines.append("RUN --> LOWLOAD{Load below compressor minimum?}")
        lines.append("LOWLOAD -- Yes --> HGB[Modulate hot gas bypass]")
    if needs["liquid_injection"]:
        lines.append("MON --> DT{Discharge temp high?}")
        lines.append("DT -- Yes --> LI[Open liquid injection]")
    return "\n".join(lines)


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Marine Chiller Design Checker", layout="wide")
if not check_password():
    st.stop()

st.title("Marine Seawater / Water-Cooled AC Package Design Checker")
st.caption("Upload compressor, condenser and evaporator PDF outputs from your other apps or supplier software. Then check pressure-drop impact, scenarios, P&ID, BOM and control logic.")

with st.sidebar:
    st.header("Uploads")
    comp_pdf = st.file_uploader("Compressor PDF", type=["pdf"])
    cond_pdf = st.file_uploader("Condenser design PDF", type=["pdf"])
    evap_pdf = st.file_uploader("Evaporator design PDF", type=["pdf"])

    st.header("Main design inputs")
    cooling_capacity_kw = st.number_input("Cooling capacity, kW", 50.0, 5000.0, 500.0, step=10.0)
    refrigerant = st.text_input("Refrigerant", "R134a")
    evaporator_type = st.selectbox("Evaporator type", ["DX - tube side refrigerant", "DX - shell side refrigerant", "Flooded"])
    sst_c = st.number_input("Design SST, °C", -30.0, 20.0, 0.0)
    sct_c = st.number_input("Design SCT, °C", 20.0, 80.0, 46.0)
    subcooling_k = st.number_input("Condenser outlet subcooling, K", 0.0, 20.0, 5.0)
    discharge_temp_c = st.number_input("Expected discharge temp, °C", 40.0, 140.0, 72.0)

    st.header("Water conditions")
    chw_in_c = st.number_input("CHW/glycol in to chiller, °C", -10.0, 30.0, 8.0)
    chw_out_c = st.number_input("CHW/glycol out from chiller, °C", -15.0, 25.0, 4.0)
    sw_in_c = st.number_input("Sea/condenser water in, °C", 0.0, 45.0, 37.0)
    sw_out_c = st.number_input("Sea/condenser water out, °C", 5.0, 55.0, 42.0)
    chw_cp = st.number_input("CHW cp, kJ/kg.K", 3.0, 4.5, 4.0)
    chw_rho = st.number_input("CHW density, kg/m³", 900.0, 1100.0, 1030.0)
    sw_cp = st.number_input("Seawater cp, kJ/kg.K", 3.5, 4.2, 3.99)
    sw_rho = st.number_input("Seawater density, kg/m³", 990.0, 1050.0, 1025.0)

    st.header("Pipe sizes")
    chw_pipe_dn = st.number_input("CHW pipe ID approx, mm", 50.0, 500.0, 150.0)
    sw_pipe_dn = st.number_input("Seawater pipe ID approx, mm", 50.0, 500.0, 150.0)

    st.header("Pressure drop inputs")
    evap_ref_dp_kpa = st.number_input("Evaporator refrigerant ΔP incl distributor, kPa", 0.0, 1000.0, 250.0)
    suction_pipe_dp_kpa = st.number_input("Suction pipe ΔP, kPa", 0.0, 200.0, 10.0)
    suction_filter_dp_kpa = st.number_input("Suction filter/valve ΔP, kPa", 0.0, 200.0, 5.0)
    discharge_pipe_dp_kpa = st.number_input("Discharge pipe ΔP, kPa", 0.0, 300.0, 10.0)
    discharge_valve_dp_kpa = st.number_input("Discharge valve/check valve ΔP, kPa", 0.0, 300.0, 10.0)
    liquid_line_dp_kpa = st.number_input("Liquid line ΔP, kPa", 0.0, 500.0, 30.0)
    filter_drier_dp_kpa = st.number_input("Filter drier ΔP, kPa", 0.0, 500.0, 20.0)
    solenoid_dp_kpa = st.number_input("Liquid solenoid ΔP, kPa", 0.0, 500.0, 10.0)

    st.header("Refrigerant P-T sensitivity")
    suction_kpa_per_k = st.number_input("Suction side kPa per K near SST", 5.0, 100.0, 13.0)
    discharge_kpa_per_k = st.number_input("Discharge side kPa per K near SCT", 10.0, 100.0, 35.0)
    liquid_kpa_per_k = st.number_input("Liquid line kPa per K near condensing temp", 10.0, 100.0, 35.0)

    st.header("Scenarios / options")
    compressor_min_capacity_pct = st.number_input("Compressor minimum capacity, %", 5.0, 100.0, 30.0)
    min_site_load_kw = st.number_input("Minimum expected site load, kW", 0.0, 5000.0, 120.0)
    variable_chw_flow = st.checkbox("Variable chilled water flow / 2-way valves possible", value=True)
    low_seawater_operation = st.checkbox("Low seawater temperature operation possible", value=True)
    use_economizer = st.checkbox("Use / provide economizer", value=False)
    oil_cooler_required = st.checkbox("Oil cooler required by compressor selection/manual", value=False)
    floodback_risk = st.checkbox("Floodback risk / uncertain evaporator control", value=False)
    liquid_injection_threshold_c = st.number_input("Liquid injection threshold discharge temp, °C", 70.0, 130.0, 95.0)
    sst_min_c = st.number_input("Minimum acceptable effective SST, °C", -20.0, 20.0, -3.0)
    sct_max_c = st.number_input("Maximum acceptable effective SCT, °C", 20.0, 80.0, 52.0)

# Parse uploads
comp_text = parse_pdf_text(comp_pdf)
cond_text = parse_pdf_text(cond_pdf)
evap_text = parse_pdf_text(evap_pdf)

comp = parse_compressor_pdf(comp_text)
cond = parse_condenser_pdf(cond_text)
evap = parse_evaporator_pdf(evap_text)

# Override some defaults from parsed PDFs where available
if comp.get("sst_c") is not None:
    sst_c = comp["sst_c"]
if comp.get("sct_c") is not None:
    sct_c = comp["sct_c"]
if comp.get("discharge_temp_c") is not None:
    discharge_temp_c = comp["discharge_temp_c"]
if evap.get("refrigerant_dp_kpa_incl") is not None:
    evap_ref_dp_kpa = evap["refrigerant_dp_kpa_incl"]

inputs = dict(
    cooling_capacity_kw=cooling_capacity_kw,
    refrigerant=refrigerant,
    evaporator_type=evaporator_type,
    sst_c=sst_c,
    sct_c=sct_c,
    subcooling_k=subcooling_k,
    discharge_temp_c=discharge_temp_c,
    chw_in_c=chw_in_c,
    chw_out_c=chw_out_c,
    sw_in_c=sw_in_c,
    sw_out_c=sw_out_c,
    chw_cp=chw_cp,
    chw_rho=chw_rho,
    sw_cp=sw_cp,
    sw_rho=sw_rho,
    chw_pipe_dn=chw_pipe_dn,
    sw_pipe_dn=sw_pipe_dn,
    evap_ref_dp_kpa=evap_ref_dp_kpa,
    suction_pipe_dp_kpa=suction_pipe_dp_kpa,
    suction_filter_dp_kpa=suction_filter_dp_kpa,
    discharge_pipe_dp_kpa=discharge_pipe_dp_kpa,
    discharge_valve_dp_kpa=discharge_valve_dp_kpa,
    liquid_line_dp_kpa=liquid_line_dp_kpa,
    filter_drier_dp_kpa=filter_drier_dp_kpa,
    solenoid_dp_kpa=solenoid_dp_kpa,
    suction_kpa_per_k=suction_kpa_per_k,
    discharge_kpa_per_k=discharge_kpa_per_k,
    liquid_kpa_per_k=liquid_kpa_per_k,
    compressor_min_capacity_pct=compressor_min_capacity_pct,
    min_site_load_kw=min_site_load_kw,
    variable_chw_flow=variable_chw_flow,
    low_seawater_operation=low_seawater_operation,
    use_economizer=use_economizer,
    oil_cooler_required=oil_cooler_required,
    floodback_risk=floodback_risk,
    liquid_injection_threshold_c=liquid_injection_threshold_c,
    sst_min_c=sst_min_c,
    sct_max_c=sct_max_c,
)

results, needs, computed = evaluate_design(inputs, comp, cond, evap)
bom = make_bom(needs, inputs)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Design check", "Parsed PDFs", "P&ID", "BOM", "Control circuit"])

with tab1:
    st.subheader(f"Overall design status: {computed['overall']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CHW flow", f"{computed['chw_flow_m3h']:.1f} m³/h")
    c2.metric("Seawater flow", f"{computed['sw_flow_m3h']:.1f} m³/h")
    c3.metric("Effective SST", f"{computed['eff_sst_c']:.2f} °C")
    c4.metric("Effective SCT", f"{computed['eff_sct_c']:.2f} °C")
    st.dataframe(results, use_container_width=True)

    st.subheader("Bypass / optional line decisions")
    st.json(needs)

with tab2:
    st.subheader("Compressor PDF extraction")
    st.json(comp)
    st.subheader("Condenser PDF extraction")
    st.json(cond)
    st.subheader("Evaporator PDF extraction")
    st.json(evap)
    if fitz is None:
        st.warning("PyMuPDF is not installed. Add pymupdf to requirements.txt for PDF parsing.")

with tab3:
    st.subheader("Generated P&ID logic diagram")
    p_mermaid = p_and_id_mermaid(needs)
    st.code(p_mermaid, language="mermaid")
    st.graphviz_chart(p_mermaid.replace("flowchart LR", "digraph G {").replace("-->", "->").replace("-. seawater in/out .-", "->").replace("-. chilled water in/out .-", "->").replace("-. HP/LP/PTC/oil protections .-", "->") + "\n}")
    st.download_button("Download P&ID Mermaid", p_mermaid, file_name="generated_pid.mmd")

with tab4:
    st.subheader("Generated preliminary BOM")
    st.dataframe(bom, use_container_width=True)
    csv = bom.to_csv(index=False).encode("utf-8")
    st.download_button("Download BOM CSV", csv, file_name="marine_chiller_bom.csv")

with tab5:
    st.subheader("Generated control circuit / sequence diagram")
    c_mermaid = control_mermaid(needs)
    st.code(c_mermaid, language="mermaid")
    st.download_button("Download control Mermaid", c_mermaid, file_name="control_circuit.mmd")

st.divider()
st.caption("Engineering note: final vessel sizing, relief valve sizing, electrical protection, marine class approval, and compressor manufacturer confirmation are required before manufacturing.")
