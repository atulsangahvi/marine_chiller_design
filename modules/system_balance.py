"""Whole-system balance solver (v16).

The component tabs size the condenser and evaporator at ASSUMED evaporating and
condensing temperatures. A real assembled machine does not run at assumed
temperatures: it settles where the compressor's refrigerant flow, the
evaporator's heat absorption and the condenser's heat rejection are all
simultaneously satisfied. This module finds that balance point, which is what
the unit will actually do on the test bench during FAT.

Model:
- Compressor: modules.compressor.cycle_operating_point (real properties,
  eta_v(PR), eta_is(PR)), swept volume calibrated from the entered design point.
- Evaporator water side: effectiveness for a phase-change cold side,
  eps_e = 1 - exp(-UA_e / C_chw), so Q_e_hx = eps_e * C_chw * (T_chw_in - T_e).
- Condenser water side: eps_c = 1 - exp(-UA_c / C_cw), so
  Q_c_hx = eps_c * C_cw * (T_c - T_cw_in).

Solution: for a trial condensing temperature, the evaporator-side balance
Q_e_comp(Te, Tc) = Q_e_hx(Te) is monotonic in Te and solved by bisection; the
outer loop then bisects Tc on the condenser residual
Q_rej_comp(Te*, Tc) - Q_c_hx(Tc).

UA values should come from the condenser/evaporator modules at conditions near
the expected balance point (UA = Uo * Ao). Because U varies with temperature and
flux, treat the result as a screening balance and re-run the component modules
once at the solved temperatures to confirm.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import pandas as pd

from .compressor import cycle_operating_point


def _eps_phase_change(ua_kw_k: float, c_kw_k: float) -> float:
    ntu = ua_kw_k / max(c_kw_k, 1e-9)
    return 1.0 - math.exp(-min(ntu, 30.0))


def solve_balance_point(
    refrigerant: str,
    compressor_type: str,
    rated_cooling_kw: float,
    rated_evap_c: float,
    rated_cond_c: float,
    evap_ua_kw_k: float,
    cond_ua_kw_k: float,
    chw_in_c: float,
    chw_flow_m3h: float,
    cw_in_c: float,
    cw_flow_m3h: float,
    chw_cp_kj_kgk: float = 4.19,
    chw_rho_kg_m3: float = 1000.0,
    cw_cp_kj_kgk: float = 4.0,
    cw_rho_kg_m3: float = 1025.0,
    superheat_k: float = 6.0,
    subcool_k: float = 3.0,
    te_lo_c: float = -15.0,
    tc_hi_c: float = 70.0,
) -> Dict[str, object]:
    """Solve the simultaneous compressor/evaporator/condenser balance point."""
    c_chw = chw_flow_m3h * chw_rho_kg_m3 / 3600.0 * chw_cp_kj_kgk  # kW/K
    c_cw = cw_flow_m3h * cw_rho_kg_m3 / 3600.0 * cw_cp_kj_kgk
    if min(c_chw, c_cw, evap_ua_kw_k, cond_ua_kw_k, rated_cooling_kw) <= 0:
        return {"status": "ERROR", "error": "All flows, UA values and rated capacity must be > 0."}

    cal = cycle_operating_point(refrigerant, rated_evap_c, rated_cond_c,
                                superheat_k=superheat_k, subcool_k=subcool_k,
                                compressor_type=compressor_type,
                                rated_cooling_kw=rated_cooling_kw,
                                rated_evap_c=rated_evap_c, rated_cond_c=rated_cond_c)
    if cal.get("error"):
        return {"status": "ERROR", "error": f"Compressor model: {cal['error']}"}
    vs = cal["swept_flow_m3_s"]
    eps_e = _eps_phase_change(evap_ua_kw_k, c_chw)
    eps_c = _eps_phase_change(cond_ua_kw_k, c_cw)

    def q_evap_hx(te: float) -> float:
        return eps_e * c_chw * max(chw_in_c - te, 0.0)

    def q_cond_hx(tc: float) -> float:
        return eps_c * c_cw * max(tc - cw_in_c, 0.0)

    def solve_te(tc: float) -> Optional[dict]:
        """Bisect Te so compressor evaporator duty equals evaporator HX duty."""
        lo, hi = te_lo_c, min(chw_in_c - 0.2, tc - 2.0)
        if hi <= lo:
            return None
        op_lo = cycle_operating_point(refrigerant, lo, tc, superheat_k, subcool_k,
                                      compressor_type, swept_flow_m3_s=vs)
        op_hi = cycle_operating_point(refrigerant, hi, tc, superheat_k, subcool_k,
                                      compressor_type, swept_flow_m3_s=vs)
        if op_lo.get("error") or op_hi.get("error"):
            return None
        # residual(Te) = Q_comp - Q_hx: rises with Te (comp capacity up, HX duty down)
        r_lo = op_lo["cooling_kw"] - q_evap_hx(lo)
        r_hi = op_hi["cooling_kw"] - q_evap_hx(hi)
        if r_lo > 0:   # even at the coldest Te the compressor outruns the HX
            return {"te": lo, **op_lo, "evap_residual_kw": r_lo}
        if r_hi < 0:   # compressor cannot absorb the HX duty even at max Te
            return {"te": hi, **op_hi, "evap_residual_kw": r_hi}
        te = 0.5 * (lo + hi)
        op = op_hi
        for _ in range(60):
            te = 0.5 * (lo + hi)
            op = cycle_operating_point(refrigerant, te, tc, superheat_k, subcool_k,
                                       compressor_type, swept_flow_m3_s=vs)
            if op.get("error"):
                return None
            r = op["cooling_kw"] - q_evap_hx(te)
            if abs(r) < 0.02 or (hi - lo) < 0.005:
                break
            if r > 0:
                hi = te
            else:
                lo = te
        return {"te": te, **op, "evap_residual_kw": op["cooling_kw"] - q_evap_hx(te)}

    # Outer bisection on Tc: residual(Tc) = Q_rej_comp - Q_cond_hx, falls with Tc.
    lo_tc, hi_tc = cw_in_c + 1.0, tc_hi_c
    sol = None
    s_lo = solve_te(lo_tc)
    s_hi = solve_te(hi_tc)
    if s_lo is None or s_hi is None:
        return {"status": "ERROR", "error": "Could not evaluate the cycle across the search window."}
    r_lo = s_lo["heat_rejection_kw"] - q_cond_hx(lo_tc)
    r_hi = s_hi["heat_rejection_kw"] - q_cond_hx(hi_tc)
    if r_lo < 0:
        sol, tc = s_lo, lo_tc          # condenser oversized: pegs near water temp
    elif r_hi > 0:
        sol, tc = s_hi, hi_tc          # condenser cannot reject: pegged at Tc max
    else:
        tc = 0.5 * (lo_tc + hi_tc)
        for _ in range(60):
            tc = 0.5 * (lo_tc + hi_tc)
            s = solve_te(tc)
            if s is None:
                return {"status": "ERROR", "error": "Cycle evaluation failed during iteration."}
            r = s["heat_rejection_kw"] - q_cond_hx(tc)
            sol = s
            if abs(r) < 0.02 or (hi_tc - lo_tc) < 0.005:
                break
            if r > 0:
                lo_tc = tc
            else:
                hi_tc = tc

    te = sol["te"]
    q = sol["cooling_kw"]
    chw_out = chw_in_c - q / max(c_chw, 1e-9)
    cw_out = cw_in_c + sol["heat_rejection_kw"] / max(c_cw, 1e-9)
    converged = abs(sol.get("evap_residual_kw", 0.0)) < 0.5 and \
        abs(sol["heat_rejection_kw"] - q_cond_hx(tc)) < 0.5
    status = "BALANCED" if converged else "LIMIT"
    notes = []
    if not converged:
        notes.append("Balance hit a search limit: one exchanger or the compressor is far from matching the others; review component sizing.")
    if te < 0.5 and chw_out < 4.0:
        notes.append("Solved evaporating temperature approaches freezing risk for plain water; check glycol/low-limit protection.")
    if tc > rated_cond_c + 5.0:
        notes.append("Condensing temperature settles well above design: condenser is the bottleneck (fouling margin, water flow, or area).")
    if te < rated_evap_c - 3.0:
        notes.append("Evaporating temperature settles well below design: evaporator is the bottleneck; capacity and COP suffer.")

    return {
        "status": status,
        "balanced_evaporating_temp_c": round(te, 2),
        "balanced_condensing_temp_c": round(tc, 2),
        "actual_cooling_capacity_kw": round(q, 2),
        "design_cooling_capacity_kw": round(rated_cooling_kw, 2),
        "capacity_vs_design_pct": round(100.0 * q / max(rated_cooling_kw, 1e-9), 1),
        "compressor_power_kw": round(sol["power_kw"], 2),
        "heat_rejection_kw": round(sol["heat_rejection_kw"], 2),
        "cop": round(sol["cop"], 3),
        "discharge_temp_c": round(sol["discharge_temp_c"], 1),
        "pressure_ratio": round(sol["pressure_ratio"], 3),
        "eta_is": round(sol["eta_is"], 3),
        "eta_vol": round(sol["eta_vol"], 3),
        "refrigerant_mass_flow_kg_s": round(sol["mass_flow_kg_s"], 4),
        "chw_leaving_c": round(chw_out, 2),
        "chw_approach_k": round(chw_out - te, 2),
        "cw_leaving_c": round(cw_out, 2),
        "condenser_approach_k": round(tc - cw_out, 2),
        "evap_effectiveness": round(eps_e, 3),
        "cond_effectiveness": round(eps_c, 3),
        "notes": " ".join(notes) if notes else
                 "Re-run the condenser/evaporator tabs at the solved temperatures to confirm UA, then lock the design point.",
    }


def balance_table(result: Dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame([[k, v] for k, v in result.items()], columns=["Parameter", "Value"])
