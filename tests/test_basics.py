import math

import pandas as pd
import pytest

from src.distances import haversine_km
from src.evaluate import capital_recovery_factor, evaluate, leg_cost_usd
from src.load_data import load_airports, load_biomass, load_config
from src.model import check_inputs, solve


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_haversine_one_degree_at_equator():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)


def test_haversine_pontianak_to_balikpapan(cfg):
    ap = load_airports(cfg).set_index("iata")
    d = haversine_km(ap.lat.PNK, ap.lon.PNK, ap.lat.BPN, ap.lon.BPN)
    assert 830 < d < 855  # straight line across Borneo


def test_official_distance_is_great_circle_times_circuity(cfg):
    from src.distances import road_km_matrix, straight_km_matrix
    assert cfg["roads"]["source"] == "haversine" and cfg["circuity"] == 1.3   # the challenge update's rule
    land = load_biomass(cfg).query("not offshore").head(20)
    assert road_km_matrix(land, land, cfg) == pytest.approx(1.3 * straight_km_matrix(land, land, 1.0))


def test_road_km_is_never_shorter_than_straight_line(cfg):
    from src.distances import road_km_matrix, straight_km_matrix
    osrm = {**cfg, "roads": {**cfg["roads"], "source": "osrm"}}   # cached real-road matrix (sensitivity)
    bio = load_biomass(cfg)
    land = bio[~bio.offshore].head(20)
    road = road_km_matrix(land, land, osrm)
    straight = straight_km_matrix(land, land, 1.0)
    assert (road >= straight * 0.98 - 0.5).all()   # small slack for road snapping
    assert road.max() > 1.2 * straight.max()        # Borneo roads wind a lot


def test_kt_to_t_conversion():
    # 1 kt over 1 km at $0.10 per tonne-km = 1,000 t x 1 km x 0.10 = $100
    assert leg_cost_usd(1.0, 1.0, 0.10) == pytest.approx(100.0)


def test_capital_recovery_factor():
    assert capital_recovery_factor(0.08, 20) == pytest.approx(0.10185, abs=1e-5)
    assert capital_recovery_factor(0.0, 20) == pytest.approx(0.05)   # straight-line, no interest


def test_evaluate_matches_hand_calculation(cfg):
    fac = pd.DataFrame([{"type": "refinery", "n_small": 1, "n_large": 0, "input_small_kt": 10.0, "input_large_kt": 0.0},
                        {"type": "depot", "n_small": 0, "n_large": 1, "input_small_kt": 0.0, "input_large_kt": 10.0}])
    flows = pd.DataFrame([{"leg": "biomass_to_depot", "to_id": "D", "kt": 10.0, "km": 50.0},
                          {"leg": "refinery_to_airport", "to_id": "PNK", "kt": 2.0, "km": 100.0}])
    c = evaluate(cfg, fac, flows)
    factor = 1 / 20 + 0.05                                  # straight-line CapEx + fixed OpEx
    variable = 10_000 * 60 + 10_000 * 4                     # Small refinery $60/t, Large depot $4/t
    expected = factor * (480e6 + 4.5e6) + variable + 10_000 * 50 * 0.10 + 2_000 * 100 * 0.08
    assert c["variable_opex_usd"] == pytest.approx(variable)
    assert c["total_annual_usd"] == pytest.approx(expected)
    assert c["cost_per_t_saf_usd"] == pytest.approx(expected / 2_000)


def test_demand_above_biomass_limit_is_rejected(cfg):
    bio = load_biomass(cfg)
    too_much = {**cfg, "demand_kt": {"PNK": 400, "PKN": 400, "BPN": 400, "TRK": 400}}  # 1,600 > 1,360
    assert "exceeds" in check_inputs(too_much, bio)
    assert check_inputs(cfg, bio) is None


def test_baseline_refinery_sizing_picks_cheapest_mix(cfg):
    from src.baselines import cheapest_mix
    ref = cfg["facilities"]["refinery"]
    assert cheapest_mix(680, ref) == (0, 1)      # 1 Large ($765M) beats 2 Small ($960M)
    assert cheapest_mix(400, ref) == (1, 0)
    assert cheapest_mix(1360, ref) == (1, 1)     # 1,587 kt for $1.245B


def test_toy_model_meets_demand(cfg):
    bio = load_biomass(cfg).head(10).reset_index(drop=True)
    demand = {a: 20.0 for a in cfg["demand_kt"]}
    toy = {**cfg, "demand_kt": demand, "candidates": {**cfg["candidates"], "kmeans_k": 3}}
    res = solve(toy, bio=bio, time_limit=30, log=lambda *_: None)
    assert res.ok and res.status == "Optimal"
    delivered = res.flows[res.flows.leg == "refinery_to_airport"].groupby("to_id").kt.sum()
    for a, d in demand.items():
        assert delivered[a] >= d - 1e-6
    assert res.costs["total_annual_usd"] == pytest.approx(res.objective, abs=1.0)
    assert not set(res.facilities.site_id) & set(bio[bio.offshore].id)  # A13
    assert math.isfinite(res.costs["cost_per_t_saf_usd"])
