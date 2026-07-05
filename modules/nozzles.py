"""Shell/channel nozzle sizing (v16).

Nozzles are a routine fabrication-drawing item that the suite previously left
entirely to the user. This module selects standard pipe sizes against the TEMA
RCB-4.6 momentum (rho*v^2) limits:

- Shell inlet, single-phase non-abrasive fluid:   rho*v^2 <= 2232 kg/(m*s^2)
  without an impingement plate.
- Saturated / condensing vapor and two-phase inlet: rho*v^2 <= 744 without
  impingement protection; above that an impingement plate/rods are required
  (and bundle entrance area must be re-checked).
- Water (channel) nozzles are additionally held to a practical 1.0-3.0 m/s.
- Liquid refrigerant outlet held to <= 1.0 m/s to avoid vortexing/flash.

Standard sizes are DN (mm) with schedule-40-style bores. Final nozzle loads,
reinforcement pads and projection remain an ASME/TEMA mechanical design task.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import pandas as pd

# DN size -> approximate internal diameter (mm), sch 40 / standard
DN_ID_MM = {15: 15.8, 20: 20.9, 25: 26.6, 32: 35.1, 40: 40.9, 50: 52.5, 65: 62.7,
            80: 77.9, 100: 102.3, 125: 128.2, 150: 154.1, 200: 202.7, 250: 254.5, 300: 303.2}

RHO_V2_SINGLE_PHASE = 2232.0
RHO_V2_VAPOR_TWO_PHASE = 744.0


def _v(mdot: float, rho: float, id_mm: float) -> float:
    a = math.pi * (id_mm / 1000.0) ** 2 / 4.0
    return mdot / max(rho * a, 1e-12)


def size_nozzle(mdot_kg_s: float, rho_kg_m3: float, service: str,
                v_max_ms: Optional[float] = None, v_min_ms: float = 0.0) -> Dict[str, object]:
    """Select the smallest DN meeting the momentum limit (and velocity band).

    service: 'shell_vapor_in' | 'shell_liquid_out' | 'water' | 'single_phase'
    """
    sv = (service or "").lower()
    if "vapor" in sv or "two_phase" in sv:
        rho_v2_limit = RHO_V2_VAPOR_TWO_PHASE
        v_cap = v_max_ms if v_max_ms else 40.0
    elif "liquid_out" in sv:
        rho_v2_limit = RHO_V2_SINGLE_PHASE
        v_cap = v_max_ms if v_max_ms else 1.0
    elif "water" in sv:
        rho_v2_limit = RHO_V2_SINGLE_PHASE
        v_cap = v_max_ms if v_max_ms else 3.0
        v_min_ms = max(v_min_ms, 1.0)
    else:
        rho_v2_limit = RHO_V2_SINGLE_PHASE
        v_cap = v_max_ms if v_max_ms else 6.0

    chosen = None
    rows = []
    for dn, idmm in DN_ID_MM.items():
        v = _v(mdot_kg_s, rho_kg_m3, idmm)
        rv2 = rho_kg_m3 * v * v
        ok = rv2 <= rho_v2_limit and v <= v_cap
        rows.append({"DN": dn, "ID mm": idmm, "velocity m/s": round(v, 2),
                     "rho_v2": round(rv2, 0), "meets_limits": ok})
        if ok and chosen is None and v >= v_min_ms:
            chosen = rows[-1]
    if chosen is None:
        # fall back to the largest size even if velocity dropped below v_min
        ok_rows = [r for r in rows if r["meets_limits"]]
        chosen = ok_rows[0] if ok_rows else rows[-1]

    impingement = ""
    if "vapor" in sv or "two_phase" in sv:
        impingement = ("No impingement plate required at this rho*v^2 (<= 744)."
                       if chosen["rho_v2"] <= RHO_V2_VAPOR_TWO_PHASE else
                       "IMPINGEMENT PLATE / RODS REQUIRED: rho*v^2 exceeds the TEMA limit for saturated vapor; also re-check bundle entrance area.")
    return {
        "service": service,
        "selected_DN": chosen["DN"],
        "selected_id_mm": chosen["ID mm"],
        "velocity_ms": chosen["velocity m/s"],
        "rho_v2_kg_m_s2": chosen["rho_v2"],
        "rho_v2_limit": rho_v2_limit,
        "impingement_note": impingement,
        "candidates": pd.DataFrame(rows),
    }


def condenser_nozzle_set(q_rej_kw: float, refrigerant: str, condensing_temp_c: float,
                         water_flow_m3h: float, water_rho: float = 1025.0,
                         discharge_temp_c: Optional[float] = None) -> Dict[str, object]:
    """Size the three condenser nozzles: hot-gas in, liquid out, water in/out."""
    try:
        from CoolProp.CoolProp import PropsSI
        Tk = condensing_temp_c + 273.15
        p = float(PropsSI("P", "T", Tk, "Q", 1, refrigerant))
        t_gas = (discharge_temp_c if discharge_temp_c else condensing_temp_c + 25.0) + 273.15
        rho_gas = float(PropsSI("D", "P", p, "T", t_gas, refrigerant))
        rho_liq = float(PropsSI("D", "T", Tk, "Q", 0, refrigerant))
        h_fg = float(PropsSI("H", "T", Tk, "Q", 1, refrigerant) - PropsSI("H", "T", Tk, "Q", 0, refrigerant))
        h_gas = float(PropsSI("H", "P", p, "T", t_gas, refrigerant))
        h_liq_sat = float(PropsSI("H", "T", Tk, "Q", 0, refrigerant))
        dh = max(h_gas - h_liq_sat, h_fg)
    except Exception:
        rho_gas, rho_liq, dh = 55.0, 1050.0, 190000.0
    mdot_ref = q_rej_kw * 1000.0 / dh
    mdot_w = water_flow_m3h * water_rho / 3600.0
    gas_in = size_nozzle(mdot_ref, rho_gas, "shell_vapor_in")
    liq_out = size_nozzle(mdot_ref, rho_liq, "shell_liquid_out")
    water = size_nozzle(mdot_w, water_rho, "water")
    return {
        "refrigerant_mass_flow_kg_s": round(mdot_ref, 4),
        "hot_gas_inlet": gas_in,
        "liquid_outlet": liq_out,
        "water_nozzles": water,
    }


def nozzle_summary_table(nset: Dict[str, object]) -> pd.DataFrame:
    rows = []
    for key, label in [("hot_gas_inlet", "Hot-gas inlet (shell)"),
                       ("liquid_outlet", "Liquid outlet (shell)"),
                       ("water_nozzles", "Water inlet/outlet (channel)")]:
        n = nset.get(key, {})
        rows.append([label, f"DN{n.get('selected_DN','—')}", n.get("velocity_ms", "—"),
                     n.get("rho_v2_kg_m_s2", "—"), n.get("rho_v2_limit", "—"),
                     n.get("impingement_note", "")])
    return pd.DataFrame(rows, columns=["Nozzle", "Size", "Velocity m/s", "rho*v^2", "TEMA limit", "Impingement / note"])
