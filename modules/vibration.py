"""Flow-induced tube vibration screening (v16).

Tube failure by flow-induced vibration is one of the most common shell-and-tube
field failures and a standard TEMA pre-manufacture check. This module screens
the three classic mechanisms for the unsupported span between baffles:

1. Tube natural frequency f_n for a multi-span beam (first mode, pinned-pinned
   at baffles — conservative, since baffle holes give partial fixity):
       f_n = (lambda^2 / 2*pi*L^2) * sqrt(E*I / m_eff),  lambda^2 = pi^2
   with m_eff = tube metal + fluid inside + hydrodynamic added mass outside.

2. Vortex shedding lock-in: f_vs = St * V_cross / D_o (St ~ 0.2-0.4 in bundles;
   0.33 used for normal triangular pitch ratios ~1.25). Resonance risk when
   f_vs is within +/-20% of f_n. Mostly relevant for liquid shell sides.

3. Fluid-elastic instability (Connors): critical crossflow velocity
       V_crit = beta * f_n * D_o * sqrt(m_eff * delta / (rho_shell * D_o^2))
   with beta ~ 3.0 (conservative lower-bound for tube bundles) and log
   decrement delta ~ 0.03 (liquid) / 0.02 (condensing vapor). Design practice
   keeps V_cross below ~0.5 * V_crit.

These are screening checks per TEMA V-section philosophy, not an HTRI vibration
analysis; inlet-nozzle local velocities and U-bend regions need separate review.
"""
from __future__ import annotations

import math
from typing import Dict

import pandas as pd

E_MODULUS_PA = {
    "Copper Cu-DHP": 117e9, "CuNi 90/10 C70600": 135e9, "CuNi 70/30 C71500": 150e9,
    "Titanium": 105e9, "Aluminum Brass S76": 100e9, "SS316L": 193e9, "Carbon steel": 200e9,
}
DENSITY_KG_M3 = {
    "Copper Cu-DHP": 8940.0, "CuNi 90/10 C70600": 8900.0, "CuNi 70/30 C71500": 8950.0,
    "Titanium": 4510.0, "Aluminum Brass S76": 8330.0, "SS316L": 8000.0, "Carbon steel": 7850.0,
}


def _lookup(d: dict, material: str, default: float) -> float:
    for k, v in d.items():
        if k.lower() in (material or "").lower() or (material or "").lower() in k.lower():
            return v
    return default


def tube_vibration_screening(
    tube_od_mm: float,
    tube_id_mm: float,
    material: str,
    baffle_spacing_mm: float,
    shell_crossflow_velocity_ms: float,
    shell_fluid_density_kg_m3: float,
    tube_side_fluid_density_kg_m3: float = 1000.0,
    pitch_ratio: float = 1.25,
    service: str = "liquid",
    added_mass_coeff: float | None = None,
) -> Dict[str, object]:
    do = max(tube_od_mm, 1.0) / 1000.0
    di = min(max(tube_id_mm, 0.5), tube_od_mm - 0.1) / 1000.0
    L = max(baffle_spacing_mm, 20.0) / 1000.0
    E = _lookup(E_MODULUS_PA, material, 120e9)
    rho_m = _lookup(DENSITY_KG_M3, material, 8900.0)

    # Section properties
    I = math.pi / 64.0 * (do**4 - di**4)
    a_metal = math.pi / 4.0 * (do**2 - di**2)
    a_bore = math.pi / 4.0 * di**2
    a_disp = math.pi / 4.0 * do**2

    # Effective mass per unit length: metal + contained fluid + added (virtual) mass
    cm = added_mass_coeff if added_mass_coeff is not None else \
        max(1.0, 1.0 + 0.6 / max(pitch_ratio - 1.0, 0.05) * 0.1)  # ~1.3-1.6 in bundles
    m_metal = rho_m * a_metal
    m_inside = tube_side_fluid_density_kg_m3 * a_bore
    m_added = cm * shell_fluid_density_kg_m3 * a_disp
    m_eff = m_metal + m_inside + m_added

    # First-mode natural frequency, pinned-pinned span (conservative)
    fn = (math.pi**2 / (2.0 * math.pi * L**2)) * math.sqrt(E * I / max(m_eff, 1e-9))

    # Vortex shedding
    strouhal = 0.33 if pitch_ratio <= 1.35 else 0.25
    v = max(shell_crossflow_velocity_ms, 0.0)
    fvs = strouhal * v / do
    vs_ratio = fvs / max(fn, 1e-9)
    vs_status = "OK" if (vs_ratio < 0.8 or vs_ratio > 1.2) else "RESONANCE RISK"
    if service.lower().startswith("condens"):
        # vortex shedding rarely damaging in condensing vapor; flag only if severe
        vs_status = "OK" if vs_ratio < 1.0 else "CHECK"

    # Fluid-elastic instability (Connors)
    delta = 0.02 if service.lower().startswith("condens") else 0.03
    beta = 3.0
    v_crit = beta * fn * do * math.sqrt(m_eff * delta / max(shell_fluid_density_kg_m3 * do**2, 1e-12))
    fei_margin = v_crit / max(v, 1e-9)
    fei_status = "OK" if v <= 0.5 * v_crit else ("CHECK" if v <= 0.8 * v_crit else "UNSTABLE RISK")

    guidance = []
    if vs_status != "OK":
        guidance.append("Vortex-shedding frequency is near the tube natural frequency: shorten baffle spacing, add support plates, or change velocity.")
    if fei_status != "OK":
        guidance.append("Crossflow velocity is a large fraction of the Connors critical velocity: reduce baffle spacing, add sealing strips/support plates, enlarge shell, or reduce flow.")
    if not guidance:
        guidance.append("Vibration screening acceptable for the mid-span; still review inlet nozzle local velocity and end spans per TEMA V-section before manufacture.")

    return {
        "tube_natural_freq_hz": round(fn, 1),
        "unsupported_span_mm": round(L * 1000.0, 1),
        "effective_mass_kg_m": round(m_eff, 3),
        "added_mass_coefficient": round(cm, 2),
        "vortex_shedding_freq_hz": round(fvs, 1),
        "vortex_freq_ratio_fvs_fn": round(vs_ratio, 3),
        "vortex_shedding_status": vs_status,
        "connors_critical_velocity_ms": round(v_crit, 2),
        "crossflow_velocity_ms": round(v, 3),
        "fei_velocity_margin": round(fei_margin, 2),
        "fluid_elastic_status": fei_status,
        "overall_status": "OK" if vs_status == "OK" and fei_status == "OK" else "CHECK",
        "guidance": " ".join(guidance),
    }


def vibration_table(result: Dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame([[k, v] for k, v in result.items()], columns=["Parameter", "Value"])
