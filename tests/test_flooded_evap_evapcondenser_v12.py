from modules.flooded_evaporator import flooded_evaporator_design
from modules.evaporative_condenser import evaporative_condenser_design


def test_flooded_evaporator_has_key_outputs():
    r = flooded_evaporator_design(42.2, 'R407C', 5.0, 12.0, 7.0, tube_count=160, tube_length_m=1.5)
    assert r['evaporator_type'] == 'Flooded shell-and-tube'
    assert r['water_flow_m3h'] > 0
    assert r['Uo_w_m2k'] > 0
    assert r['estimated_refrigerant_charge_kg'] > 0
    assert 'oil' in r['engineering_note'].lower()


def test_evaporative_condenser_has_water_air_balance():
    r = evaporative_condenser_design(55.0, 'R407C', 45.0, 35.0, 28.0, tube_count=400, tube_length_m=2.0, face_width_m=2.5, face_height_m=2.0)
    assert r['condenser_type'].startswith('Evaporative')
    assert r['air_flow_m3s'] > 0
    assert r['spray_water_flow_m3h'] > 0
    assert r['makeup_water_m3h'] > 0
    assert r['heat_rejection_possible_kw'] > 0
