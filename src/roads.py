"""Road distances and route shapes from OSRM (OpenStreetMap car routing), cached locally.

Road km between two points = OSRM network km between their snapped road positions
                            + off-road access at each end (straight line to the nearest road x circuity).
OSRM's car profile includes ferries, so Tarakan is reachable by its ferry link.

Every OSRM answer is cached in data/, so solves and the dashboard only call the server for
points or routes they have never seen. Run `python -m src.roads` to fill the cache for all
candidate sites.
"""
import json
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

from src.load_data import ROOT

USER_AGENT = "saf-hackathon-planner/0.1 (Autonomous SG 2026 hackathon)"
CHUNK = 50          # sources + destinations per table request stays <= 100 coordinates
PAUSE_S = 1.1       # public server policy: about 1 request per second


def key(lat, lon) -> str:
    return f"{float(lat):.6f},{float(lon):.6f}"


class RoadNetwork:
    def __init__(self, cfg, log=print):
        rc = cfg["roads"]
        self.server = rc["server"].rstrip("/")
        self.matrix_path = ROOT / rc["matrix_cache"]
        self.routes_path = ROOT / rc["routes_cache"]
        self.offroad = cfg["circuity"]
        self.log = log
        empty = {"source": f"OSRM car profile, {self.server}", "snap_km": {}, "km": {}}
        self.m = json.loads(self.matrix_path.read_text()) if self.matrix_path.exists() else empty
        # Road shapes are only drawn when distances come from roads; great-circle plans draw straight lines.
        self.enabled = rc.get("source", "haversine") == "osrm"
        self.routes = json.loads(self.routes_path.read_text()) if self.enabled and self.routes_path.exists() else {}
        self._last_call = 0.0

    # ----- OSRM calls -----
    def _get(self, path):
        wait = PAUSE_S - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        url = f"{self.server}/{path}"
        for attempt in range(5):
            try:
                self._last_call = time.time()
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                data = json.load(urllib.request.urlopen(req, timeout=90))
                if data.get("code") != "Ok":
                    raise RuntimeError(f"OSRM error {data.get('code')}: {data.get('message')}")
                return data
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == 4:
                    raise RuntimeError(f"OSRM unreachable after 5 tries: {e}") from e
                time.sleep(2 ** attempt)

    def ensure(self, points):
        """Make sure every (lat, lon) in points has distances to every other cached point."""
        new = list(dict.fromkeys(key(*p) for p in points if key(*p) not in self.m["km"]))
        if not new:
            return
        everything = list(self.m["km"]) + new
        self.log(f"OSRM: fetching road distances for {len(new)} new points ({len(everything)} total)")
        for k in new:
            self.m["km"][k] = {}
        chunks = [everything[i:i + CHUNK] for i in range(0, len(everything), CHUNK)]
        for src in chunks:
            for dst in chunks:
                if not (set(src) & set(new) or set(dst) & set(new)):
                    continue
                pts = src + dst
                coords = ";".join(f"{k.split(',')[1]},{k.split(',')[0]}" for k in pts)
                q = (f"sources={';'.join(map(str, range(len(src))))}"
                     f"&destinations={';'.join(map(str, range(len(src), len(pts))))}&annotations=distance")
                data = self._get(f"table/v1/driving/{coords}?{q}")
                for i, s in enumerate(src):
                    self.m["snap_km"][s] = data["sources"][i]["distance"] / 1000
                    for j, d in enumerate(dst):
                        v = data["distances"][i][j]
                        self.m["km"][s][d] = None if v is None else v / 1000
        self.matrix_path.write_text(json.dumps(self.m, separators=(",", ":")))

    # ----- distances -----
    def km(self, a, b) -> float:
        """Road km from point a to b (lat, lon tuples); inf if OSRM finds no route."""
        ka, kb = key(*a), key(*b)
        if ka == kb:
            return 0.0
        net = self.m["km"][ka][kb]
        if net is None:
            return float("inf")
        return net + self.offroad * (self.m["snap_km"][ka] + self.m["snap_km"][kb])

    def matrix(self, a: pd.DataFrame, b: pd.DataFrame) -> np.ndarray:
        self.ensure(list(zip(a.lat, a.lon)) + list(zip(b.lat, b.lon)))
        return np.array([[self.km((la, lo), (lb, lob)) for lb, lob in zip(b.lat, b.lon)]
                         for la, lo in zip(a.lat, a.lon)])

    # ----- route shapes for the map -----
    def route(self, a, b):
        """[[lat, lon], ...] from a to b along roads, with the off-road ends drawn straight."""
        k = f"{key(*a)}|{key(*b)}"
        if k not in self.routes:
            data = self._get(f"route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}?overview=simplified&geometries=geojson")
            line = [[round(lat, 5), round(lon, 5)] for lon, lat in data["routes"][0]["geometry"]["coordinates"]]
            self.routes[k] = line
            self.routes_path.write_text(json.dumps(self.routes, separators=(",", ":")))
        return [list(a)] + self.routes[k] + [list(b)]

    def routes_for(self, flows: pd.DataFrame, log=None):
        """Fetch any missing route shapes for a flows table. Returns how many were fetched."""
        if not self.enabled:
            return 0
        missing = [(r.from_lat, r.from_lon, r.to_lat, r.to_lon) for r in flows.itertuples()
                   if f"{key(r.from_lat, r.from_lon)}|{key(r.to_lat, r.to_lon)}" not in self.routes
                   and key(r.from_lat, r.from_lon) != key(r.to_lat, r.to_lon)]
        if missing and log:
            log(f"OSRM: fetching {len(missing)} route shapes")
        for la, lo, lb, lob in missing:
            self.route((la, lo), (lb, lob))
        return len(missing)


def fetch_plan_routes(cfg, out_dir=None, log=print) -> int:
    """Fetch route shapes for the MILP plan and both baselines in outputs/. Returns how many were new."""
    out_dir = out_dir or ROOT / "outputs"
    net = RoadNetwork(cfg, log=log)
    total = 0
    for name in ("flows.csv", "baseline_b1_flows.csv", "baseline_b2_flows.csv"):
        p = out_dir / name
        if p.exists():
            total += net.routes_for(pd.read_csv(p), log=log)
    return total


def main():
    """Fill the distance cache for every candidate site, airport and the B1 centre.
    With --routes, fetch route shapes for the plans in outputs/ instead."""
    import sys
    from src.candidates import build_candidates
    from src.load_data import load_airports, load_biomass, load_config, load_geo
    cfg = load_config()
    if "--routes" in sys.argv:
        print(f"Fetched {fetch_plan_routes(cfg)} new route shapes")
        return
    bio, ap, geo = load_biomass(cfg), load_airports(cfg), load_geo(cfg)
    cand = build_candidates(cfg, bio, ap, geo)
    centre = ((bio.lat * bio.kt).sum() / bio.kt.sum(), (bio.lon * bio.kt).sum() / bio.kt.sum())
    pts = list(zip(bio.lat, bio.lon)) + list(zip(cand.lat, cand.lon)) + list(zip(ap.lat, ap.lon)) + [centre]
    net = RoadNetwork(cfg)
    net.ensure(pts)
    keys = list(net.m["km"])
    vals = [net.m["km"][a][b] for a in keys for b in keys if a != b]
    snaps = sorted(net.m["snap_km"].values())
    print(f"{len(keys)} points cached; {sum(v is None for v in vals)} unreachable pairs of {len(vals)}; "
          f"snap to road: median {snaps[len(snaps) // 2]:.1f} km, max {snaps[-1]:.1f} km")


if __name__ == "__main__":
    main()
