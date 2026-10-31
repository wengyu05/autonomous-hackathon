"""Map and table builders shared by the live dashboard (app.py) and the HTML export."""
import math

import folium
import pandas as pd

from src.roads import key

# Leg colours: first three slots of the dataviz reference categorical palette, in fixed order.
LEGS = {
    "biomass_to_depot": ("Biomass → depot", "#2a78d6"),
    "depot_to_refinery": ("Depot → refinery", "#eb6834"),
    "refinery_to_airport": ("Refinery → airport", "#1baf7a"),
}


INK, INK_2, CRITICAL = "#0b0b0b", "#52514e", "#d03b2f"


def build_map(bio, ap, fac, flows, net, fit=True):
    """fit=False keeps a fixed view, for maps that start hidden (bounds can't be fitted at zero size)."""
    m = folium.Map(location=[-0.5, 113.6], zoom_start=6, tiles="OpenStreetMap", control_scale=True)
    if fit:
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
