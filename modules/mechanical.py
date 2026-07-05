"""Preliminary TEMA-style mechanical screening helpers.

These functions are not pressure-vessel code calculations.  They provide
preliminary minimums and engineering flags so the designer does not accidentally
leave a manufacturing design with zero/blank tubesheet or support information.
Final tubesheet, flange, nozzle and shell calculations must be done to the
chosen pressure-vessel code and TEMA class by a qualified mechanical engineer.
"""
from __future__ import annotations

import math
import pandas as pd


def preliminary_tubesheet_screen(shell_id_mm: float, tube_od_mm: float, design_pressure_bar_g: float,
                                 material_allowable_mpa: float = 95.0, corrosion_allowance_mm: float = 1.5,
                                 joint_efficiency: float = 0.85, fixed_tubesheet: bool = True):
    """Return a conservative placeholder tubesheet thickness screen.

    This is deliberately labelled SCREENING.  It uses a plate-like pressure term
    plus tube-rolling ligament allowance and corrosion allowance; it is not a
    substitute for TEMA RCB/ASME tubesheet design with exact boundary conditions.
    """
    D = max(float(shell_id_mm), 50.0) / 1000.0
    p = max(float(design_pressure_bar_g), 0.1) * 1e5
    S = max(float(material_allowable_mpa), 20.0) * 1e6
    E = max(min(float(joint_efficiency), 1.0), 0.5)
    # plate-like screening thickness; fixed tubesheet gets extra conservatism
    C = 0.55 if fixed_tubesheet else 0.45
    t_pressure_mm = C * D * math.sqrt(p / max(S * E, 1e-9)) * 1000.0
    tube_allowance_mm = max(0.0, 0.35 * float(tube_od_mm))
    min_practical_mm = max(12.0, 1.25 * float(tube_od_mm))
    t_total = max(t_pressure_mm + tube_allowance_mm + corrosion_allowance_mm, min_practical_mm)
    status = "SCREENING OK" if t_total > 0 else "N/A"
    guidance = ("Preliminary only. Final tubesheet design requires TEMA/ASME calculation using exact head type, "
                "tube layout, pass partition grooves, gasket seating, design pressure/temperature and material allowable stress.")
    return {
        "screening_tubesheet_thickness_mm": round(t_total, 1),
        "pressure_component_mm": round(t_pressure_mm, 1),
        "tube_ligament_allowance_mm": round(tube_allowance_mm, 1),
        "corrosion_allowance_mm": round(corrosion_allowance_mm, 1),
        "min_practical_mm": round(min_practical_mm, 1),
        "status": status,
        "guidance": guidance,
    }


def mechanical_screen_table(ts: dict, vib: dict | None = None) -> pd.DataFrame:
    rows = [["Tubesheet thickness screening", ts.get("status", "N/A"), f"{ts.get('screening_tubesheet_thickness_mm','N/A')} mm", ts.get("guidance", "")]]
    if vib:
        rows.append(["Tube vibration screening", vib.get("overall_status", "N/A"), f"fn={vib.get('tube_natural_freq_hz','N/A')} Hz; V/Vcrit margin={vib.get('fei_velocity_margin','N/A')}", vib.get("guidance", "")])
    return pd.DataFrame(rows, columns=["Check", "Status", "Value", "Guidance"])
