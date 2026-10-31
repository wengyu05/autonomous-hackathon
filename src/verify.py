"""Independent check of a solved plan (CLAUDE.md rule 3).

Reloads outputs/flows.csv, facilities.csv and solution.json plus the raw input files, and
recomputes every constraint and the total cost from scratch. Imports nothing from the model.

Run: python -m src.verify      (exit code 1 if any check fails)
"""
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def run(out_dir: Path = OUT) -> dict:
    sol = json.loads((out_dir / "solution.json").read_text())
    cfg = sol["config"]
    breakdown = {r["item"]: float(r["usd"]) for r in read_csv(out_dir / "cost_breakdown.csv")}
    checks, recomputed = check_plan(cfg, sol["demand_kt"], out_dir / "flows.csv", out_dir / "facilities.csv",
                                    {"solver objective": sol["objective_usd_per_year"],
                                     "cost_breakdown.csv": breakdown["Total annual cost"]})
    result = {"status": sol["status"], "gap": sol["gap"], "all_pass": all(c["pass"] for c in checks),
              "recomputed_total_usd": recomputed, "checks": checks, "baselines": {}}

    # Baselines get the same checks, except the per-site limit they are allowed to break.
    if (out_dir / "baselines.csv").exists():
        for b in read_csv(out_dir / "baselines.csv"):
            key = b["baseline"].lower()
            bchecks, btotal = check_plan(cfg, sol["demand_kt"], out_dir / f"baseline_{key}_flows.csv",
                                         out_dir / f"baseline_{key}_facilities.csv",
                                         {"baselines.csv": float(b["total_annual_usd"])}, enforce_site_limits=False)
            result["baselines"][b["baseline"]] = {"all_pass": all(c["pass"] for c in bchecks),
                                                  "recomputed_total_usd": btotal, "checks": bchecks}
    (out_dir / "verification.json").write_text(json.dumps(result, indent=2))
    return result


def check_plan(cfg, demand, flows_path, facs_path, expected_totals: dict, enforce_site_limits=True):
    """Recompute every constraint and the total cost of one plan. Returns (checks, recomputed_total)."""
    tol = cfg["verify"]["tolerance"]
    flows = read_csv(flows_path)
    facs = read_csv(facs_path)
    for f in flows:
        for k in ("kt", "km", "from_lat", "from_lon", "to_lat", "to_lon"):
            f[k] = float(f[k])
    for r in facs:
        r["n_small"], r["n_large"] = int(r["n_small"]), int(r["n_large"])
        r["lat"], r["lon"] = float(r["lat"]), float(r["lon"])
        r["input_small_kt"], r["input_large_kt"] = float(r["input_small_kt"]), float(r["input_large_kt"])

    bio = {r["location_id"]: r for r in read_csv(ROOT / cfg["data"]["biomass_csv"])}
    geo_path = ROOT / cfg["data"]["geo_json"]
    offshore = set()
    if geo_path.exists():
        offshore = {k for k, v in json.loads(geo_path.read_text())["site_checks"].items() if not v["on_land"]}
    airports = {}
    for row in read_csv(ROOT / cfg["data"]["airports_csv"]):
        if row["iata"] in cfg["airports"]:
            airports[row["iata"]] = (float(row["latitude"]), float(row["longitude"]))

    depots = {r["site_id"]: r for r in facs if r["type"] == "depot"}
    refs = {r["site_id"]: r for r in facs if r["type"] == "refinery"}
    leg = lambda name: [f for f in flows if f["leg"] == name]
    l1, l2, l3 = leg("biomass_to_depot"), leg("depot_to_refinery"), leg("refinery_to_airport")
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    def total(rows, key, val):
        return sum(f["kt"] for f in rows if f[key] == val)

    # Flow sanity
    check("All flows non-negative", all(f["kt"] >= -tol for f in flows), f"{len(flows)} flows")
    bad = [f["from_id"] for f in l1 if f["from_id"] not in bio] + [f["to_id"] for f in l1 if f["to_id"] not in depots]
    bad += [f["from_id"] for f in l2 if f["from_id"] not in depots] + [f["to_id"] for f in l2 if f["to_id"] not in refs]
    bad += [f["from_id"] for f in l3 if f["from_id"] not in refs] + [f["to_id"] for f in l3 if f["to_id"] not in airports]
    check("Every flow starts and ends at a built facility, site or airport", not bad, ", ".join(sorted(set(bad)))[:200])

    # Coordinates and distances
    def coords(kind, id_):
        if kind == "bio":
            return float(bio[id_]["latitude"]), float(bio[id_]["longitude"])
        if kind == "air":
            return airports[id_]
        r = (depots if kind == "dep" else refs)[id_]
        return r["lat"], r["lon"]
    if cfg.get("roads", {}).get("source", "haversine") == "osrm":
        rm = json.loads((ROOT / cfg["roads"]["matrix_cache"]).read_text())
        pkey = lambda p: f"{p[0]:.6f},{p[1]:.6f}"

        def truck_km(a, b):
            ka, kb = pkey(a), pkey(b)
            if ka == kb:
                return 0.0
            return rm["km"][ka][kb] + cfg["circuity"] * (rm["snap_km"][ka] + rm["snap_km"][kb])
        dist_check = "Distances = OSRM road km + off-road access (cached road matrix)"
    else:
        truck_km = lambda a, b: cfg["circuity"] * haversine_km(*a, *b)
        dist_check = "Distances = great-circle x circuity"
    ends = {"biomass_to_depot": ("bio", "dep"), "depot_to_refinery": ("dep", "ref"), "refinery_to_airport": ("ref", "air")}
    worst_xy, worst_km = 0.0, 0.0
    for f in flows:
        if f["from_id"] in bad or f["to_id"] in bad:
            continue
        a, b = (coords(k, f[e]) for k, e in zip(ends[f["leg"]], ("from_id", "to_id")))
        worst_xy = max(worst_xy, abs(a[0] - f["from_lat"]), abs(a[1] - f["from_lon"]), abs(b[0] - f["to_lat"]), abs(b[1] - f["to_lon"]))
        worst_km = max(worst_km, abs(truck_km(a, b) - f["km"]))
    check("Flow coordinates match the source files", worst_xy < 1e-9, f"max diff {worst_xy:.2e} deg")
    check(dist_check, worst_km < tol, f"max diff {worst_km:.2e} km")

    # 1. Supply
    viol = []
    for i, r in bio.items():
        out, s = total(l1, "from_id", i), float(r["production_kilotons"])
        if out > s + tol or (cfg["mode"] == "process_all" and out < s - tol):
            viol.append(f"{i}: {out:.6f} vs {s}")
    check(f"1. Supply ({'= supply' if cfg['mode'] == 'process_all' else '<= supply'}) at all {len(bio)} sites", not viol, "; ".join(viol)[:200])

    fac = cfg["facilities"]
    cap = lambda t, r: r["n_small"] * fac[t]["Small"]["capacity_kt"] + r["n_large"] * fac[t]["Large"]["capacity_kt"]

    def size_load(t, r, load_of):
        """Per size: the biomass into its units must fit their capacity (capacity basis applied)."""
        return [f"{r['site_id']} {s}: {load_of(r[f'input_{s.lower()}_kt']):.3f} > {r[f'n_{s.lower()}'] * fac[t][s]['capacity_kt']}"
                for s in ("Small", "Large")
                if load_of(r[f"input_{s.lower()}_kt"]) > r[f"n_{s.lower()}"] * fac[t][s]["capacity_kt"] + tol]
    # 2-3. Depots
    v_cap, v_bal = [], []
    for j, r in depots.items():
        inflow, outflow = total(l1, "to_id", j), total(l2, "from_id", j)
        if inflow > cap("depot", r) + tol:
            v_cap.append(f"{j}: {inflow:.3f} > {cap('depot', r)}")
        v_cap += size_load("depot", r, lambda kt: kt)
        if abs(r["input_small_kt"] + r["input_large_kt"] - inflow) > tol:
            v_bal.append(f"{j}: Small + Large intake {r['input_small_kt'] + r['input_large_kt']:.6f} vs inflow {inflow:.6f}")
        if abs(outflow - cfg["depot_yield"] * inflow) > tol:
            v_bal.append(f"{j}: out {outflow:.6f} vs {cfg['depot_yield']} x in {inflow:.6f}")
    check(f"2. Depot capacity ({len(depots)} depot sites)", not v_cap, "; ".join(v_cap))
    check("3. Depot mass balance", not v_bal, "; ".join(v_bal))
    # 4-5. Refineries
    v_cap, v_bal = [], []
    for k, r in refs.items():
        inflow, outflow = total(l2, "to_id", k), total(l3, "from_id", k)
        load = inflow if cfg["refinery_capacity_basis"] == "input" else cfg["refinery_yield"] * inflow
        if load > cap("refinery", r) + tol:
            v_cap.append(f"{k}: {load:.3f} > {cap('refinery', r)}")
        v_cap += size_load("refinery", r, lambda kt: kt if cfg["refinery_capacity_basis"] == "input" else cfg["refinery_yield"] * kt)
        if abs(r["input_small_kt"] + r["input_large_kt"] - inflow) > tol:
            v_bal.append(f"{k}: Small + Large intake {r['input_small_kt'] + r['input_large_kt']:.6f} vs inflow {inflow:.6f}")
        if abs(outflow - cfg["refinery_yield"] * inflow) > tol:
            v_bal.append(f"{k}: out {outflow:.6f} vs yield x in {inflow:.6f}")
    check(f"4. Refinery capacity, {cfg['refinery_capacity_basis']} basis ({len(refs)} refinery sites)", not v_cap, "; ".join(v_cap))
    check("5. Refinery mass balance", not v_bal, "; ".join(v_bal))
    # 6. Demand
    v = [f"{a}: {total(l3, 'to_id', a):.6f} < {d}" for a, d in demand.items() if total(l3, "to_id", a) < d - tol]
    check("6. Demand met at all 4 airports", not v,
          "; ".join(v) or ", ".join(f"{a} {total(l3, 'to_id', a):.3f}/{d:g}" for a, d in demand.items()))
    # 7. Facility limits
    if enforce_site_limits:
        v = [f"{r['type']} {r['site_id']}: {r['n_small'] + r['n_large']}" for r in facs
             if r["n_small"] + r["n_large"] > cfg["max_per_site"][r["type"]]]
        check("7. Facilities per site within limits", not v, "; ".join(v))
    # A13
    if cfg["offshore_sites"] == "supply_only":
        v = sorted({r["site_id"] for r in facs if r["site_id"] in offshore})
        check("No depot or refinery at an offshore site (A13)", not v, ", ".join(v))

    # Cost, recomputed from scratch
    a = cfg["capex_annualisation"]
    crf = 1 / a["years"] if a["rate"] == 0 else a["rate"] / (1 - (1 + a["rate"]) ** -a["years"])
    capex = sum(r["n_small"] * fac[r["type"]]["Small"]["capex_usd"] + r["n_large"] * fac[r["type"]]["Large"]["capex_usd"] for r in facs)
    variable = sum(r[f"input_{s.lower()}_kt"] * 1000 * fac[r["type"]][s].get("variable_opex_usd_per_t", 0)
                   for r in facs for s in ("Small", "Large"))
    logistics = sum(f["kt"] * 1000 * f["km"] * cfg["transport"][f["leg"]]["usd_per_tkm"] for f in flows)
    sea = sum(f["kt"] * 1000 * cfg["sea_leg"]["surcharge_usd_per_t"] for f in l3 if f["to_id"] in cfg["sea_leg"]["airports"])
    recomputed = (crf + cfg["opex_rate"]) * capex + variable + logistics + sea
    usd_tol = cfg["verify"]["cost_tolerance_usd"]
    for source, value in expected_totals.items():
        check(f"Recomputed total cost = {source}", abs(recomputed - value) <= usd_tol,
              f"recomputed ${recomputed:,.2f} vs ${value:,.2f}")
    return checks, recomputed


def main():
    res = run()
    gap = f"{res['gap']:.3%}" if res["gap"] is not None else "n/a"
    print(f"Solver status: {res['status']}   gap: {gap}")
    for c in res["checks"]:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['check']}" + (f"  ({c['detail']})" if c["detail"] else ""))
    for name, b in res["baselines"].items():
        failed = [c["check"] for c in b["checks"] if not c["pass"]]
        print(f"Baseline {name}: {'all ' + str(len(b['checks'])) + ' checks pass' if not failed else 'FAILED: ' + '; '.join(failed)}"
              f"  (recomputed ${b['recomputed_total_usd']:,.0f}/yr)")
    ok = res["all_pass"] and all(b["all_pass"] for b in res["baselines"].values())
    print("ALL CHECKS PASS" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
