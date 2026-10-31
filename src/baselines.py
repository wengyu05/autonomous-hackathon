"""Rule-of-thumb plans a planner might draw by hand (CLAUDE.md 7.1), scored by the same
cost function as the MILP (src/evaluate.py).

B1 One central refinery: enough Large refineries at the biomass-weighted centre of all 80 sites;
   biomass taken from the sites nearest to it.
B2 Refinery at every airport: each airport refines biomass from the sites nearest to it; SAF it
   cannot make locally comes from the nearest airport refinery with spare output.

Both put a depot at every biomass site they use, sized to fit. Offshore sites (A13) send to the
nearest on-land site's depot. Baselines may exceed the per-site facility limit (A10).

Run: python -m src.baselines   (after python -m src.model)
"""
import json
import math

import numpy as np
import pandas as pd

from src.candidates import point_in_land
from src.distances import road_km_matrix
from src.evaluate import KT_TO_T, evaluate, size_split, truck_trips
from src.load_data import ROOT, load_airports, load_biomass, load_config, load_geo

OUT = ROOT / "outputs"
SIZES = ("Small", "Large")


def cheapest_mix(load_kt: float, units: dict) -> tuple[int, int]:
    """Cheapest (n_small, n_large) with capacity >= load."""
    best = None
    for nl in range(math.ceil(load_kt / units["Large"]["capacity_kt"]) + 1):
        rest = max(0.0, load_kt - nl * units["Large"]["capacity_kt"])
        ns = math.ceil(rest / units["Small"]["capacity_kt"] - 1e-9)
        cost = ns * units["Small"]["capex_usd"] + nl * units["Large"]["capex_usd"]
        if best is None or cost < best[0]:
            best = (cost, ns, nl)
    return best[1], best[2]


class Plan:
    """Collects facilities and flows in the same shape as the MILP outputs."""

    def __init__(self, cfg):
        self.cfg, self.fac_rows, self.flow_rows = cfg, [], []

    def flow(self, leg, src, dst, kt, km):
        if kt <= 1e-9:
            return
        t = self.cfg["transport"][leg]
        self.flow_rows.append({"leg": leg, "from_id": src[0], "from_lat": src[1], "from_lon": src[2],
                               "to_id": dst[0], "to_lat": dst[1], "to_lon": dst[2], "kt": kt, "km": km,
                               "cost_usd": kt * KT_TO_T * km * t["usd_per_tkm"],
                               "trips_small_truck": truck_trips(kt, t["truck_t"]["Small"]),
                               "trips_large_truck": truck_trips(kt, t["truck_t"]["Large"])})

    def facility(self, kind, site, input_kt, ns=None, nl=None):
        units = self.cfg["facilities"][kind]
        y_ref = self.cfg["refinery_yield"]
        out = input_kt * (self.cfg["depot_yield"] if kind == "depot" else y_ref)
        load = input_kt if kind == "depot" or self.cfg["refinery_capacity_basis"] == "input" else out
        if ns is None:
            ns, nl = cheapest_mix(load, units)
        cap = ns * units["Small"]["capacity_kt"] + nl * units["Large"]["capacity_kt"]
        in_small, in_large = size_split(self.cfg, kind, ns, nl, input_kt)
        self.fac_rows.append({"type": kind, "site_id": site[0], "site_kind": "baseline", "lat": site[1], "lon": site[2],
                              "n_small": ns, "n_large": nl,
                              "size": " + ".join(p for p in (f"{nl} Large" if nl else "", f"{ns} Small" if ns else "") if p),
                              "capacity_kt": cap, "input_kt": input_kt, "input_small_kt": in_small,
                              "input_large_kt": in_large, "output_kt": out,
                              "utilisation_pct": 100 * load / cap})

    def frames(self):
        return pd.DataFrame(self.fac_rows), pd.DataFrame(self.flow_rows)


def _depots(plan, bio, take, dest_of, cfg):
    """Depot at every used site (offshore sites use the nearest on-land site's depot).
    take: kt used per biomass row. dest_of: depot site -> (refinery site tuple).
    Returns kt arriving at each refinery id."""
    land = bio[~bio.offshore].reset_index(drop=True)
    d_land = road_km_matrix(bio, land, cfg)
    depot_in, refinery_in = {}, {}
    for i, kt in take.items():
        if kt <= 0:
            continue
        r = bio.loc[i]
        j = i if not r.offshore else bio.index[bio.id == land.id[d_land[i].argmin()]][0]
        dep = bio.loc[j]
        plan.flow("biomass_to_depot", (r.id, r.lat, r.lon), (dep.id, dep.lat, dep.lon), kt,
                  float(road_km_matrix(bio.loc[[i]], bio.loc[[j]], cfg)[0, 0]))
        depot_in[j] = depot_in.get(j, 0.0) + kt
    for j, kt in depot_in.items():
        dep = bio.loc[j]
        plan.facility("depot", (dep.id, dep.lat, dep.lon), kt)
        ref = dest_of(j)
        out = plan.cfg["depot_yield"] * kt
        km = float(road_km_matrix(pd.DataFrame([dep]), pd.DataFrame([{"lat": ref[1], "lon": ref[2]}]), cfg)[0, 0])
        plan.flow("depot_to_refinery", (dep.id, dep.lat, dep.lon), ref, out, km)
        refinery_in[ref[0]] = refinery_in.get(ref[0], 0.0) + out
    return refinery_in


def baseline_central(cfg, bio, ap, geo) -> Plan:
    y = cfg["refinery_yield"] * cfg["depot_yield"]
    demand = {a: float(cfg["demand_kt"][a]) for a in ap.iata}
    lat = float((bio.lat * bio.kt).sum() / bio.kt.sum())
    lon = float((bio.lon * bio.kt).sum() / bio.kt.sum())
    if geo is not None and not point_in_land(lat, lon, geo):
        raise ValueError("Biomass-weighted centre is in the sea; pick another B1 site")
    ref = ("CENTRAL", lat, lon)
    centre = pd.DataFrame([{"lat": lat, "lon": lon}])

    need = sum(demand.values()) / y
    order = np.argsort(road_km_matrix(bio, centre, cfg)[:, 0])
    take = {}
    for i in order:
        take[bio.index[i]] = min(bio.kt.iloc[i], max(0.0, need - sum(take.values())))
    plan = Plan(cfg)
    ref_in = _depots(plan, bio, take, lambda j: ref, cfg)["CENTRAL"]
    load = ref_in if cfg["refinery_capacity_basis"] == "input" else cfg["refinery_yield"] * ref_in
    nl = math.ceil(load / cfg["facilities"]["refinery"]["Large"]["capacity_kt"] - 1e-9)
    plan.facility("refinery", ref, ref_in, 0, nl)
    d = road_km_matrix(centre, ap, cfg)[0]
    for a, row in ap.iterrows():
        plan.flow("refinery_to_airport", ref, (row.iata, row.lat, row.lon), demand[row.iata], float(d[a]))
    return plan


def baseline_airports(cfg, bio, ap, geo) -> Plan:
    y = cfg["refinery_yield"] * cfg["depot_yield"]
    demand = {a: float(cfg["demand_kt"][a]) for a in ap.iata}
    d_site = road_km_matrix(bio, ap, cfg)
    nearest = d_site.argmin(axis=1)
    pool = {a: [i for i in np.argsort(d_site[:, a]) if nearest[i] == a] for a in range(len(ap))}
    supply = {a: float(bio.kt.iloc[pool[a]].sum()) for a in pool}

    # Biomass per airport refinery: its own demand first. An airport without enough nearby biomass
    # has the rest made at the nearest airport refinery that has spare biomass.
    target = {a: min(demand[ap.iata[a]] / y, supply[a]) for a in pool}
    d_ap = road_km_matrix(ap, ap, cfg)
    for b in pool:
        short = demand[ap.iata[b]] / y - target[b]
        for a in np.argsort(d_ap[b]):
            if short <= 1e-9:
                break
            extra = min(short, supply[a] - target[a])
            target[a] += extra
            short -= extra
        assert short < 1e-6, "not enough biomass for B2"

    take = {}
    for a, sites in pool.items():
        left = target[a]
        for i in sites:
            take[bio.index[i]] = min(bio.kt.iloc[i], left)
            left -= take[bio.index[i]]
    site_ap = {bio.index[i]: nearest[i] for i in range(len(bio))}
    land_ap = {}
    plan = Plan(cfg)
    refs = {a: (f"AIRPORT_{ap.iata[a]}", ap.lat[a], ap.lon[a]) for a in range(len(ap))}

    def dest(j):
        return refs[land_ap.setdefault(j, site_ap[j])]
    ref_in = _depots(plan, bio, take, dest, cfg)

    saf = {a: cfg["refinery_yield"] * ref_in.get(refs[a][0], 0.0) for a in refs}
    for a in refs:
        if ref_in.get(refs[a][0], 0.0) > 0:
            plan.facility("refinery", refs[a], ref_in[refs[a][0]])
    # Each refinery serves its own airport, then the nearest airport still short.
    need = dict(demand)
    for a in refs:
        own = min(saf[a], need[ap.iata[a]])
        plan.flow("refinery_to_airport", refs[a], (ap.iata[a], ap.lat[a], ap.lon[a]), own, float(d_ap[a, a]))
        saf[a] -= own
        need[ap.iata[a]] -= own
    for b in sorted(refs, key=lambda b: -need[ap.iata[b]]):
        for a in np.argsort(d_ap[:, b]):
            if need[ap.iata[b]] <= 1e-9:
                break
            give = min(saf[a], need[ap.iata[b]])
            if give > 1e-9:
                plan.flow("refinery_to_airport", refs[a], (ap.iata[b], ap.lat[b], ap.lon[b]), give, float(d_ap[a, b]))
                saf[a] -= give
                need[ap.iata[b]] -= give
    assert all(v <= 1e-6 for v in need.values()), f"B2 unmet demand {need}"
    return plan


def check_plan(cfg, fac, flows, demand):
    """Light feasibility check so a baseline never undercuts the MILP by breaking a rule."""
    l3 = flows[flows.leg == "refinery_to_airport"].groupby("to_id").kt.sum()
    for a, d in demand.items():
        assert l3.get(a, 0.0) >= d - 1e-6, f"demand not met at {a}"
    assert (fac.utilisation_pct <= 100 + 1e-6).all(), "facility over capacity"


def run(cfg, milp_total=None, out_dir=OUT, write=True):
    bio, ap, geo = load_biomass(cfg), load_airports(cfg), load_geo(cfg)
    demand = {a: float(cfg["demand_kt"][a]) for a in ap.iata}
    rows = []
    for key, name, builder in (("B1", "One central refinery", baseline_central),
                               ("B2", "Refinery at every airport", baseline_airports)):
        fac, flows = builder(cfg, bio, ap, geo).frames()
        check_plan(cfg, fac, flows, demand)
        c = evaluate(cfg, fac, flows)
        refs = fac[fac.type == "refinery"]
        rows.append({"baseline": key, "name": name, "total_annual_usd": c["total_annual_usd"],
                     "capex_onetime_usd": c["capex_onetime_total_usd"],
                     "capex_plus_opex_annual_usd": c["capex_annualised_usd"] + c["opex_usd"],
                     "variable_opex_usd": c["variable_opex_usd"],
                     "logistics_usd": c["logistics_total_usd"], "cost_per_t_saf_usd": c["cost_per_t_saf_usd"],
                     "refinery_sites": len(refs), "refineries": f"{int(refs.n_large.sum())} Large + {int(refs.n_small.sum())} Small",
                     "depot_sites": int((fac.type == "depot").sum()),
                     "milp_saving_pct": None if milp_total is None else 100 * (c["total_annual_usd"] - milp_total) / c["total_annual_usd"]})
        if write:
            flows.to_csv(out_dir / f"baseline_{key.lower()}_flows.csv", index=False)
            fac.to_csv(out_dir / f"baseline_{key.lower()}_facilities.csv", index=False)
    table = pd.DataFrame(rows)
    if write:
        table.to_csv(out_dir / "baselines.csv", index=False)
    return table


def main():
    sol = json.loads((OUT / "solution.json").read_text())
    if not sol["ok"]:
        raise SystemExit(f"No MILP plan to compare against: {sol['status']}")
    cfg = load_config(overrides={"demand_kt": sol["demand_kt"]})
    table = run(cfg, sol["total_annual_usd"])
    print(f"MILP ({sol['status']}, gap {sol['gap']:.2%}): ${sol['total_annual_usd']:,.0f}/yr, "
          f"${sol['cost_per_t_saf_usd']:,.0f}/t SAF, demand {sol['demand_kt']}")
    for r in table.itertuples():
        print(f"{r.baseline} {r.name:26s} ${r.total_annual_usd:,.0f}/yr  ${r.cost_per_t_saf_usd:,.0f}/t  "
              f"refineries {r.refineries} at {r.refinery_sites} site(s), {r.depot_sites} depot sites  "
              f"capex+opex ${r.capex_plus_opex_annual_usd:,.0f}  variable ${r.variable_opex_usd:,.0f}  logistics ${r.logistics_usd:,.0f}  "
              f"-> MILP saves {r.milp_saving_pct:.1f}%")


if __name__ == "__main__":
    main()
