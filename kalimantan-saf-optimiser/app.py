"""SAF supply chain planner dashboard.

Run: .venv/bin/streamlit run app.py
"""
import json
import math

import altair as alt
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src import baselines, verify
from src.load_data import ROOT, load_airports, load_biomass, load_config
from src.model import check_inputs, solve_by_mix, write_outputs
from src.roads import RoadNetwork, fetch_plan_routes, key

OUT = ROOT / "outputs"
st.set_page_config(page_title="Kalimantan SAF Planner", page_icon="✈️", layout="wide")

# Leg colours: first three slots of the dataviz reference categorical palette, in fixed order.
LEGS = {
    "biomass_to_depot": ("Biomass → depot", "#2a78d6"),
    "depot_to_refinery": ("Depot → refinery", "#eb6834"),
    "refinery_to_airport": ("Refinery → airport", "#1baf7a"),
}
INK, INK_2, CRITICAL = "#0b0b0b", "#52514e", "#d03b2f"

st.markdown("""
<style>
  .block-container { padding-top: 1.6rem; padding-bottom: 2rem; }
  [data-testid="stMetricValue"] { font-size: 1.65rem; font-variant-numeric: tabular-nums; }
  [data-testid="stMetricLabel"] p { font-size: 0.82rem; color: #52514e; }
  .subtitle { color: #52514e; margin: -0.6rem 0 0.8rem; font-size: 0.98rem; }
</style>""", unsafe_allow_html=True)


# ---------- data ----------

@st.cache_data
def load_inputs():
    cfg = load_config()
    return load_biomass(cfg), load_airports(cfg)


def read_csv(name):
    p = OUT / name
    return pd.read_csv(p) if p.exists() else None


def load_results():
    p = OUT / "solution.json"
    if not p.exists():
        return None
    r = {"sol": json.loads(p.read_text())}
    for k, name in (("fac", "facilities.csv"), ("flows", "flows.csv"), ("costs", "cost_breakdown.csv"),
                    ("baselines", "baselines.csv"), ("b1_fac", "baseline_b1_facilities.csv"),
                    ("b1_flows", "baseline_b1_flows.csv"), ("b2_fac", "baseline_b2_facilities.csv"),
                    ("b2_flows", "baseline_b2_flows.csv")):
        r[k] = read_csv(name)
    v = OUT / "verification.json"
    r["verify"] = json.loads(v.read_text()) if v.exists() else None
    return r


def run_solve(cfg, time_limit, status):
    status.update(label=f"Solving the MILP (up to {time_limit} s)…")
    res = solve_by_mix(cfg, time_limit=time_limit, log=lambda *_: None)
    write_outputs(cfg, res)
    if res.ok:
        status.update(label="Scoring the baselines and running the independent checks…")
        baselines.run(cfg, res.costs["total_annual_usd"])
        verify.run()
        status.update(label="Fetching road shapes for new routes (about 1 per second)…")
        fetch_plan_routes(cfg, log=lambda *_: None)
    return res


# ---------- map ----------

def build_map(bio, ap, fac, flows, net):
    m = folium.Map(location=[-0.6, 113.4], zoom_start=6, tiles="OpenStreetMap", control_scale=True)
    m.fit_bounds([[bio.lat.min() - 0.3, min(bio.lon.min(), ap.lon.min()) - 0.3],
                  [max(bio.lat.max(), ap.lat.max()) + 0.3, bio.lon.max() + 0.5]])
    max_kt = flows.kt.max() if len(flows) else 1.0

    for leg, (label, colour) in LEGS.items():
        fg = folium.FeatureGroup(name=f"Routes: {label}")
        for f in flows[flows.leg == leg].itertuples():
            a, b = (f.from_lat, f.from_lon), (f.to_lat, f.to_lon)
            if key(*a) == key(*b):
                continue  # co-located: no truck leg
            cached = f"{key(*a)}|{key(*b)}" in net.routes
            folium.PolyLine(
                net.route(a, b) if cached else [list(a), list(b)], color=colour, opacity=0.8,
                weight=1.5 + 6 * math.sqrt(f.kt / max_kt), dash_array=None if cached else "6 6",
                tooltip=f"<b>{label}</b><br>{f.from_id} → {f.to_id}<br>{f.kt:,.1f} kt/yr · {f.km:,.0f} road km<br>"
                        f"${f.cost_usd / 1e6:,.2f}M/yr · {f.trips_large_truck:,} large-truck trips/yr",
            ).add_to(fg)
        fg.add_to(m)

    used = flows[flows.leg == "biomass_to_depot"].groupby("from_id").kt.sum()
    fg = folium.FeatureGroup(name="Biomass sites (80)")
    for r in bio.itertuples():
        u = float(used.get(r.id, 0.0))
        note = f"<br><b style='color:{CRITICAL}'>In the sea ({r.coast_km:.0f} km off the coast): supply only</b>" if r.offshore else ""
        folium.CircleMarker(
            [r.lat, r.lon], radius=3 + math.sqrt(r.kt) * 0.55, weight=2 if r.offshore else 1,
            color=CRITICAL if r.offshore else INK_2, fill=True, fill_opacity=0.85 if u > 0 else 0.12,
            fill_color=INK_2,
            tooltip=f"<b>{r.id}</b> · {r.district}<br>{r.kt:.1f} kt/yr available<br>"
                    f"{'Used: ' + format(u, ',.1f') + ' kt' if u > 0 else 'Not used in this plan'}{note}",
        ).add_to(fg)
    fg.add_to(m)

    fg = folium.FeatureGroup(name="Depots")
    for d in fac[fac.type == "depot"].itertuples():
        folium.RegularPolygonMarker(
            [d.lat, d.lon], number_of_sides=4, rotation=45, radius=6 + 2 * (d.n_small + d.n_large),
            color=INK, weight=2, fill=True, fill_color="#ffffff", fill_opacity=0.95,
            tooltip=f"<b>Depot · {d.site_id}</b><br>{d.size} ({d.capacity_kt:,.0f} kt)<br>"
                    f"{d.input_kt:,.1f} kt in · {d.utilisation_pct:.0f}% used<br>{d.lat:.4f}, {d.lon:.4f}",
        ).add_to(fg)
    fg.add_to(m)
    fg = folium.FeatureGroup(name="Refineries")
    for r in fac[fac.type == "refinery"].itertuples():
        folium.Marker(
            [r.lat, r.lon], icon=folium.Icon(color="black", icon="industry", prefix="fa"),
            tooltip=f"<b>Refinery · {r.site_id}</b><br>{r.size} ({r.capacity_kt:,.0f} kt capacity)<br>"
                    f"{r.input_kt:,.1f} kt biomass in → {r.output_kt:,.1f} kt SAF<br>{r.utilisation_pct:.0f}% used"
                    f"<br>{r.lat:.4f}, {r.lon:.4f}",
        ).add_to(fg)
    fg.add_to(m)

    fg = folium.FeatureGroup(name="Airports (4)")
    delivered = flows[flows.leg == "refinery_to_airport"].groupby("to_id").kt.sum()
    for a in ap.itertuples():
        note = (f"<br><b style='color:{CRITICAL}'>On an island: routes use the ferry,<br>priced at the truck rate.</b>"
                if a.island else "")
        folium.Marker(
            [a.lat, a.lon], icon=folium.Icon(color="red" if a.island else "gray", icon="plane", prefix="fa"),
            tooltip=f"<b>{a.brief_name} ({a.iata})</b><br>{a.city.replace('Taraken', 'Tarakan')}<br>"
                    f"{float(delivered.get(a.iata, 0)):,.1f} kt SAF/yr delivered{note}",
        ).add_to(fg)
    fg.add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    rows = "".join(f'<div><span style="display:inline-block;width:18px;height:4px;background:{c};'
                   f'vertical-align:middle;margin-right:6px;border-radius:2px"></span>{n}</div>' for n, c in LEGS.values())
    m.get_root().html.add_child(folium.Element(f"""
<div style="position:fixed;bottom:22px;left:10px;z-index:9999;background:rgba(255,255,255,.94);color:{INK};
     padding:7px 10px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.25);font:11.5px/1.55 system-ui,sans-serif">
  {rows}
  <div style="color:{INK_2}">Road routes · width ∝ kt/yr</div>
  <div><i class="fa fa-industry"></i> Refinery &nbsp;<span style="display:inline-block;width:8px;height:8px;
       border:2px solid {INK};transform:rotate(45deg);margin:0 4px 0 2px"></span> Depot &nbsp;<i class="fa fa-plane"></i> Airport</div>
  <div><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:{INK_2};margin-right:4px"></span>Biomass used
       &nbsp;<span style="display:inline-block;width:9px;height:9px;border-radius:50%;border:1px solid {INK_2};margin-right:4px"></span>unused
       &nbsp;<span style="display:inline-block;width:9px;height:9px;border-radius:50%;border:2px solid {CRITICAL};margin-right:4px"></span>in the sea</div>
</div>"""))
    return m


# ---------- panels ----------

def money(v):
    return f"${v / 1e9:,.2f}B" if abs(v) >= 1e9 else f"${v / 1e6:,.1f}M"


def assumptions_table(cfg):
    a = cfg["capex_annualisation"]
    crf = a["rate"] / (1 - (1 + a["rate"]) ** -a["years"])
    roads = cfg.get("roads", {}).get("source", "haversine")
    dist = (f"OpenStreetMap road km via OSRM; site-to-road stretch = straight line × {cfg['circuity']}"
            if roads == "osrm" else f"straight line × {cfg['circuity']}")
    rows = [
        ("A1", "Mode", cfg["mode"].replace("_", " "), "Decided: produce exactly what the airports need"),
        ("A2", "Airport SAF demand", ", ".join(f"{k} {v:g}" for k, v in cfg["demand_kt"].items()) + " kt/yr", "User input; no demand data was provided"),
        ("A3", "Refinery yield", f"{cfg['refinery_yield']} t SAF per t biomass", "Not given in the brief"),
        ("A4", "Depot mass yield", f"{cfg['depot_yield']}", "No mass loss at depots"),
        ("A5", "Refinery capacity basis", cfg["refinery_capacity_basis"], "Brief's column says 'Production Capacity'"),
        ("A6", "Depot capacity basis", cfg["depot_capacity_basis"], ""),
        ("A7", "OpEx", f"{cfg['opex_rate']:.0%} of CapEx per year", "Brief names OpEx but gives no figures"),
        ("A8", "CapEx annualisation", f"{a['years']} yrs at {a['rate']:.0%} → factor {crf:.4f}", "Puts one-time CapEx on the same yearly basis as logistics"),
        ("A9", "Truck distance", dist, "Ferries count as road at the truck rate"),
        ("A10", "Facilities per site", f"≤ {cfg['max_per_site']['depot']} depots, ≤ {cfg['max_per_site']['refinery']} refineries", ""),
        ("A11", "Biomass → depot routes", "all kept" if not cfg["nearest_depots_per_site"] else f"{cfg['nearest_depots_per_site']} nearest", ""),
        ("A12", "Tarakan sea leg", f"${cfg['sea_leg']['surcharge_usd_per_t']}/t surcharge", "0 = ferry priced as road"),
        ("A13", "Offshore biomass sites", cfg["offshore_sites"].replace("_", " "), "13 sites in the sea: biomass usable, no facilities"),
    ]
    return pd.DataFrame(rows, columns=["ID", "Assumption", "Value", "Note"])


def cost_chart(costs: pd.DataFrame):
    keep = ["CapEx annualised", "OpEx", "Logistics: biomass to depot", "Logistics: depot to refinery",
            "Logistics: refinery to airport", "Sea surcharge (Tarakan)"]
    d = costs[costs["item"].isin(keep)].copy()
    d["USD M/yr"] = d.usd / 1e6
    d["label"] = d["USD M/yr"].map(lambda v: f"${v:,.1f}M")
    base = alt.Chart(d).encode(y=alt.Y("item:N", sort=keep, title=None, axis=alt.Axis(labelLimit=220)))
    bars = base.mark_bar(color="#2a78d6", cornerRadiusEnd=4, height=16).encode(
        x=alt.X("USD M/yr:Q", title="USD million per year", axis=alt.Axis(grid=True, gridOpacity=0.3)),
        tooltip=[alt.Tooltip("item:N", title="Cost"), alt.Tooltip("label:N", title="Per year")])
    text = base.mark_text(align="left", dx=4, color=INK_2).encode(x="USD M/yr:Q", text="label:N")
    return (bars + text).properties(height=230)


def airports_table(ap, flows, demand):
    l3 = flows[flows.leg == "refinery_to_airport"]
    rows = []
    for a in ap.itertuples():
        f = l3[l3.to_id == a.iata]
        kt = f.kt.sum()
        rows.append({"Airport": f"{a.iata} · {a.city.replace('Taraken', 'Tarakan')}", "Demand (kt)": demand[a.iata],
                     "Delivered (kt)": kt, "From refineries": ", ".join(f.from_id),
                     "Avg road km": (f.kt * f.km).sum() / kt if kt else 0.0})
    return pd.DataFrame(rows)


# ---------- page ----------

cfg_default = load_config()
bio, ap = load_inputs()
net = RoadNetwork(cfg_default)
res = load_results()
max_saf = cfg_default["refinery_yield"] * cfg_default["depot_yield"] * bio.kt.sum()

with st.sidebar:
    st.header("Airport SAF demand")
    st.caption("kt of SAF per year. The brief gives no demand figures, so these are inputs.")
    start = res["sol"]["demand_kt"] if res else cfg_default["demand_kt"]
    with st.form("demand"):
        demand = {code: st.number_input(f"{code} · {name}", min_value=0.0, max_value=float(max_saf), step=10.0,
                                        value=float(start[code]), key=f"d_{code}")
                  for code, name in cfg_default["airports"].items()}
        limit = st.select_slider("Solver time limit (s)", options=[60, 120, 300], value=60,
                                 help="Longer runs can prove the plan optimal; shorter runs report how close they got.")
        submitted = st.form_submit_button("Solve", type="primary", use_container_width=True)
    st.caption(f"The 6,800 kt of biomass can make at most **{max_saf:,.0f} kt** SAF a year.")
    if submitted:
        cfg = load_config(overrides={"demand_kt": demand})
        err = check_inputs(cfg, bio)
        if err:
            st.error(err)
        else:
            with st.status("Planning…", expanded=False) as status:
                run_solve(cfg, limit, status)
            st.rerun()

    st.divider()
    plan_choice = st.radio("Plan on the map", ["Optimised (MILP)", "B1 · one central refinery", "B2 · refinery at every airport"])

st.title("Kalimantan SAF Planner")
st.markdown('<p class="subtitle">Where to build biomass depots and SAF refineries, and how to truck everything '
            'along real roads to Kalimantan\'s four international airports at the lowest annual cost.</p>',
            unsafe_allow_html=True)

if res is None:
    st.info("No plan yet. Enter airport demand and press Solve.")
    st.stop()

sol = res["sol"]
ver = res["verify"]
demand_txt = " · ".join(f"{k} {v:g}" for k, v in sol["demand_kt"].items())
if not sol["ok"]:
    st.error(f"**{sol['status']}.** {sol['message']}  \nDemand asked: {demand_txt} kt SAF/yr. No plan is shown.")
    st.stop()
n_pass = sum(c["pass"] for c in ver["checks"]) if ver else 0
n_checks = len(ver["checks"]) if ver else 0
gap = f"{sol['gap']:.2%}" if sol["gap"] is not None else "n/a"
status_line = (f"**{sol['status']}** · within {gap} of the best possible plan · solved in {sol['solve_time_s']:.0f} s · "
               f"independent check {n_pass}/{n_checks} pass · demand {demand_txt} kt SAF/yr")
(st.success if sol["status"] == "Optimal" and ver and ver["all_pass"] else st.warning)(status_line, icon="✅" if sol["status"] == "Optimal" else "⏱️")

if plan_choice.startswith("B1"):
    fac, flows, plan_key = res["b1_fac"], res["b1_flows"], "B1"
elif plan_choice.startswith("B2"):
    fac, flows, plan_key = res["b2_fac"], res["b2_flows"], "B2"
else:
    fac, flows, plan_key = res["fac"], res["flows"], "MILP"

missing = sum(f"{key(r.from_lat, r.from_lon)}|{key(r.to_lat, r.to_lon)}" not in net.routes
              and key(r.from_lat, r.from_lon) != key(r.to_lat, r.to_lon) for r in flows.itertuples())
if missing:
    with st.spinner(f"Fetching {missing} road routes from OSRM (about 1 per second)…"):
        net.routes_for(flows)

milp_total = sol["total_annual_usd"]
if plan_key == "MILP":
    c = {r["item"]: r["usd"] for r in res["costs"].to_dict("records")}
    total, per_t = c["Total annual cost"], c["Cost per tonne SAF"]
    capex = c["CapEx one-time: depots"] + c["CapEx one-time: refineries"]
    logistics = sum(v for k, v in c.items() if k.startswith("Logistics"))
else:
    b = res["baselines"].set_index("baseline").loc[plan_key]
    total, per_t, capex, logistics = b.total_annual_usd, b.cost_per_t_saf_usd, b.capex_onetime_usd, b.logistics_usd
n_ref = int((fac.type == "refinery").sum())
n_dep = int((fac.type == "depot").sum())

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total cost per year", money(total),
          None if plan_key == "MILP" else f"{money(total - milp_total)} more than optimised", delta_color="inverse")
k2.metric("Cost per tonne of SAF", f"${per_t:,.0f}")
k3.metric("One-time CapEx", money(capex))
k4.metric("Trucking per year", money(logistics))
k5.metric("Refinery · depot sites", f"{n_ref} · {n_dep}")

col_map, col_data = st.columns([3, 2], gap="medium")
with col_map:
    st_folium(build_map(bio, ap, fac, flows, net), height=660, use_container_width=True, returned_objects=[],
              center=[-0.5, 113.4], zoom=6,
              key=f"map_{plan_key}_{sol['solve_time_s']:.3f}")
    st.caption("Truck routes follow OpenStreetMap roads (routing by OSRM). Hover lines and markers for details; "
               "the layers button (top right) turns groups on and off. © OpenStreetMap contributors.")
    st.warning("**Known limit: Tarakan (TRK) is on an island.** Its SAF reaches it by the ferry in the road network, "
               "priced at the truck rate. A real plan needs a barge or ferry tariff (assumption A12).", icon="⚠️")

with col_data:
    t_air, t_fac, t_cost, t_flow, t_base, t_check, t_assume = st.tabs(
        ["Airports", "Facilities", "Costs", "Routes", "Baselines", "Checks", "Assumptions"])

    with t_air:
        st.dataframe(airports_table(ap, flows, sol["demand_kt"]), hide_index=True, use_container_width=True,
                     column_config={"Demand (kt)": st.column_config.NumberColumn(format="%.0f"),
                                    "Delivered (kt)": st.column_config.NumberColumn(format="%.1f"),
                                    "Avg road km": st.column_config.NumberColumn(format="%.0f")})
        used = flows[flows.leg == "biomass_to_depot"].groupby("from_id").kt.sum()
        st.caption(f"Biomass used: **{used.sum():,.0f} kt** from **{len(used)} of 80 sites**, "
                   f"making {flows[flows.leg == 'refinery_to_airport'].kt.sum():,.0f} kt SAF.")

    with t_fac:
        f = fac.copy()
        f["type"] = f["type"].str.title()
        f["coords"] = f.apply(lambda r: f"{r.lat:.4f}, {r.lon:.4f}", axis=1)
        st.dataframe(
            f[["type", "site_id", "size", "coords", "input_kt", "output_kt", "utilisation_pct"]].sort_values("type", ascending=False),
            hide_index=True, use_container_width=True,
            column_config={
                "type": "Type", "site_id": "Site", "size": "Size", "coords": "Lat, Lon",
                "input_kt": st.column_config.NumberColumn("In (kt/yr)", format="%.1f"),
                "output_kt": st.column_config.NumberColumn("Out (kt/yr)", format="%.1f"),
                "utilisation_pct": st.column_config.ProgressColumn("Used", format="%.0f%%", min_value=0, max_value=100),
            })
        st.caption("Small and Large depots cost the same per kt, so the depot Small/Large split is a cost tie; "
                   "total capacity per site is the real decision.")

    with t_cost:
        if plan_key == "MILP":
            st.altair_chart(cost_chart(res["costs"]), use_container_width=True)
            show = res["costs"].copy()
            show["USD"] = show.apply(lambda r: f"${r.usd:,.0f}" if r.basis != "USD/t" else f"${r.usd:,.2f}", axis=1)
            st.dataframe(show[["item", "USD", "basis"]], hide_index=True, use_container_width=True,
                         column_config={"item": "Item", "basis": "Basis"})
        else:
            st.info("The detailed cost breakdown is for the optimised plan. Baseline totals are in the Baselines tab.")

    with t_flow:
        show = flows.copy()
        show["leg"] = show.leg.map(lambda l: LEGS[l][0])
        st.dataframe(show[["leg", "from_id", "to_id", "kt", "km", "cost_usd", "trips_large_truck"]],
                     hide_index=True, use_container_width=True, height=440,
                     column_config={"leg": "Leg", "from_id": "From", "to_id": "To",
                                    "kt": st.column_config.NumberColumn("kt/yr", format="%.1f"),
                                    "km": st.column_config.NumberColumn("Road km", format="%.0f"),
                                    "cost_usd": st.column_config.NumberColumn("USD/yr", format="$%,.0f"),
                                    "trips_large_truck": st.column_config.NumberColumn("Large-truck trips/yr", format="%,d")})
        st.caption("Road km = OpenStreetMap route between the nearest road points + the straight stretch from each site "
                   "to its road × 1.3. A depot at the same site as its refinery has a 0 km leg.")

    with t_base:
        b = res["baselines"]
        rows = [{"Plan": "Optimised (MILP)", "Cost per year": milp_total, "MILP saves": None,
                 "$/t SAF": sol["cost_per_t_saf_usd"],
                 "Refineries": ", ".join(res["fac"][res["fac"].type == "refinery"]["size"]),
                 "Depot sites": int((res["fac"].type == "depot").sum())}]
        rows += [{"Plan": f"{r.baseline} · {r.name}", "Cost per year": r.total_annual_usd, "MILP saves": r.milp_saving_pct,
                  "$/t SAF": r.cost_per_t_saf_usd, "Refineries": r.refineries, "Depot sites": r.depot_sites}
                 for r in b.itertuples()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     column_config={"Cost per year": st.column_config.NumberColumn(format="$%,.0f"),
                                    "$/t SAF": st.column_config.NumberColumn(format="$%,.0f"),
                                    "MILP saves": st.column_config.NumberColumn(format="%.1f%%")})
        st.caption("All three plans use the same road distances and cost function and pass the same independent "
                   "checks. Savings are modelled, not measured, and depend on the demand entered.")

    with t_check:
        st.markdown(f"**Solver:** {sol['config']['solver']['name']} · **{sol['status']}** · gap {gap} "
                    f"(target {sol['config']['solver']['mip_gap']:.1%}) · {sol['solve_time_s']:.0f} s")
        if sol["message"]:
            st.warning(sol["message"])
        if ver:
            st.dataframe(pd.DataFrame([{"": "✅" if c["pass"] else "❌", "Check": c["check"], "Detail": c["detail"]}
                                       for c in ver["checks"]]), hide_index=True, use_container_width=True)
            for name, bv in ver.get("baselines", {}).items():
                st.caption(f"Baseline {name}: {sum(c['pass'] for c in bv['checks'])}/{len(bv['checks'])} checks pass")
        mix = pd.DataFrame(sol.get("refinery_mix_search", []))
        if len(mix):
            st.markdown("**Refinery mixes considered**")
            st.dataframe(mix.rename(columns={"mix": "Refinery mix", "result": "Result", "objective_usd": "Best plan",
                                             "lower_bound_usd": "Proven lower bound", "seconds": "Seconds"}),
                         hide_index=True, use_container_width=True,
                         column_config={"Best plan": st.column_config.NumberColumn(format="$%,.0f"),
                                        "Proven lower bound": st.column_config.NumberColumn(format="$%,.0f"),
                                        "Seconds": st.column_config.NumberColumn(format="%.0f")})

    with t_assume:
        st.dataframe(assumptions_table(sol["config"]), hide_index=True, use_container_width=True)
        st.caption("Every value here is an assumption from config.yaml, not given by the organisers. "
                   "Facility costs, capacities and transport rates are the brief's figures.")
