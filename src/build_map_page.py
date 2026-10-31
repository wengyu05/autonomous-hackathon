"""Self-contained map page (no tile server) for sharing as a claude.ai artifact.

Needs data/borneo_geo.json from src/geo_extract.py.
Run: python -m src.build_map_page   ->  outputs/kalimantan_map.html
"""
import json
from pathlib import Path

from src.plot_map import (AIRPORT_LABEL_SIDE, AIRPORTS, DISTRICT_COLOURS, DISTRICT_LABEL_SIDE,
                          ISLAND_AIRPORTS, LIKELY_REFINERY_REGIONS, load_airports, load_biomass)

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "data" / "borneo_geo.json"
OUT = ROOT / "outputs" / "kalimantan_map.html"
TEMPLATE = Path(__file__).with_name("map_page_template.html")

# Natural Earth 1:10m puts BPN airport (which sits on the shore) 1.5 km offshore,
# so anything closer than this to the coast is within the coastline's error.
COAST_TOLERANCE_KM = 5.0


def build_payload():
    bio, ap = load_biomass(), load_airports()
    geo = json.loads(GEO.read_text())
    checks = geo["site_checks"]

    sites = [{
        "id": r.location_id, "district": r.district, "province": r.province,
        "kt": round(r.production_kilotons, 2), "lat": r.latitude, "lon": r.longitude,
        "offshore": not checks[r.location_id]["on_land"],
        "coast_km": checks[r.location_id]["coast_km"],
    } for r in bio.itertuples()]

    districts = []
    for d, g in bio.groupby("district"):
        kt = g.production_kilotons.sum()
        districts.append({
            "name": d, "kt": round(kt, 1), "n": len(g), "colour": DISTRICT_COLOURS[d],
            "side": DISTRICT_LABEL_SIDE.get(d, "N"),
            "lat": (g.latitude * g.production_kilotons).sum() / kt,
            "lon": (g.longitude * g.production_kilotons).sum() / kt,
            "min_lat": g.latitude.min(), "max_lat": g.latitude.max(),
            "min_lon": g.longitude.min(), "max_lon": g.longitude.max(),
        })
    districts.sort(key=lambda d: list(DISTRICT_COLOURS).index(d["name"]))

    regions = []
    for name, (members, colour) in LIKELY_REFINERY_REGIONS.items():
        g = bio[bio.district.isin(members)]
        kt = g.production_kilotons.sum()
        regions.append({
            "name": name, "colour": colour, "kt": round(kt, 1), "districts": members,
            "lat": (g.latitude * g.production_kilotons).sum() / kt,
            "lon": (g.longitude * g.production_kilotons).sum() / kt,
        })

    airports = [{
        "iata": a.iata, "brief_name": AIRPORTS[a.iata], "file_name": a.name, "city": a.city,
        "lat": a.lat, "lon": a.lon, "island": a.iata in ISLAND_AIRPORTS,
        "side": AIRPORT_LABEL_SIDE.get(a.iata, "S"),
    } for a in ap.itertuples()]

    return {
        "sites": sites, "districts": districts, "regions": regions, "airports": airports,
        "land": geo["land"], "borders": geo["borders"],
        "coast_tolerance_km": COAST_TOLERANCE_KM,
        "bpn_coast_km": geo["airport_checks"]["BPN"]["coast_km"],
    }


def main():
    payload = build_payload()
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":")))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    off = [s for s in payload["sites"] if s["offshore"]]
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1e3:.0f} kB); offshore sites: {len(off)}")


if __name__ == "__main__":
    main()
