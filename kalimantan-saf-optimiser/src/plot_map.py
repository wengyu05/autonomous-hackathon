"""Pre-solve map of the raw data: biomass sites by district, the 4 airports,
and the likely refinery regions (a hand estimate, replaced by solver output later).

Run: python -m src.plot_map   ->  outputs/map_data.html
"""
from pathlib import Path

import folium
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "outputs" / "map_data.html"

# The only 4 airports in scope (brief name -> IATA code used to match airports.dat).
AIRPORTS = {
    "PNK": "Supadio Intl",
    "PKN": "Iskandar Intl",
    "BPN": "Sultan Aji Muhammad Sulaiman Sepinggan Intl",
    "TRK": "Juwata Intl",
}
ISLAND_AIRPORTS = {"TRK"}

DISTRICT_COLOURS = {
    "Ketapang": "#1f5fa8",
    "Sanggau": "#5fa8e0",
    "Kotawaringin Barat": "#1d8a3a",
    "Kotawaringin Timur": "#7cc576",
    "Kutai Kartanegara": "#6a3d9a",
    "Paser": "#b294c7",
    "Tanah Laut": "#8c564b",
    "Bulungan": "#d99a00",
}

# Hand estimate from the data profile, NOT solver output. Shown only as dashed zones.
LIKELY_REFINERY_REGIONS = {
    "West": (["Ketapang", "Sanggau"], "#1f5fa8"),
    "Central": (["Kotawaringin Barat", "Kotawaringin Timur"], "#1d8a3a"),
    "East": (["Kutai Kartanegara", "Paser"], "#6a3d9a"),
}
REGION_PAD_DEG = 0.12  # how far the dashed zone sits outside the outermost sites

# Which side of its cluster each district label sits on, chosen to avoid airport labels.
DISTRICT_LABEL_SIDE = {
    "Ketapang": "W", "Sanggau": "N", "Kotawaringin Barat": "S", "Kotawaringin Timur": "N",
    "Kutai Kartanegara": "N", "Paser": "W", "Tanah Laut": "S", "Bulungan": "W",
}
AIRPORT_LABEL_SIDE = {"PNK": "W", "PKN": "W", "BPN": "E", "TRK": "E"}
LABEL_GAP_DEG = 0.08

AIRPORT_COLS = ["id", "name", "city", "country", "iata", "icao", "lat", "lon",
                "alt", "tz_offset", "dst", "tz", "type", "source"]


def load_biomass() -> pd.DataFrame:
    df = pd.read_csv(DATA / "kalimantan_80_locations_6800kt_full_range.csv")
    assert len(df) == 80, len(df)
    assert abs(df.production_kilotons.sum() - 6800) < 1e-6
    assert ((df.production_kilotons * 1000 - df.production_tonnes).abs() < 1e-6).all()
    return df


def load_airports() -> pd.DataFrame:
    path = next(DATA.glob("airport*.dat"))
    df = pd.read_csv(path, header=None, names=AIRPORT_COLS)
    df = df[df.iata.isin(AIRPORTS)].copy()
    assert sorted(df.iata) == sorted(AIRPORTS), df.iata.tolist()
    df["brief_name"] = df.iata.map(AIRPORTS)
    return df


def convex_hull(points):
    """Andrew's monotone chain on (lon, lat) tuples."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def padded_hull(sites: pd.DataFrame):
    hull = convex_hull(list(zip(sites.longitude, sites.latitude)))
    clon, clat = sites.longitude.mean(), sites.latitude.mean()
    out = []
    for lon, lat in hull:
        dlon, dlat = lon - clon, lat - clat
        norm = (dlon ** 2 + dlat ** 2) ** 0.5 or 1.0
        out.append((lat + REGION_PAD_DEG * dlat / norm, lon + REGION_PAD_DEG * dlon / norm))
    return out


def label(html: str, size: int = 12, side: str = "C") -> folium.DivIcon:
    """Text label; `side` says where the text sits relative to its point (N/S/W/E/C)."""
    w, h = 220, 40
    anchor, align, valign = {
        "N": ((w // 2, h), "center", "flex-end"),
        "S": ((w // 2, 0), "center", "flex-start"),
        "W": ((w, h // 2), "right", "center"),
        "E": ((0, h // 2), "left", "center"),
        "C": ((w // 2, h // 2), "center", "center"),
    }[side]
    return folium.DivIcon(
        icon_size=(w, h), icon_anchor=anchor,
        html=f'<div style="height:{h}px;display:flex;flex-direction:column;'
             f'justify-content:{valign};text-align:{align};font:600 {size}px/1.25 system-ui,'
             f'sans-serif;color:#222;text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff">'
             f'{html}</div>',
    )


def build_map(bio: pd.DataFrame, ap: pd.DataFrame) -> folium.Map:
    m = folium.Map(location=[-0.6, 113.4], zoom_start=6, tiles="OpenStreetMap",
                   control_scale=True)

    regions = folium.FeatureGroup(name="Likely refinery regions (hand estimate)")
    for region, (districts, colour) in LIKELY_REFINERY_REGIONS.items():
        sites = bio[bio.district.isin(districts)]
        kt = sites.production_kilotons.sum()
        folium.Polygon(
            padded_hull(sites), color=colour, weight=2, dash_array="8 6",
            fill=True, fill_opacity=0.06,
            tooltip=f"<b>Likely refinery region: {region}</b><br>{kt:,.0f} kt biomass "
                    f"({kt / 6800:.0%})<br><i>Hand estimate, not solver output</i>",
        ).add_to(regions)
    regions.add_to(m)

    sites_fg = folium.FeatureGroup(name="Biomass sites (80)")
    for r in bio.itertuples():
        folium.CircleMarker(
            [r.latitude, r.longitude], radius=2 + r.production_kilotons ** 0.5 * 0.7,
            color="#fff", weight=1, fill=True, fill_opacity=0.9,
            fill_color=DISTRICT_COLOURS[r.district],
            tooltip=f"<b>{r.location_id}</b><br>{r.district}, {r.province}<br>"
                    f"{r.production_kilotons:.1f} kt/yr<br>{r.latitude:.4f}, {r.longitude:.4f}",
        ).add_to(sites_fg)
    sites_fg.add_to(m)

    labels = folium.FeatureGroup(name="District labels")
    for district, g in bio.groupby("district"):
        kt = g.production_kilotons.sum()
        lat = (g.latitude * g.production_kilotons).sum() / kt
        lon = (g.longitude * g.production_kilotons).sum() / kt
        side = DISTRICT_LABEL_SIDE.get(district, "N")
        lat, lon = {
            "N": (g.latitude.max() + LABEL_GAP_DEG, lon),
            "S": (g.latitude.min() - LABEL_GAP_DEG, lon),
            "W": (lat, g.longitude.min() - LABEL_GAP_DEG),
            "E": (lat, g.longitude.max() + LABEL_GAP_DEG),
        }[side]
        folium.Marker(
            [lat, lon],
            icon=label(f"{district}<br>{kt:,.0f} kt · {len(g)} sites", 11, side),
        ).add_to(labels)
    labels.add_to(m)

    airports = folium.FeatureGroup(name="Airports (4)")
    for a in ap.itertuples():
        island = a.iata in ISLAND_AIRPORTS
        note = ("<br><b style='color:#c0392b'>Island: no road link. "
                "Needs a barge or ship leg.</b>" if island else "")
        folium.Marker(
            [a.lat, a.lon],
            icon=folium.Icon(color="red" if island else "black", icon="plane", prefix="fa"),
            tooltip=f"<b>{a.brief_name} ({a.iata})</b><br>{a.city}<br>"
                    f"{a.lat:.4f}, {a.lon:.4f}{note}",
        ).add_to(airports)
        text = f"{a.iata} · {a.city}" + ("<br><span style='color:#c0392b'>island</span>" if island else "")
        side = AIRPORT_LABEL_SIDE.get(a.iata, "S")
        dlat, dlon = {"N": (0.35, 0), "S": (-0.06, 0), "W": (0.15, -0.2), "E": (0.15, 0.2)}[side]
        folium.Marker([a.lat + dlat, a.lon + dlon], icon=label(text, 12, side)).add_to(airports)
    airports.add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    m.fit_bounds([[bio.latitude.min() - 0.4, min(bio.longitude.min(), ap.lon.min()) - 0.4],
                  [max(bio.latitude.max(), ap.lat.max()) + 0.4, bio.longitude.max() + 0.6]])
    m.get_root().html.add_child(folium.Element(legend_html(bio)))
    return m


def legend_html(bio: pd.DataFrame) -> str:
    totals = bio.groupby("district").production_kilotons.sum()
    rows = "".join(
        f'<div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        f'background:{c};margin-right:6px"></span>{d} <span style="color:#666">'
        f'{totals[d]:,.0f} kt</span></div>'
        for d, c in DISTRICT_COLOURS.items()
    )
    return f"""
<div style="position:fixed;bottom:24px;right:12px;z-index:9999;background:rgba(255,255,255,.94);
     padding:8px 10px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);
     font:11px/1.45 system-ui,sans-serif;max-width:230px">
  <div style="font-weight:700;margin-bottom:4px">Kalimantan SAF: input data</div>
  <div style="color:#444;margin-bottom:6px">80 biomass sites · 6,800 kt/yr · circle size ∝ kt</div>
  {rows}
  <div style="margin-top:6px"><i class="fa fa-plane"></i> Airport &nbsp;
    <i class="fa fa-plane" style="color:#c0392b"></i> Island airport (TRK)</div>
  <div style="margin-top:4px;color:#555">Dashed zones: likely refinery regions.
    <b>Hand estimate, not solver output.</b></div>
</div>"""


def main():
    bio, ap = load_biomass(), load_airports()
    print(ap[["brief_name", "name", "city", "iata", "lat", "lon"]].to_string(index=False))
    OUT.parent.mkdir(exist_ok=True)
    build_map(bio, ap).save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
