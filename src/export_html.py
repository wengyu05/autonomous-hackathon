"""Save the dashboard as one self-contained HTML file (no Python or server needed to view it).

Reads the current plan from outputs/ and writes outputs/kalimantan_saf_dashboard.html with the
optimised plan and both baselines, each with its road-route map and tables. Map tiles and the
map library still load from the internet when the file is opened.

Run: python -m src.export_html [output path]
"""
import html
import json
import sys
from datetime import datetime

import folium
import pandas as pd

from src.load_data import ROOT, load_airports, load_biomass, load_config
from src.plan_map import LEGS, airports_table, assumptions_table, build_map, money
from src.roads import RoadNetwork

OUT = ROOT / "outputs"
DEFAULT_PATH = OUT / "kalimantan_saf_dashboard.html"
PLANS = [("MILP", "Optimised (MILP)", "facilities.csv", "flows.csv"),
         ("B1", "B1 · one central refinery", "baseline_b1_facilities.csv", "baseline_b1_flows.csv"),
         ("B2", "B2 · refinery at every airport", "baseline_b2_facilities.csv", "baseline_b2_flows.csv")]


def table(df: pd.DataFrame, num: dict | None = None) -> str:
    """HTML table; num maps column -> format string for numeric columns (right-aligned)."""
    num = num or {}
    head = "".join(f'<th class="{"n" if c in num else ""}">{html.escape(str(c))}</th>' for c in df.columns)
    rows = []
    for r in df.itertuples(index=False):
        cells = []
        for c, v in zip(df.columns, r):
            if c in num and v is not None and not (isinstance(v, float) and pd.isna(v)):
                cells.append(f'<td class="n">{num[c].format(v)}</td>')
            else:
                cells.append(f"<td>{html.escape('' if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def cost_bars(costs: pd.DataFrame) -> str:
    keep = ["CapEx annualised", "OpEx", "Logistics: biomass to depot", "Logistics: depot to refinery",
            "Logistics: refinery to airport", "Sea surcharge (Tarakan)"]
    d = costs.set_index("item").loc[keep, "usd"]
    top = d.max() or 1
    rows = "".join(
        f'<div class="bar"><span class="bl">{html.escape(k)}</span>'
        f'<span class="bt"><span class="bf" style="width:{100 * v / top:.1f}%"></span></span>'
        f'<span class="bv">${v / 1e6:,.1f}M</span></div>' for k, v in d.items())
    return f'<div class="bars">{rows}</div>'


def plan_block(key_, fac, flows, ap, sol, res, net, bio):
    if key_ == "MILP":
        c = dict(zip(res["costs"]["item"], res["costs"]["usd"]))
        total, per_t = c["Total annual cost"], c["Cost per tonne SAF"]
        capex = c["CapEx one-time: depots"] + c["CapEx one-time: refineries"]
        logistics = sum(v for k, v in c.items() if k.startswith("Logistics"))
        delta = ""
    else:
        b = res["baselines"].set_index("baseline").loc[key_]
        total, per_t, capex, logistics = b.total_annual_usd, b.cost_per_t_saf_usd, b.capex_onetime_usd, b.logistics_usd
        delta = f'<div class="delta">▲ {money(total - sol["total_annual_usd"])} more than optimised</div>'
    n_ref, n_dep = int((fac.type == "refinery").sum()), int((fac.type == "depot").sum())
    kpis = "".join(f'<div class="kpi"><div class="kl">{k}</div><div class="kv">{v}</div>{d}</div>' for k, v, d in [
        ("Total cost per year", money(total), delta), ("Cost per tonne of SAF", f"${per_t:,.0f}", ""),
        ("One-time CapEx", money(capex), ""), ("Trucking per year", money(logistics), ""),
        ("Refinery · depot sites", f"{n_ref} · {n_dep}", "")])

    m = build_map(bio, ap, fac, flows, net, fit=False)
    m.get_root().html.add_child(folium.Element("<style>html,body{height:100%;margin:0}</style>"))
    map_html = m.get_root().render()

    air = airports_table(ap, flows, sol["demand_kt"])
    f = fac.copy()
    f["Type"] = f["type"].str.title()
    f["Lat, Lon"] = f.apply(lambda r: f"{r.lat:.4f}, {r.lon:.4f}", axis=1)
    f = f.sort_values("type", ascending=False)[["Type", "site_id", "size", "Lat, Lon", "input_kt", "output_kt", "utilisation_pct"]]
    f.columns = ["Type", "Site", "Size", "Lat, Lon", "In (kt/yr)", "Out (kt/yr)", "Used"]
    r = flows.copy()
    r["Leg"] = r.leg.map(lambda l: LEGS[l][0])
    r = r[["Leg", "from_id", "to_id", "kt", "km", "cost_usd", "trips_large_truck"]]
    r.columns = ["Leg", "From", "To", "kt/yr", "Road km", "USD/yr", "Large-truck trips/yr"]
    used = flows[flows.leg == "biomass_to_depot"].groupby("from_id").kt.sum()

    costs_tab = (cost_bars(res["costs"]) + table(
        res["costs"].assign(USD=res["costs"].apply(lambda x: f"${x.usd:,.0f}" if x.basis != "USD/t" else f"${x.usd:,.2f}", axis=1))
        [["item", "USD", "basis"]].rename(columns={"item": "Item", "basis": "Basis"}))
        if key_ == "MILP" else '<p class="note">The detailed cost breakdown is for the optimised plan. '
                               'Baseline totals are in the Baselines tab.</p>')
    tabs = {
        "Airports": table(air, {"Demand (kt)": "{:,.0f}", "Delivered (kt)": "{:,.1f}", "Avg road km": "{:,.0f}"})
        + f'<p class="note">Biomass used: <b>{used.sum():,.0f} kt</b> from <b>{len(used)} of 80 sites</b>.</p>',
        "Facilities": table(f, {"In (kt/yr)": "{:,.1f}", "Out (kt/yr)": "{:,.1f}", "Used": "{:.0f}%"})
        + '<p class="note">Small and Large depots cost the same per kt, so the depot Small/Large split is a cost tie.</p>',
        "Costs": costs_tab,
        "Routes": table(r, {"kt/yr": "{:,.1f}", "Road km": "{:,.0f}", "USD/yr": "${:,.0f}", "Large-truck trips/yr": "{:,}"})
        + '<p class="note">Road km = OpenStreetMap route (OSRM) + the straight stretch from each site to its road × 1.3.</p>',
    }
    return kpis, map_html, tabs


def build(out_path=DEFAULT_PATH):
    cfg = load_config()
    bio, ap = load_biomass(cfg), load_airports(cfg)
    sol = json.loads((OUT / "solution.json").read_text())
    if not sol["ok"]:
        raise SystemExit(f"No plan to export: {sol['status']}")
    res = {"costs": pd.read_csv(OUT / "cost_breakdown.csv"), "baselines": pd.read_csv(OUT / "baselines.csv")}
    ver = json.loads((OUT / "verification.json").read_text())
    net = RoadNetwork(cfg)

    blocks = []
    for k, name, fac_file, flow_file in PLANS:
        fac, flows = pd.read_csv(OUT / fac_file), pd.read_csv(OUT / flow_file)
        net.routes_for(flows)
        blocks.append((k, name, *plan_block(k, fac, flows, ap, sol, res, net, bio)))

    gap = f"{sol['gap']:.2%}" if sol["gap"] is not None else "n/a"
    n_pass = sum(c["pass"] for c in ver["checks"])
    demand_txt = " · ".join(f"{k} {v:g}" for k, v in sol["demand_kt"].items())
    optimal = sol["status"] == "Optimal" and ver["all_pass"]
    banner = (f'<div class="banner {"ok" if optimal else "warn"}"><b>{sol["status"]}</b> · within {gap} of the best '
              f'possible plan · solved in {sol["solve_time_s"]:.0f} s · independent check {n_pass}/{len(ver["checks"])} pass · '
              f'demand {demand_txt} kt SAF/yr</div>')

    b = res["baselines"]
    milp_fac = pd.read_csv(OUT / "facilities.csv")
    base_rows = [{"Plan": "Optimised (MILP)", "Cost per year": sol["total_annual_usd"], "MILP saves": None,
                  "$/t SAF": sol["cost_per_t_saf_usd"], "Refineries": ", ".join(milp_fac[milp_fac.type == "refinery"]["size"]),
                  "Depot sites": int((milp_fac.type == "depot").sum())}]
    base_rows += [{"Plan": f"{x.baseline} · {x.name}", "Cost per year": x.total_annual_usd, "MILP saves": x.milp_saving_pct,
                   "$/t SAF": x.cost_per_t_saf_usd, "Refineries": x.refineries, "Depot sites": x.depot_sites} for x in b.itertuples()]
    checks = pd.DataFrame([{"": "✅" if c["pass"] else "❌", "Check": c["check"], "Detail": c["detail"]} for c in ver["checks"]])
    mix = pd.DataFrame(sol.get("refinery_mix_search", []))
    shared = {
        "Baselines": table(pd.DataFrame(base_rows), {"Cost per year": "${:,.0f}", "MILP saves": "{:.1f}%", "$/t SAF": "${:,.0f}"})
        + '<p class="note">All three plans use the same road distances and cost function and pass the same independent '
          'checks. Savings are modelled, not measured.</p>',
        "Checks": f'<p class="note"><b>Solver:</b> {sol["config"]["solver"]["name"]} · <b>{sol["status"]}</b> · gap {gap} '
                  f'(target {sol["config"]["solver"]["mip_gap"]:.1%}) · {sol["solve_time_s"]:.0f} s</p>' + table(checks)
        + "".join(f'<p class="note">Baseline {n}: {sum(c["pass"] for c in bv["checks"])}/{len(bv["checks"])} checks pass</p>'
                  for n, bv in ver.get("baselines", {}).items())
        + ("<h3>Refinery mixes considered</h3>" + table(
            mix.rename(columns={"mix": "Refinery mix", "result": "Result", "objective_usd": "Best plan",
                                "lower_bound_usd": "Proven lower bound", "seconds": "Seconds"}),
            {"Best plan": "${:,.0f}", "Proven lower bound": "${:,.0f}", "Seconds": "{:.0f}"}) if len(mix) else ""),
        "Assumptions": table(assumptions_table(sol["config"]))
        + '<p class="note">Every value here is an assumption from config.yaml. Facility costs, capacities and transport '
          'rates are the brief\'s figures.</p>',
    }

    tab_names = ["Airports", "Facilities", "Costs", "Routes", "Baselines", "Checks", "Assumptions"]
    plan_buttons = "".join(f'<button class="pb{" on" if i == 0 else ""}" data-plan="{k}">{html.escape(n)}</button>'
                           for i, (k, n, *_ ) in enumerate(blocks))
    tab_buttons = "".join(f'<button class="tb{" on" if i == 0 else ""}" data-tab="{t}">{t}</button>' for i, t in enumerate(tab_names))
    plan_html = []
    for i, (k, name, kpis, map_html, tabs) in enumerate(blocks):
        hidden = "" if i == 0 else " hidden"
        panes = "".join(f'<section class="pane" data-tab="{t}"{"" if t == "Airports" else " hidden"}>{tabs[t]}</section>'
                        for t in ("Airports", "Facilities", "Costs", "Routes"))
        plan_html.append(f'''
<div class="plan" data-plan="{k}"{hidden}>
  <div class="kpis">{kpis}</div>
  <div class="grid">
    <div class="mapcol"><iframe title="Map: {html.escape(name)}" srcdoc="{html.escape(map_html, quote=True)}"></iframe>
      <p class="note">Truck routes follow OpenStreetMap roads (routing by OSRM). Hover lines and markers for details.
      © OpenStreetMap contributors.</p>
      <div class="banner warn"><b>Known limit: Tarakan (TRK) is on an island.</b> Its SAF reaches it by the ferry in the
      road network, priced at the truck rate (assumption A12).</div></div>
    <div class="datacol"><div class="tabs">{tab_buttons}</div>{panes}
      {"".join(f'<section class="pane" data-tab="{t}" hidden>{shared[t]}</section>' for t in ("Baselines", "Checks", "Assumptions"))}
    </div>
  </div>
</div>''')

    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kalimantan SAF Planner</title>
<style>
:root {{ --bg:#f6f7f5; --panel:#fff; --fg:#1b2220; --muted:#52514e; --line:#d9dfdc; --accent:#0d6b5b;
  --ok:#e6f4ea; --ok-fg:#1e6b33; --warn:#fdf3dc; --warn-fg:#7a5300; --bar:#2a78d6; --bad:#d03b2f; }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 "Source Sans 3",system-ui,-apple-system,"Segoe UI",sans-serif;
  padding:24px max(16px,env(safe-area-inset-left)) 40px max(16px,env(safe-area-inset-right)) }}
.wrap {{ max-width:1400px; margin:0 auto; display:flex; flex-direction:column; gap:14px }}
h1 {{ margin:0; font-size:34px; letter-spacing:-.01em }} h3 {{ margin:14px 0 6px; font-size:14px }}
.sub {{ margin:0; color:var(--muted) }} .stamp {{ color:var(--muted); font-size:12.5px; margin:0 }}
.banner {{ padding:10px 14px; border-radius:8px; font-size:14px }}
.banner.ok {{ background:var(--ok); color:var(--ok-fg) }} .banner.warn {{ background:var(--warn); color:var(--warn-fg) }}
.plans {{ display:flex; flex-wrap:wrap; gap:6px }}
button {{ font:inherit; cursor:pointer; border:1px solid var(--line); background:var(--panel); color:var(--fg); border-radius:6px; padding:5px 12px }}
button.on {{ background:var(--accent); border-color:var(--accent); color:#fff }}
button:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px }}
.kpis {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin-bottom:12px }}
.kl {{ font-size:13px; color:var(--muted) }} .kv {{ font-size:26px; font-variant-numeric:tabular-nums }}
.delta {{ display:inline-block; font-size:12.5px; color:var(--bad); background:#fbe9e7; border-radius:10px; padding:0 8px }}
.grid {{ display:grid; grid-template-columns:minmax(0,3fr) minmax(0,2fr); gap:18px; align-items:start }}
iframe {{ width:100%; height:660px; border:1px solid var(--line); border-radius:8px; background:#e8eef0 }}
.mapcol {{ display:flex; flex-direction:column; gap:8px }}
.tabs {{ display:flex; flex-wrap:wrap; gap:4px; margin-bottom:10px }}
.tabs button {{ padding:4px 10px; font-size:14px }}
.tw {{ overflow-x:auto; border:1px solid var(--line); border-radius:8px; background:var(--panel) }}
table {{ border-collapse:collapse; width:100%; font-size:13.5px }}
th, td {{ padding:6px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top }}
th {{ font-weight:600; color:var(--muted); font-size:12.5px; background:#fafbfa; position:sticky; top:0 }}
.n {{ text-align:right; font-variant-numeric:tabular-nums }}
.note {{ color:var(--muted); font-size:13px; margin:8px 0 0 }}
.bars {{ display:flex; flex-direction:column; gap:6px; margin-bottom:12px }}
.bar {{ display:grid; grid-template-columns:200px 1fr 70px; gap:8px; align-items:center; font-size:13px }}
.bt {{ background:#eef1ef; border-radius:4px; height:16px }} .bf {{ display:block; height:16px; background:var(--bar); border-radius:0 4px 4px 0 }}
.bv {{ text-align:right; color:var(--muted); font-variant-numeric:tabular-nums }}
[hidden] {{ display:none !important }}
@media (max-width:1000px) {{ .grid {{ grid-template-columns:minmax(0,1fr) }} .kpis {{ grid-template-columns:repeat(2,minmax(0,1fr)) }}
  .bar {{ grid-template-columns:130px 1fr 60px }} }}
</style></head><body><div class="wrap">
<h1>Kalimantan SAF Planner</h1>
<p class="sub">Where to build biomass depots and SAF refineries, and how to truck everything along real roads to
Kalimantan's four international airports at the lowest annual cost.</p>
<p class="stamp">Saved {datetime.now():%d %b %Y, %H:%M} from the dashboard. This file is a snapshot; run the dashboard to re-solve.</p>
{banner}
<div class="plans" role="group" aria-label="Plan on the map">{plan_buttons}</div>
{"".join(plan_html)}
</div>
<script>
let plan = "MILP", tab = "Airports";
function show() {{
  document.querySelectorAll(".plan").forEach(p => p.hidden = p.dataset.plan !== plan);
  document.querySelectorAll(".pb").forEach(b => b.classList.toggle("on", b.dataset.plan === plan));
  const cur = document.querySelector(`.plan[data-plan="${{plan}}"]`);
  cur.querySelectorAll(".pane").forEach(p => p.hidden = p.dataset.tab !== tab);
  cur.querySelectorAll(".tb").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
}}
document.querySelectorAll(".pb").forEach(b => b.addEventListener("click", () => {{ plan = b.dataset.plan; show(); }}));
document.querySelectorAll(".tb").forEach(b => b.addEventListener("click", () => {{ tab = b.dataset.tab; show(); }}));
</script>
</body></html>'''
    out_path.write_text(page)
    return out_path


def main():
    path = build(DEFAULT_PATH if len(sys.argv) < 2 else ROOT / sys.argv[1])
    print(f"Saved {path} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
