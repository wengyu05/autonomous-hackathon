"""Convert the optimiser outputs into the web dashboard's JSON contract (web/lib/types.ts).

Used by api.py and runnable on its own to refresh the static files the dashboard loads:
  python -m src.export_web                 # writes web/public/data/*.json

Produces one document per plan: the optimised plan plus baselines B1 and B2, all read from outputs/.
Reads files only: no solving and no network calls.
"""
import json
from pathlib import Path

import pandas as pd

from src.load_data import DISTANCE_MODES, ROOT, load_airports, load_biomass, load_config, outputs_dir
from src.plan_map import assumptions_table
from src.roads import key

OUT = ROOT / "outputs"
WEB_DATA = ROOT / "web" / "public" / "data"

LEG = {"biomass_to_depot": "farm_depot", "depot_to_refinery": "depot_refinery", "refinery_to_airport": "refinery_airport"}
PREFIX = {"depot": "D", "refinery": "R"}
FILES = {"optimised": "results.json", "b1": "results_b1.json", "b2": "results_b2.json"}


class NoPlan(Exception):
    """outputs/ has no usable optimised plan (never solved, or the last solve failed)."""


def _build(fac, flows, summary, meta, farms_df, airport_names, airport_xy, demand, routes, airport_info):
    farms = [{"id": r.id, "name": f"{r.district}, {r.province}", "lat": r.lat, "lng": r.lon, "supplyKt": r.kt,
              "offshore": bool(r.offshore), "coastKm": None if pd.isna(r.coast_km) else float(r.coast_km)}
             for r in farms_df.itertuples()]

    def facilities(kind):
        return [{"id": f"{PREFIX[kind]}-{r.site_id}", "site": r.site_id, "lat": round(r.lat, 5), "lng": round(r.lon, 5),
                 # The contract asks for Small|Large; sites with mixed units are reported by their largest unit
                 # and the exact mix goes in `units`.
                 "size": "Large" if r.n_large > 0 else "Small", "units": r.size,
                 "capacityKt": float(r.capacity_kt), "throughputKt": round(float(r.input_kt), 2),
                 "outputKt": round(float(r.output_kt), 2), "utilisationPct": round(float(r.utilisation_pct), 1)}
                for r in fac[fac.type == kind].itertuples()]

    delivered = flows[flows.leg == "refinery_to_airport"].groupby("to_id").kt.sum()
    airports = [{"id": code, "name": airport_names[code], "lat": airport_xy[code][0], "lng": airport_xy[code][1],
                 "demandKt": float(demand[code]), "deliveredKt": round(float(delivered.get(code, 0.0)), 2),
                 **airport_info[code]}
                for code in airport_names]

    out_flows = []
    for r in flows.itertuples():
        src = r.from_id if r.leg == "biomass_to_depot" else f"{'D' if r.leg == 'depot_to_refinery' else 'R'}-{r.from_id}"
        dst = {"biomass_to_depot": f"D-{r.to_id}", "depot_to_refinery": f"R-{r.to_id}"}.get(r.leg, r.to_id)
        f = {"from": src, "to": dst, "leg": LEG[r.leg], "tonnes": round(r.kt * 1000),
             "distanceKm": round(r.km, 1), "cost": round(r.cost_usd), "trucksLarge": int(r.trips_large_truck)}
        k = f"{key(r.from_lat, r.from_lon)}|{key(r.to_lat, r.to_lon)}"
        if k in routes:  # road shape for the map (real-road runs only); flows without one are drawn straight
            f["path"] = [[r.from_lat, r.from_lon]] + routes[k] + [[r.to_lat, r.to_lon]]
        out_flows.append(f)

    return {"meta": meta, "summary": summary, "farms": farms, "depots": facilities("depot"),
            "refineries": facilities("refinery"), "airports": airports, "flows": out_flows}


def build_all(out_dir: Path = OUT) -> dict[str, dict]:
    """Return {"optimised": doc, "b1": doc, "b2": doc} built from the files in out_dir."""
    sol_path = out_dir / "solution.json"
    if not sol_path.exists():
        raise NoPlan("No plan yet: run a solve first.")
    sol = json.loads(sol_path.read_text())
    if not sol["ok"]:
        raise NoPlan(f"The last solve did not produce a plan: {sol['status']}. {sol['message']}")

    cfg = sol["config"]
    names, demand, opex_rate = cfg["airports"], sol["demand_kt"], cfg["opex_rate"]
    ap = load_airports(load_config())
    xy = {r.iata: (float(r.lat), float(r.lon)) for r in ap.itertuples()}
    # The airports file spells Tarakan "Taraken".
    airport_info = {r.iata: {"city": r.city.replace("Taraken", "Tarakan"), "island": bool(r.island)}
                    for r in ap.itertuples()}
    farms_df = load_biomass(load_config())  # adds the offshore flags from data/borneo_geo.json
    routes_path = ROOT / cfg["roads"]["routes_cache"]
    on_roads = cfg["roads"].get("source", "haversine") == "osrm"
    routes = json.loads(routes_path.read_text()) if on_roads and routes_path.exists() else {}
    ver_path = out_dir / "verification.json"
    ver = json.loads(ver_path.read_text()) if ver_path.exists() else None

    cost_rows = pd.read_csv(out_dir / "cost_breakdown.csv")
    costs = cost_rows.set_index("item").usd
    # Shared by every plan: what the Streamlit app's Checks and Assumptions tabs show.
    common = {"demandKt": demand, "solver": cfg["solver"]["name"],
              "verified": bool(ver and ver["all_pass"]),
              "checksPassed": sum(c["pass"] for c in ver["checks"]) if ver else 0,
              "checksTotal": len(ver["checks"]) if ver else 0,
              "checks": ver["checks"] if ver else [],
              "baselineChecks": {n: {"passed": sum(c["pass"] for c in b["checks"]), "total": len(b["checks"])}
                                 for n, b in (ver or {}).get("baselines", {}).items()},
              "mixSearch": sol.get("refinery_mix_search", []),
              "assumptions": assumptions_table(cfg).to_dict("records"),
              "mipGapTarget": cfg["solver"]["mip_gap"],
              "maxTotalDemandKt": cfg["refinery_yield"] * cfg["depot_yield"] * float(farms_df.kt.sum()),
              "optimisedStatus": sol["status"], "optimisedGap": sol["gap"], "optimisedSolveTimeS": sol["solve_time_s"]}

    plans = [("optimised", "Optimised plan (MILP)", out_dir / "facilities.csv", out_dir / "flows.csv", {
        "totalCost": costs["Total annual cost"], "capex": costs["CapEx annualised"], "opex": costs["Fixed OpEx"],
        "variableOpex": costs["Variable OpEx: depots"] + costs["Variable OpEx: refineries"],
        "logistics": sum(v for k, v in costs.items() if k.startswith("Logistics")),
        "safDelivered": sol["saf_delivered_kt"], "costPerTonne": costs["Cost per tonne SAF"],
        "capexOneTime": costs["CapEx one-time: depots"] + costs["CapEx one-time: refineries"],
        "costItems": cost_rows.to_dict("records"),
    }, {"status": sol["status"], "gap": sol["gap"], "solveTimeS": sol["solve_time_s"]})]

    base_path = out_dir / "baselines.csv"
    base = pd.read_csv(base_path).set_index("baseline") if base_path.exists() else pd.DataFrame()
    for b, r in base.iterrows():
        fl = pd.read_csv(out_dir / f"baseline_{b.lower()}_flows.csv")
        plans.append((b.lower(), f"Baseline {b}: {r['name']}", out_dir / f"baseline_{b.lower()}_facilities.csv",
                      out_dir / f"baseline_{b.lower()}_flows.csv", {
                          "totalCost": r.total_annual_usd,
                          "capex": r.capex_plus_opex_annual_usd - opex_rate * r.capex_onetime_usd,
                          "opex": opex_rate * r.capex_onetime_usd, "variableOpex": r.variable_opex_usd,
                          "logistics": r.logistics_usd,
                          "safDelivered": round(fl[fl.leg == "refinery_to_airport"].kt.sum(), 3),
                          "costPerTonne": r.cost_per_t_saf_usd, "capexOneTime": r.capex_onetime_usd,
                      }, {"status": "Baseline (rule-based)", "gap": None, "solveTimeS": None}))

    # Headline numbers for every plan, so each document can compare itself with the others.
    frames = {sid: (pd.read_csv(fp), pd.read_csv(flp)) for sid, _, fp, flp, _, _ in plans}
    comparisons = []
    for sid, label, _, _, summary, _ in plans:
        fac = frames[sid][0]
        ref = fac[fac.type == "refinery"]
        comparisons.append({"id": sid, "label": label, "totalCost": summary["totalCost"],
                            "costPerTonne": summary["costPerTonne"], "safDelivered": summary["safDelivered"],
                            "depotSites": int((fac.type == "depot").sum()),
                            "refineries": int(ref.n_small.sum() + ref.n_large.sum()),
                            "refinerySizes": ", ".join(ref["size"]),
                            "logistics": summary["logistics"], "capexOneTime": summary["capexOneTime"]})

    docs = {}
    for sid, label, _, _, summary, extra in plans:
        meta = {"scenario": sid, "label": label, **common, **extra, "comparisons": comparisons}
        docs[sid] = _build(*frames[sid], summary, meta, farms_df, names, xy, demand, routes, airport_info)
    return docs


def web_dir(mode: str) -> Path:
    """Where the Next.js app serves a distance mode's JSON (mirrors load_data.outputs_dir)."""
    return WEB_DATA if mode == "official" else WEB_DATA / mode


def web_prefix(mode: str) -> str:
    return "/data/" if mode == "official" else f"/data/{mode}/"


def scenario_index(docs: dict[str, dict], prefix: str = "/data/") -> list[dict]:
    """Dropdown entries; `prefix` is "/data/" for static files or an API path."""
    return [{"id": sid, "label": d["meta"]["label"],
             "file": f"{prefix}{FILES[sid]}" if prefix.startswith("/data") else f"{prefix}{sid}"}
            for sid, d in docs.items()]


def write_static(docs: dict[str, dict], dest: Path = WEB_DATA, prefix: str = "/data/") -> list[Path]:
    """Write the documents and scenarios.json where the Next.js app serves them."""
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for sid, doc in docs.items():
        p = dest / FILES[sid]
        p.write_text(json.dumps(doc, separators=(",", ":"), default=float))
        written.append(p)
    (dest / "scenarios.json").write_text(json.dumps(scenario_index(docs, prefix), indent=2))
    return written


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--distances", choices=list(DISTANCE_MODES), default="official")
    mode = p.parse_args().distances
    docs = build_all(outputs_dir(mode))
    for p in write_static(docs, web_dir(mode), web_prefix(mode)):
        print(f"wrote {p.relative_to(ROOT)}")
    for sid, d in docs.items():
        print(f"  {sid}: {len(d['depots'])} depots, {len(d['refineries'])} refineries, "
              f"{len(d['flows'])} flows, ${d['summary']['totalCost'] / 1e6:,.1f}M/yr")


if __name__ == "__main__":
    main()
