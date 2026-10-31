"""Convert the optimiser outputs into the web dashboard's JSON contract (web/lib/types.ts).

Used by api.py and runnable on its own to refresh the static files the dashboard loads:
  python -m src.export_web                 # writes web/public/data/*.json

Produces one document per plan: the optimised plan plus baselines B1 and B2, all read from outputs/.
Reads files only: no solving and no network calls.
"""
import json
from pathlib import Path

import pandas as pd

from src.load_data import ROOT, load_airports, load_config
from src.roads import key

OUT = ROOT / "outputs"
WEB_DATA = ROOT / "web" / "public" / "data"

LEG = {"biomass_to_depot": "farm_depot", "depot_to_refinery": "depot_refinery", "refinery_to_airport": "refinery_airport"}
PREFIX = {"depot": "D", "refinery": "R"}
FILES = {"optimised": "results.json", "b1": "results_b1.json", "b2": "results_b2.json"}


class NoPlan(Exception):
    """outputs/ has no usable optimised plan (never solved, or the last solve failed)."""


def _build(fac, flows, summary, meta, farms_df, airport_names, airport_xy, demand, routes):
    farms = [{"id": r.location_id, "name": f"{r.district}, {r.province}", "lat": r.latitude,
              "lng": r.longitude, "supplyKt": r.production_kilotons} for r in farms_df.itertuples()]

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
                 "demandKt": float(demand[code]), "deliveredKt": round(float(delivered.get(code, 0.0)), 2)}
                for code in airport_names]

    out_flows = []
    for r in flows.itertuples():
        src = r.from_id if r.leg == "biomass_to_depot" else f"{'D' if r.leg == 'depot_to_refinery' else 'R'}-{r.from_id}"
        dst = {"biomass_to_depot": f"D-{r.to_id}", "depot_to_refinery": f"R-{r.to_id}"}.get(r.leg, r.to_id)
        f = {"from": src, "to": dst, "leg": LEG[r.leg], "tonnes": round(r.kt * 1000),
             "distanceKm": round(r.km, 1), "cost": round(r.cost_usd), "trucksLarge": int(r.trips_large_truck)}
        k = f"{key(r.from_lat, r.from_lon)}|{key(r.to_lat, r.to_lon)}"
        if k in routes:  # road shape for the map; flows without one are drawn straight
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
    farms_df = pd.read_csv(ROOT / cfg["data"]["biomass_csv"])
    routes_path = ROOT / cfg["roads"]["routes_cache"]
    routes = json.loads(routes_path.read_text()) if routes_path.exists() else {}
    ver_path = out_dir / "verification.json"
    ver = json.loads(ver_path.read_text()) if ver_path.exists() else None

    costs = pd.read_csv(out_dir / "cost_breakdown.csv").set_index("item").usd
    common = {"demandKt": demand, "solver": cfg["solver"]["name"],
              "verified": bool(ver and ver["all_pass"]),
              "checksPassed": sum(c["pass"] for c in ver["checks"]) if ver else 0,
              "checksTotal": len(ver["checks"]) if ver else 0}

    plans = [("optimised", "Optimised plan (MILP)", out_dir / "facilities.csv", out_dir / "flows.csv", {
        "totalCost": costs["Total annual cost"], "capex": costs["CapEx annualised"], "opex": costs["OpEx"],
        "logistics": sum(v for k, v in costs.items() if k.startswith("Logistics")),
        "safDelivered": sol["saf_delivered_kt"], "costPerTonne": costs["Cost per tonne SAF"],
        "capexOneTime": costs["CapEx one-time: depots"] + costs["CapEx one-time: refineries"],
    }, {"status": sol["status"], "gap": sol["gap"], "solveTimeS": sol["solve_time_s"]})]

    base_path = out_dir / "baselines.csv"
    base = pd.read_csv(base_path).set_index("baseline") if base_path.exists() else pd.DataFrame()
    for b, r in base.iterrows():
        fl = pd.read_csv(out_dir / f"baseline_{b.lower()}_flows.csv")
        plans.append((b.lower(), f"Baseline {b}: {r['name']}", out_dir / f"baseline_{b.lower()}_facilities.csv",
                      out_dir / f"baseline_{b.lower()}_flows.csv", {
                          "totalCost": r.total_annual_usd,
                          "capex": r.capex_plus_opex_annual_usd - opex_rate * r.capex_onetime_usd,
                          "opex": opex_rate * r.capex_onetime_usd, "logistics": r.logistics_usd,
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
                            "refineries": int(ref.n_small.sum() + ref.n_large.sum())})

    docs = {}
    for sid, label, _, _, summary, extra in plans:
        meta = {"scenario": sid, "label": label, **common, **extra, "comparisons": comparisons}
        docs[sid] = _build(*frames[sid], summary, meta, farms_df, names, xy, demand, routes)
    return docs


def scenario_index(docs: dict[str, dict], prefix: str = "/data/") -> list[dict]:
    """Dropdown entries; `prefix` is "/data/" for static files or an API path."""
    return [{"id": sid, "label": d["meta"]["label"],
             "file": f"{prefix}{FILES[sid]}" if prefix.startswith("/data") else f"{prefix}{sid}"}
            for sid, d in docs.items()]


def write_static(docs: dict[str, dict], dest: Path = WEB_DATA) -> list[Path]:
    """Write the documents and scenarios.json where the Next.js app serves them."""
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for sid, doc in docs.items():
        p = dest / FILES[sid]
        p.write_text(json.dumps(doc, separators=(",", ":"), default=float))
        written.append(p)
    (dest / "scenarios.json").write_text(json.dumps(scenario_index(docs), indent=2))
    return written


def main():
    docs = build_all()
    for p in write_static(docs):
        print(f"wrote {p.relative_to(ROOT)}")
    for sid, d in docs.items():
        print(f"  {sid}: {len(d['depots'])} depots, {len(d['refineries'])} refineries, "
              f"{len(d['flows'])} flows, ${d['summary']['totalCost'] / 1e6:,.1f}M/yr")


if __name__ == "__main__":
    main()
