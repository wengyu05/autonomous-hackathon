"""One full re-plan for one distance mode: feasibility gate -> MILP (solve_by_mix) -> outputs ->
baselines -> independent verifier -> road shapes (roads mode) -> dashboard JSON.

Used by api.py, and from the command line to (re)build a mode's saved results:
  python -m src.pipeline --distances roads --time-limit 300
"""
import argparse

from src import baselines, verify
from src.export_web import build_all, web_dir, web_prefix, write_static
from src.load_data import DISTANCE_MODES, distance_config, load_config, outputs_dir
from src.model import solve_by_mix, write_outputs
from src.roads import fetch_plan_routes


def run(cfg, mode: str, time_limit, bio=None, ap=None, geo=None, fetch_routes=True, static=True, log=print):
    """Returns (solver result, dashboard docs or None when there is no plan)."""
    cfg = distance_config(cfg, mode)
    out = outputs_dir(mode)
    res = solve_by_mix(cfg, bio=bio, ap=ap, geo=geo, time_limit=time_limit, log=log)
    write_outputs(cfg, res, out)
    if not res.ok:  # never present an unsolved result as a plan (CLAUDE.md 6.2)
        return res, None
    baselines.run(cfg, res.costs["total_annual_usd"], out_dir=out)
    verify.run(out)
    new_routes = fetch_plan_routes(cfg, out_dir=out, log=log) if fetch_routes else 0
    docs = build_all(out)
    if static:
        write_static(docs, web_dir(mode), web_prefix(mode))
    docs["optimised"]["meta"]["newRoutesFetched"] = new_routes
    return res, docs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--distances", choices=list(DISTANCE_MODES), default="official")
    p.add_argument("--time-limit", type=float)
    a = p.parse_args()
    cfg = load_config()
    res, docs = run(cfg, a.distances, a.time_limit or cfg["solver"]["time_limit_s"], log=lambda *_: None)
    print(f"{a.distances}: {res.status}, gap {res.gap:.2%}, {res.solve_time_s:.0f} s" if res.ok else f"{a.distances}: {res.status}")
    for sid, d in (docs or {}).items():
        print(f"  {sid}: ${d['summary']['totalCost'] / 1e6:,.1f}M/yr, {len(d['refineries'])} refinery sites, "
              f"{len(d['depots'])} depot sites")


if __name__ == "__main__":
    main()
