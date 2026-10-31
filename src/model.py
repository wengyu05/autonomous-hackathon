"""MILP: choose depot/refinery sites and sizes and all flows at minimum annual cost (CLAUDE.md 4).

Run:
  python -m src.model                                  # full data, demand from config.yaml
  python -m src.model --demand PNK=200 BPN=300 ...     # override some airports
  python -m src.model --toy 10                         # 10-site smoke test
"""
import argparse
import json
import math
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pulp

from src.candidates import build_candidates
from src.distances import road_km_matrix
from src.evaluate import KT_TO_T, LEGS, annual_capex_factor, evaluate, truck_trips
from src.load_data import ROOT, load_airports, load_biomass, load_config, load_geo

SIZES = ("Small", "Large")
FLOW_EPS_KT = 1e-7  # drop solver noise below 0.1 kg/yr when writing flows


@dataclass
class Result:
    status: str                      # Optimal | Feasible (time limit) | Infeasible | Infeasible input | ...
    ok: bool
    message: str = ""
    objective: float | None = None
    best_bound: float | None = None
    gap: float | None = None
    solve_time_s: float | None = None
    demand_kt: dict = field(default_factory=dict)
    facilities: pd.DataFrame | None = None
    flows: pd.DataFrame | None = None
    costs: dict | None = None
    candidates: pd.DataFrame | None = None
    model_size: dict = field(default_factory=dict)
    mix_runs: list = field(default_factory=list)      # per refinery mix, from solve_by_mix


def check_inputs(cfg, bio) -> str | None:
    """Pre-solve gate (CLAUDE.md 4.8). Returns an error message or None."""
    demand = cfg["demand_kt"]
    if any(v is None or v < 0 for v in demand.values()):
        return "Every airport demand must be a number of 0 or more."
    total, max_saf = sum(demand.values()), cfg["refinery_yield"] * cfg["depot_yield"] * bio.kt.sum()
    if total > max_saf + 1e-9:
        return (f"Demand exceeds what all {bio.kt.sum():,.0f} kt of biomass can make: "
                f"{total:,.1f} kt SAF asked, {max_saf:,.1f} kt SAF possible at yield {cfg['refinery_yield']}.")
    if total <= 0 and cfg["mode"] == "meet_demand":
        return "Total demand is 0, so there is nothing to plan."
    return None


def solve(cfg, bio=None, ap=None, geo=None, time_limit=None, log=print, ref_mix=None) -> Result:
    """ref_mix: optional {"Small": n, "Large": n} that fixes the total refinery count by size."""
    bio = bio if bio is not None else load_biomass(cfg)
    ap = ap if ap is not None else load_airports(cfg)
    geo = geo if geo is not None else load_geo(cfg)
    demand = {a: float(cfg["demand_kt"][a]) for a in ap.iata}

    err = check_inputs(cfg, bio)
    if err:
        return Result("Infeasible input", False, err, demand_kt=demand)

    cand = build_candidates(cfg, bio, ap, geo, log=log)
    J = cand[cand.depot_ok].reset_index(drop=True)
    K = cand[cand.refinery_ok].reset_index(drop=True)
    d_ij = road_km_matrix(bio, J, cfg)
    d_jk = road_km_matrix(J, K, cfg)
    d_ka = road_km_matrix(K, ap, cfg)
    for name, d in (("biomass site -> depot", d_ij), ("depot -> refinery", d_jk), ("refinery -> airport", d_ka)):
        if not np.isfinite(d).all():
            raise ValueError(f"No road route for some {name} pairs; check the road data or use roads.source: haversine")

    nI, nJ, nK, nA = len(bio), len(J), len(K), len(ap)
    nearest = cfg.get("nearest_depots_per_site")
    arcs_ij = [(i, j) for i in range(nI) for j in (range(nJ) if not nearest else d_ij[i].argsort()[:nearest])]

    fac, tr = cfg["facilities"], cfg["transport"]
    y_dep, y_ref = cfg["depot_yield"], cfg["refinery_yield"]
    rate = {leg: tr[leg]["usd_per_tkm"] for leg in LEGS}
    sea = set(cfg["sea_leg"]["airports"])
    sea_usd_t = cfg["sea_leg"]["surcharge_usd_per_t"]

    m = pulp.LpProblem("saf_supply_chain", pulp.LpMinimize)
    max_dep = cfg["max_per_site"]["depot"]
    modular = _depots_are_modular(fac["depot"])
    if modular:
        # Small and Large depots cost the same per kt and Large = 2 x Small, so a site's depot capacity
        # is just a count of Small-sized modules. Any module count up to 2 x max fits in at most
        # max_dep facilities (pack pairs into Large). Exact, and removes Small/Large symmetry.
        n_mod = {j: pulp.LpVariable(f"ndepmod_{j}", 0, 2 * max_dep, cat="Integer") for j in range(nJ)}
        dep_units = {j: n_mod[j] for j in range(nJ)}
        dep_cap = {j: fac["depot"]["Small"]["capacity_kt"] * n_mod[j] for j in range(nJ)}
        dep_capex = pulp.lpSum(fac["depot"]["Small"]["capex_usd"] * n_mod[j] for j in range(nJ))
        dep_counts = lambda j: (round(n_mod[j].value() or 0) % 2, round(n_mod[j].value() or 0) // 2)
    else:
        n_dep = {(j, s): pulp.LpVariable(f"ndep_{j}_{s}", 0, max_dep, cat="Integer") for j in range(nJ) for s in SIZES}
        dep_units = {j: pulp.lpSum(n_dep[j, s] for s in SIZES) for j in range(nJ)}
        dep_cap = {j: pulp.lpSum(fac["depot"][s]["capacity_kt"] * n_dep[j, s] for s in SIZES) for j in range(nJ)}
        dep_capex = pulp.lpSum(fac["depot"][s]["capex_usd"] * n_dep[j, s] for j in range(nJ) for s in SIZES)
        dep_counts = lambda j: tuple(round(n_dep[j, s].value() or 0) for s in SIZES)
    n_ref = {(k, s): pulp.LpVariable(f"nref_{k}_{s}", 0, cfg["max_per_site"]["refinery"], cat="Integer")
             for k in range(nK) for s in SIZES}
    n_ref_total = {s: pulp.LpVariable(f"nref_total_{s}", 0, cat="Integer") for s in SIZES}  # branching aid
    x = {(i, j): pulp.LpVariable(f"x_{i}_{j}", 0) for i, j in arcs_ij}
    w = {(j, k): pulp.LpVariable(f"w_{j}_{k}", 0) for j in range(nJ) for k in range(nK)}
    z = {(k, a): pulp.LpVariable(f"z_{k}_{a}", 0) for k in range(nK) for a in range(nA)}
    # Biomass into the Small and the Large units at each site: variable OpEx differs by size.
    dep_in = {(j, s): pulp.LpVariable(f"depin_{j}_{s}", 0) for j in range(nJ) for s in SIZES}
    ref_in = {(k, s): pulp.LpVariable(f"refin_{k}_{s}", 0) for k in range(nK) for s in SIZES}

    factor = annual_capex_factor(cfg)
    capex = dep_capex + pulp.lpSum(fac["refinery"][s]["capex_usd"] * n_ref[k, s] for k in range(nK) for s in SIZES)
    variable = KT_TO_T * (
        pulp.lpSum(fac["depot"][s]["variable_opex_usd_per_t"] * dep_in[j, s] for j in range(nJ) for s in SIZES)
        + pulp.lpSum(fac["refinery"][s]["variable_opex_usd_per_t"] * ref_in[k, s] for k in range(nK) for s in SIZES))
    logistics = KT_TO_T * (
        rate["biomass_to_depot"] * pulp.lpSum(d_ij[i, j] * v for (i, j), v in x.items())
        + rate["depot_to_refinery"] * pulp.lpSum(d_jk[j, k] * v for (j, k), v in w.items())
        + rate["refinery_to_airport"] * pulp.lpSum(d_ka[k, a] * v for (k, a), v in z.items()))
    sea_cost = KT_TO_T * sea_usd_t * pulp.lpSum(z[k, a] for k in range(nK) for a in range(nA) if ap.iata[a] in sea)
    m += factor * capex + variable + logistics + sea_cost

    out_i = {i: [] for i in range(nI)}
    in_j = {j: [] for j in range(nJ)}
    for (i, j), v in x.items():
        out_i[i].append(v)
        in_j[j].append(v)
    for i in range(nI):                                       # 1. supply
        flow = pulp.lpSum(out_i[i])
        m += (flow == bio.kt[i]) if cfg["mode"] == "process_all" else (flow <= bio.kt[i]), f"supply_{i}"
    for j in range(nJ):
        inflow = pulp.lpSum(in_j[j])
        m += pulp.lpSum(dep_in[j, s] for s in SIZES) == inflow, f"depsplit_{j}"
        if modular:  # one pool of modules; the size split only matters for variable OpEx, which is equal here
            m += inflow <= dep_cap[j], f"depcap_{j}"                                                             # 2
        else:
            for s in SIZES:
                m += dep_in[j, s] <= fac["depot"][s]["capacity_kt"] * n_dep[j, s], f"depcap_{j}_{s}"            # 2
            m += dep_units[j] <= max_dep, f"deplim_{j}"                                                          # 7
        m += pulp.lpSum(w[j, k] for k in range(nK)) == y_dep * inflow, f"depbal_{j}"                           # 3
    for k in range(nK):
        inflow = pulp.lpSum(w[j, k] for j in range(nJ))
        m += pulp.lpSum(ref_in[k, s] for s in SIZES) == inflow, f"refsplit_{k}"
        for s in SIZES:
            load = ref_in[k, s] if cfg["refinery_capacity_basis"] == "input" else y_ref * ref_in[k, s]
            m += load <= fac["refinery"][s]["capacity_kt"] * n_ref[k, s], f"refcap_{k}_{s}"                    # 4
        m += pulp.lpSum(z[k, a] for a in range(nA)) == y_ref * inflow, f"refbal_{k}"                            # 5
        m += pulp.lpSum(n_ref[k, s] for s in SIZES) <= cfg["max_per_site"]["refinery"], f"reflim_{k}"         # 7
    for a in range(nA):
        m += pulp.lpSum(z[k, a] for k in range(nK)) >= demand[ap.iata[a]], f"demand_{a}"                       # 6

    # Valid inequalities: they cut fractional facilities out of the LP relaxation without removing
    # any optimal integer plan. A flow can only use a site that has at least one unit built.
    max_saf = y_ref * y_dep * bio.kt.sum()
    for (i, j), v in x.items():
        m += v <= bio.kt[i] * dep_units[j], f"vi_dep_{i}_{j}"
    for s in SIZES:
        m += n_ref_total[s] == pulp.lpSum(n_ref[k, s] for k in range(nK)), f"nref_total_{s}"
        if ref_mix is not None:
            m += n_ref_total[s] == ref_mix[s], f"ref_mix_{s}"
    for k in range(nK):
        n_k = pulp.lpSum(n_ref[k, s] for s in SIZES)
        for a in range(nA):
            cap_a = demand[ap.iata[a]] if cfg["mode"] == "meet_demand" else max_saf
            m += z[k, a] <= cap_a * n_k, f"vi_ref_{k}_{a}"
    need = sum(demand.values()) / (y_ref if cfg["refinery_capacity_basis"] == "input" else 1)
    m += pulp.lpSum(fac["refinery"][s]["capacity_kt"] * n_ref_total[s] for s in SIZES) >= need, "vi_refcover"

    size = {"integer_vars": sum(v.cat == "Integer" for v in m.variables()), "continuous_vars": len(x) + len(w) + len(z),
            "constraints": len(m.constraints), "depot_candidates": nJ, "refinery_candidates": nK}
    log(f"Model: {size['integer_vars']} integer, {size['continuous_vars']} continuous, {size['constraints']} constraints")

    best_bound, stopped, elapsed = _run_solver(m, cfg["solver"], time_limit)
    if m.sol_status == pulp.LpSolutionOptimal and not stopped:
        status = "Optimal"
    elif m.sol_status in (pulp.LpSolutionOptimal, pulp.LpSolutionIntegerFeasible):
        status = "Feasible (time limit)"
    elif m.status == pulp.LpStatusInfeasible:
        return Result("Infeasible", False, "The solver proved no plan meets these demands.", demand_kt=demand,
                      solve_time_s=elapsed, model_size=size, candidates=cand)
    else:
        return Result(pulp.LpStatus[m.status], False, "The solver found no plan within the time limit.",
                      demand_kt=demand, solve_time_s=elapsed, model_size=size, candidates=cand)

    obj = pulp.value(m.objective)
    if best_bound is None and status == "Optimal":
        best_bound = obj
    gap = None if best_bound is None else max(0.0, (obj - best_bound) / abs(obj))

    ref_counts = lambda k: tuple(round(n_ref[k, s].value() or 0) for s in SIZES)
    facilities = _facilities(cfg, J, K, dep_counts, ref_counts, x, w, dep_in, ref_in)
    flows = _flows(cfg, bio, J, K, ap, x, w, z, d_ij, d_jk, d_ka)
    costs = evaluate(cfg, facilities, flows)
    msg = "" if status == "Optimal" else f"Stopped at the time limit; plan is within {gap:.2%} of optimal." if gap is not None else ""
    return Result(status, True, msg, obj, best_bound, gap, elapsed, demand, facilities, flows, costs, cand, size)


def _run_solver(m, sc, time_limit):
    """Solve with HiGHS (default) or CBC. Returns (best_bound, stopped_on_time_limit, seconds)."""
    limit = time_limit or sc["time_limit_s"]
    t0 = time.time()
    if sc["name"] == "HiGHS":
        import highspy
        m.solve(pulp.HiGHS(msg=False, timeLimit=limit, gapRel=sc["mip_gap"], threads=sc["threads"]))
        h = m.solverModel
        stopped = h.getModelStatus() == highspy.HighsModelStatus.kTimeLimit
        return h.getInfo().mip_dual_bound, stopped, time.time() - t0
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "cbc.log"
        m.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=limit, gapRel=sc["mip_gap"], threads=sc["threads"],
                                  logPath=str(log_path)))
        text = log_path.read_text() if log_path.exists() else ""
    hit = re.search(r"Lower bound:\s+([-\d.eE+]+)", text)
    return (float(hit.group(1)) if hit else None), "Stopped on time" in text, time.time() - t0


def _depots_are_modular(dep) -> bool:
    """Small and Large depots are interchangeable modules: Large = 2 x Small at the same cost per kt
    and the same variable OpEx per tonne."""
    s, l = dep["Small"], dep["Large"]
    return (l["capacity_kt"] == 2 * s["capacity_kt"]
            and abs(l["capex_usd"] / l["capacity_kt"] - s["capex_usd"] / s["capacity_kt"]) < 1e-9
            and l.get("variable_opex_usd_per_t", 0) == s.get("variable_opex_usd_per_t", 0))


def _facilities(cfg, J, K, dep_counts, ref_counts, x, w, dep_in, ref_in) -> pd.DataFrame:
    """dep_counts / ref_counts: site index -> (n_small, n_large); dep_in / ref_in: biomass kt per size."""
    fac, rows = cfg["facilities"], []
    y_ref = cfg["refinery_yield"]
    split = {"depot": dep_in, "refinery": ref_in}
    for kind, sites, counts in (("depot", J, dep_counts), ("refinery", K, ref_counts)):
        for idx, site in sites.iterrows():
            ns, nl = counts(idx)
            if ns + nl == 0:
                continue
            in_s, in_l = ((split[kind][idx, s].value() or 0.0) for s in SIZES)
            cap = ns * fac[kind]["Small"]["capacity_kt"] + nl * fac[kind]["Large"]["capacity_kt"]
            if kind == "depot":
                inflow = sum(v.value() or 0 for (i, j), v in x.items() if j == idx)
                out, load = cfg["depot_yield"] * inflow, inflow
            else:
                inflow = sum(w[j, idx].value() or 0 for j in range(len(J)))
                out = y_ref * inflow
                load = inflow if cfg["refinery_capacity_basis"] == "input" else out
            rows.append({"type": kind, "site_id": site.cid, "site_kind": site.kind, "lat": site.lat, "lon": site.lon,
                         "n_small": ns, "n_large": nl, "size": _size_label(ns, nl), "capacity_kt": cap,
                         "input_kt": inflow, "input_small_kt": in_s, "input_large_kt": in_l,
                         "output_kt": out, "utilisation_pct": 100 * load / cap})
    return pd.DataFrame(rows)


def _size_label(ns, nl):
    return " + ".join(p for p in (f"{nl} Large" if nl else "", f"{ns} Small" if ns else "") if p)


def _flows(cfg, bio, J, K, ap, x, w, z, d_ij, d_jk, d_ka) -> pd.DataFrame:
    tr, rows = cfg["transport"], []

    def add(leg, src, dst, kt, km):
        if kt <= FLOW_EPS_KT:
            return
        t = tr[leg]["truck_t"]
        rows.append({"leg": leg, "from_id": src.id_, "from_lat": src.lat, "from_lon": src.lon,
                     "to_id": dst.id_, "to_lat": dst.lat, "to_lon": dst.lon, "kt": kt, "km": km,
                     "cost_usd": kt * KT_TO_T * km * tr[leg]["usd_per_tkm"],
                     "trips_small_truck": truck_trips(kt, t["Small"]), "trips_large_truck": truck_trips(kt, t["Large"])})

    pt = lambda id_, lat, lon: type("P", (), {"id_": id_, "lat": lat, "lon": lon})
    for (i, j), v in x.items():
        add("biomass_to_depot", pt(bio.id[i], bio.lat[i], bio.lon[i]), pt(J.cid[j], J.lat[j], J.lon[j]), v.value() or 0, d_ij[i, j])
    for (j, k), v in w.items():
        add("depot_to_refinery", pt(J.cid[j], J.lat[j], J.lon[j]), pt(K.cid[k], K.lat[k], K.lon[k]), v.value() or 0, d_jk[j, k])
    for (k, a), v in z.items():
        add("refinery_to_airport", pt(K.cid[k], K.lat[k], K.lon[k]), pt(ap.iata[a], ap.lat[a], ap.lon[a]), v.value() or 0, d_ka[k, a])
    return pd.DataFrame(rows)


def write_outputs(cfg, res: Result, out_dir: Path = ROOT / "outputs"):
    out_dir.mkdir(exist_ok=True)
    sol = {
        "status": res.status, "ok": res.ok, "message": res.message,
        "objective_usd_per_year": res.objective, "best_bound_usd": res.best_bound,
        "gap": res.gap, "solve_time_s": res.solve_time_s,
        "demand_kt": res.demand_kt,
        "saf_delivered_kt": res.costs["saf_delivered_kt"] if res.costs else None,
        "total_annual_usd": res.costs["total_annual_usd"] if res.costs else None,
        "cost_per_t_saf_usd": res.costs["cost_per_t_saf_usd"] if res.costs else None,
        "model_size": res.model_size,
        "refinery_mix_search": res.mix_runs,
        "dropped_candidates": res.candidates.attrs.get("dropped", []) if res.candidates is not None else [],
        "config": cfg,
    }
    (out_dir / "solution.json").write_text(json.dumps(sol, indent=2, default=float))
    if not res.ok:
        return
    res.facilities.to_csv(out_dir / "facilities.csv", index=False)
    res.flows.to_csv(out_dir / "flows.csv", index=False)
    c = res.costs
    rows = [("CapEx one-time: depots", c["capex_onetime_depot_usd"], "one-time"),
            ("CapEx one-time: refineries", c["capex_onetime_refinery_usd"], "one-time"),
            ("CapEx annualised", c["capex_annualised_usd"], "per year"),
            ("Fixed OpEx", c["opex_usd"], "per year"),
            ("Variable OpEx: depots", c["variable_opex_depot_usd"], "per year"),
            ("Variable OpEx: refineries", c["variable_opex_refinery_usd"], "per year"),
            ("Logistics: biomass to depot", c["logistics_biomass_to_depot_usd"], "per year"),
            ("Logistics: depot to refinery", c["logistics_depot_to_refinery_usd"], "per year"),
            ("Logistics: refinery to airport", c["logistics_refinery_to_airport_usd"], "per year"),
            ("Sea surcharge (Tarakan)", c["sea_surcharge_usd"], "per year"),
            ("Total annual cost", c["total_annual_usd"], "per year"),
            ("Cost per tonne SAF", c["cost_per_t_saf_usd"], "USD/t")]
    pd.DataFrame(rows, columns=["item", "usd", "basis"]).to_csv(out_dir / "cost_breakdown.csv", index=False)


def solve_by_mix(cfg, bio=None, ap=None, geo=None, time_limit=None, log=print) -> Result:
    """Exact split of the search by refinery mix (number of Small and Large refineries).

    Every mix with enough capacity is either solved with its total counts fixed, or ruled out
    because its refinery cost alone (plus the cheapest possible depots) already exceeds the best
    plan found. The proven lower bound is the smallest bound over all mixes, so the reported gap
    covers the whole problem, not just one mix.
    """
    bio = bio if bio is not None else load_biomass(cfg)
    ap = ap if ap is not None else load_airports(cfg)
    geo = geo if geo is not None else load_geo(cfg)
    demand = {a: float(cfg["demand_kt"][a]) for a in ap.iata}
    err = check_inputs(cfg, bio)
    if err:
        return Result("Infeasible input", False, err, demand_kt=demand)

    fac, factor = cfg["facilities"], annual_capex_factor(cfg)
    y_ref, y_dep = cfg["refinery_yield"], cfg["depot_yield"]
    total_d = sum(demand.values())
    need = total_d / (y_ref if cfg["refinery_capacity_basis"] == "input" else 1)
    biomass_in = total_d / (y_ref * y_dep)
    dep, ref = fac["depot"], fac["refinery"]
    # Every plan processes at least `biomass_in` kt through depots and through refineries, so it pays at
    # least the cheapest depot CapEx per kt and the cheapest variable OpEx on all of it.
    depot_floor = (factor * biomass_in * min(dep[s]["capex_usd"] / dep[s]["capacity_kt"] for s in SIZES)
                   + KT_TO_T * biomass_in * min(dep[s].get("variable_opex_usd_per_t", 0) for s in SIZES))
    ref_var_floor = lambda mx: KT_TO_T * biomass_in * min(
        ref[s].get("variable_opex_usd_per_t", 0) for s in SIZES if mx[s] > 0)
    cap = {s: fac["refinery"][s]["capacity_kt"] for s in SIZES}
    max_n = {s: math.ceil(need / cap[s]) + 1 for s in SIZES}
    mixes = sorted(
        ({"Small": ns, "Large": nl} for ns in range(max_n["Small"] + 1) for nl in range(max_n["Large"] + 1)
         if ns * cap["Small"] + nl * cap["Large"] >= need and ns + nl > 0),
        key=lambda mx: sum(mx[s] * fac["refinery"][s]["capex_usd"] for s in SIZES))

    limit = time_limit or cfg["solver"]["time_limit_s"]
    t0, best, runs, bounds = time.time(), None, [], []
    floor_of = lambda mx: (factor * sum(mx[s] * fac["refinery"][s]["capex_usd"] for s in SIZES)
                           + depot_floor + ref_var_floor(mx))
    for n, mix in enumerate(mixes):
        floor = floor_of(mix)
        label = _size_label(mix["Small"], mix["Large"])
        if best is not None:
            # Stop once the best plan is proven within the gap target against every mix left.
            lb = min(bounds + [floor_of(mx) for mx in mixes[n:]])
            if (best.objective - lb) / best.objective <= cfg["solver"]["mip_gap"]:
                for mx in mixes[n:]:
                    runs.append({"mix": _size_label(mx["Small"], mx["Large"]), "result": "not needed (within gap)",
                                 "lower_bound_usd": floor_of(mx)})
                    bounds.append(floor_of(mx))
                break
        if best is not None and floor >= best.objective:
            runs.append({"mix": label, "result": "ruled out", "lower_bound_usd": floor})
            bounds.append(floor)
            continue
        remaining = limit - (time.time() - t0)
        if remaining < 5:
            runs.append({"mix": label, "result": "not reached (time)", "lower_bound_usd": floor})
            bounds.append(floor)
            continue
        # Each mix may use all remaining time; a mix never reached still counts by its cost floor.
        r = solve(cfg, bio, ap, geo, time_limit=remaining, log=lambda *_: None, ref_mix=mix)
        runs.append({"mix": label, "result": r.status, "objective_usd": r.objective,
                     "lower_bound_usd": r.best_bound, "seconds": r.solve_time_s})
        if r.status == "Infeasible":
            continue
        bounds.append(r.best_bound if r.best_bound is not None else floor)
        if r.ok and (best is None or r.objective < best.objective):
            best = r
        log(f"  mix {label}: {r.status}, ${(r.objective or 0):,.0f}/yr, bound ${(r.best_bound or 0):,.0f}")

    elapsed = time.time() - t0
    if best is None:
        return Result("No plan found", False, "No refinery mix produced a feasible plan within the time limit.",
                      demand_kt=demand, solve_time_s=elapsed)
    lower = min(bounds) if bounds else best.objective
    gap = max(0.0, (best.objective - lower) / best.objective)
    status = "Optimal" if gap <= cfg["solver"]["mip_gap"] + 1e-12 else "Feasible (time limit)"
    best.status, best.best_bound, best.gap, best.solve_time_s = status, min(lower, best.objective), gap, elapsed
    best.message = "" if status == "Optimal" else f"Stopped at the time limit; plan is within {gap:.2%} of optimal."
    best.mix_runs = runs
    return best


def summary(res: Result) -> str:
    if not res.ok:
        return f"Status: {res.status}. {res.message}"
    c, f = res.costs, res.facilities
    lines = [f"Status: {res.status}  gap {res.gap:.3%}  solve {res.solve_time_s:.1f}s  objective ${res.objective:,.0f}/yr"
             if res.gap is not None else f"Status: {res.status}  solve {res.solve_time_s:.1f}s",
             f"Demand: " + ", ".join(f"{a} {v:g}" for a, v in res.demand_kt.items()) + f" kt  (total {sum(res.demand_kt.values()):g})",
             f"Total ${c['total_annual_usd']:,.0f}/yr   SAF {c['saf_delivered_kt']:,.1f} kt   ${c['cost_per_t_saf_usd']:,.0f}/t SAF",
             f"CapEx one-time ${c['capex_onetime_total_usd']:,.0f}   logistics ${c['logistics_total_usd']:,.0f}/yr"]
    for kind in ("refinery", "depot"):
        sub = f[f.type == kind]
        lines.append(f"{'Refineries' if kind == 'refinery' else 'Depots'} ({len(sub)} sites):")
        for r in sub.itertuples():
            lines.append(f"  {r.site_id:14s} {r.size:18s} ({r.lat:.3f}, {r.lon:.3f})  in {r.input_kt:7.1f} kt  util {r.utilisation_pct:5.1f}%")
    used = res.flows[res.flows.leg == "biomass_to_depot"].groupby("from_id").kt.sum()
    lines.append(f"Biomass used: {used.sum():,.1f} kt from {len(used)} of 80 sites")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--demand", nargs="*", default=[], help="IATA=kt, e.g. PNK=200 TRK=50")
    p.add_argument("--toy", type=int, help="use only the first N biomass sites (smoke test)")
    p.add_argument("--time-limit", type=float)
    args = p.parse_args()

    overrides = {"demand_kt": {k: float(v) for k, v in (d.split("=") for d in args.demand)}} if args.demand else None
    cfg = load_config(overrides=overrides)
    bio = load_biomass(cfg)
    if args.toy:
        bio = bio.head(args.toy).reset_index(drop=True)
        cap = cfg["refinery_yield"] * bio.kt.sum()
        cfg["demand_kt"] = {a: round(float(cap) * 0.5 / 4, 3) for a in cfg["demand_kt"]}
        cfg["candidates"]["kmeans_k"] = min(3, args.toy)
        print(f"TOY: {args.toy} sites, {bio.kt.sum():.1f} kt, demand {cfg['demand_kt']}")
    res = solve_by_mix(cfg, bio=bio, time_limit=args.time_limit)
    print(summary(res))
    for r in res.mix_runs:
        print(f"  mix {r['mix']:16s} {r['result']:22s} bound ${r['lower_bound_usd'] or 0:,.0f}"
              + (f"  plan ${r['objective_usd']:,.0f}" if r.get("objective_usd") else ""))
    if not args.toy:
        write_outputs(cfg, res)
        print(f"Outputs written to {ROOT / 'outputs'}")


if __name__ == "__main__":
    main()
