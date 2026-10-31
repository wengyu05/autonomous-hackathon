"""SAF supply chain planner dashboard.

Run: .venv/bin/streamlit run app.py
"""
import json

import altair as alt
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src import baselines, verify
from src.load_data import ROOT, load_airports, load_biomass, load_config
from src.model import check_inputs, solve_by_mix, write_outputs
from src.plan_map import INK_2, LEGS, airports_table, assumptions_table, build_map, money
from src.roads import RoadNetwork, fetch_plan_routes, key

OUT = ROOT / "outputs"
st.set_page_config(page_title="Kalimantan SAF Planner", page_icon="✈️", layout="wide")


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
        if cfg["roads"]["source"] == "osrm":
            status.update(label="Fetching road shapes for new routes (about 1 per second)…")
            fetch_plan_routes(cfg, log=lambda *_: None)
    return res


# ---------- panels ----------


def cost_chart(costs: pd.DataFrame):
    keep = ["CapEx annualised", "Fixed OpEx", "Variable OpEx: depots", "Variable OpEx: refineries",
            "Logistics: biomass to depot", "Logistics: depot to refinery",
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


# ---------- page ----------

cfg_default = load_config()
bio, ap = load_inputs()
net = RoadNetwork(cfg_default)
res = load_results()
max_saf = cfg_default["refinery_yield"] * cfg_default["depot_yield"] * bio.kt.sum()

with st.sidebar:
    st.header("Airport SAF demand")
    st.caption("kt of SAF per year. The organisers set 300 kt per airport; change it to test other demand.")
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
    st.caption(("Truck routes follow OpenStreetMap roads (routing by OSRM). " if net.enabled else
                "Lines are straight: distances are great-circle km × 1.3, as the organisers specify. ")
               + "Hover lines and markers for details; the layers button (top right) turns groups on and off. "
               "© OpenStreetMap contributors.")
    st.info("**Tarakan (TRK) is on an island.** Its last leg is a barge at the same $0.08 per t·km as the truck leg, "
            "with no extra fixed cost, as the organisers specify (assumption A12).", icon="🚢")

with col_data:
    t_air, t_fac, t_cost, t_flow, t_base, t_check, t_assume = st.tabs(
        ["Airports", "Facilities", "Costs", "Routes", "Baselines", "Checks", "Assumptions"])

    with t_air:
        st.dataframe(airports_table(ap, flows, sol["demand_kt"]), hide_index=True, use_container_width=True,
                     column_config={"Demand (kt)": st.column_config.NumberColumn(format="%.0f"),
                                    "Delivered (kt)": st.column_config.NumberColumn(format="%.1f"),
                                    "Avg km": st.column_config.NumberColumn(format="%.0f")})
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
        st.caption("Capacity is biomass intake. Large units cost less to run per tonne ($4 vs $5 at depots, "
                   "$55 vs $60 at refineries), so the size split is a real decision, not a tie.")

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
                                    "km": st.column_config.NumberColumn("km", format="%.0f"),
                                    "cost_usd": st.column_config.NumberColumn("USD/yr", format="$%,.0f"),
                                    "trips_large_truck": st.column_config.NumberColumn("Large-truck trips/yr", format="%,d")})
        st.caption(("km = OpenStreetMap route between the nearest road points + the straight stretch from each site "
                    "to its road × 1.3." if net.enabled else "km = great-circle distance × 1.3.")
                   + " A depot at the same site as its refinery has a 0 km leg.")

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
        st.caption("All three plans use the same distances and cost function and pass the same independent "
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
