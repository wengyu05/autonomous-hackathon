"""Candidate depot and refinery sites (CLAUDE.md 4.2).

Depots: on-land biomass sites + on-land k-means centroids.
Refineries: the same, plus the 4 airports.
"""
import pandas as pd
from sklearn.cluster import KMeans


def point_in_land(lat: float, lon: float, geo: dict) -> bool:
    """Even-odd test against the simplified Natural Earth land polygons."""
    for poly in geo["land"]:
        outer = poly[0]
        xs = [p[0] for p in outer]
        ys = [p[1] for p in outer]
        if not (min(xs) <= lon <= max(xs) and min(ys) <= lat <= max(ys)):
            continue
        if _in_ring(lon, lat, outer) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
            return True
    return False


def _in_ring(x, y, ring) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def build_candidates(cfg, bio: pd.DataFrame, ap: pd.DataFrame, geo: dict | None, log=print) -> pd.DataFrame:
    rows, dropped = [], []
    supply_only = cfg["offshore_sites"] == "supply_only"

    for r in bio.itertuples():
        if supply_only and r.offshore:
            dropped.append((r.id, "biomass site in the sea"))
            continue
        rows.append({"cid": r.id, "kind": "biomass_site", "lat": r.lat, "lon": r.lon,
                     "depot_ok": True, "refinery_ok": True})

    k = min(cfg["candidates"]["kmeans_k"], len(bio))
    km = KMeans(n_clusters=k, random_state=cfg["candidates"]["kmeans_seed"], n_init=10)
    km.fit(bio[["lat", "lon"]].to_numpy(), sample_weight=bio.kt.to_numpy())
    b = cfg["biomass_checks"]["bbox"]
    for n, (lat, lon) in enumerate(km.cluster_centers_, start=1):
        cid = f"CENTROID_{n:02d}"
        if not (b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]):
            dropped.append((cid, "outside Kalimantan box"))
        elif geo is not None and not point_in_land(lat, lon, geo):
            dropped.append((cid, "centroid in the sea"))
        else:
            rows.append({"cid": cid, "kind": "centroid", "lat": lat, "lon": lon,
                         "depot_ok": True, "refinery_ok": True})

    if cfg["candidates"]["refinery_at_airports"]:
        for a in ap.itertuples():
            rows.append({"cid": f"AIRPORT_{a.iata}", "kind": "airport", "lat": a.lat, "lon": a.lon,
                         "depot_ok": False, "refinery_ok": True})

    cand = pd.DataFrame(rows)
    log(f"Candidates: {int(cand.depot_ok.sum())} depot, {int(cand.refinery_ok.sum())} refinery; "
        f"dropped {len(dropped)}: " + ", ".join(f"{c} ({why})" for c, why in dropped))
    cand.attrs["dropped"] = dropped
    return cand
