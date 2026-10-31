"""Read config and input files, validate them, and print the checks.

Run: python -m src.load_data
"""
import copy
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
AIRPORT_COLS = ["id", "name", "city", "country", "iata", "icao", "lat", "lon",
                "alt", "tz_offset", "dst", "tz", "type", "source"]


def load_config(path=None, overrides=None) -> dict:
    cfg = yaml.safe_load(Path(path or ROOT / "config.yaml").read_text())
    if overrides:
        cfg = deep_merge(cfg, overrides)
    return cfg


def deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_geo(cfg) -> dict | None:
    path = ROOT / cfg["data"]["geo_json"]
    return json.loads(path.read_text()) if path.exists() else None


def load_biomass(cfg, geo=None) -> pd.DataFrame:
    path = ROOT / cfg["data"]["biomass_csv"]
    if not path.exists():
        raise FileNotFoundError(f"Biomass file missing: put it at {path}")
    raw = pd.read_csv(path)
    chk = cfg["biomass_checks"]
    df = pd.DataFrame({
        "id": raw.location_id, "province": raw.province, "district": raw.district,
        "kt": raw.production_kilotons.astype(float),
        "lat": raw.latitude.astype(float), "lon": raw.longitude.astype(float),
    })
    assert len(df) == chk["n_sites"], f"expected {chk['n_sites']} sites, got {len(df)}"
    assert df.id.is_unique, "duplicate location_id"
    assert abs(df.kt.sum() - chk["total_kt"]) < 1e-6, f"total {df.kt.sum()} kt != {chk['total_kt']}"
    assert df.kt.min() >= chk["min_kt"] and df.kt.max() <= chk["max_kt"], "kt outside brief's range"
    assert ((raw.production_kilotons * 1000 - raw.production_tonnes).abs() < 1e-6).all(), "kt/t columns disagree"
    b = chk["bbox"]
    inside = df.lat.between(b["lat_min"], b["lat_max"]) & df.lon.between(b["lon_min"], b["lon_max"])
    assert inside.all(), f"sites outside Kalimantan box: {df.id[~inside].tolist()}"

    geo = geo if geo is not None else load_geo(cfg)
    if geo is None:
        print("WARNING: no coastline file; offshore check skipped (run src/geo_extract.py)")
        df["offshore"], df["coast_km"] = False, float("nan")
    else:
        df["offshore"] = df.id.map(lambda i: not geo["site_checks"][i]["on_land"])
        df["coast_km"] = df.id.map(lambda i: geo["site_checks"][i]["coast_km"])
    return df


def load_airports(cfg) -> pd.DataFrame:
    paths = sorted(ROOT.glob(cfg["data"]["airports_glob"]))
    if not paths:
        raise FileNotFoundError(f"Airport file missing: put airports.dat in {ROOT / 'data'}")
    df = pd.read_csv(paths[0], header=None, names=AIRPORT_COLS)
    wanted = cfg["airports"]
    df = df[df.iata.isin(wanted)].copy()
    missing = set(wanted) - set(df.iata)
    if missing:
        raise ValueError(f"IATA codes not found in {paths[0].name}: {sorted(missing)}")
    df["brief_name"] = df.iata.map(wanted)
    df["island"] = df.iata.isin(cfg["sea_leg"]["airports"])
    df = df.set_index("iata").loc[list(wanted)].reset_index()  # config order
    return df[["iata", "brief_name", "name", "city", "lat", "lon", "island"]]


def main():
    cfg = load_config()
    bio, ap = load_biomass(cfg), load_airports(cfg)
    print(f"Biomass: {len(bio)} sites, {bio.kt.sum():,.1f} kt, min {bio.kt.min()} max {bio.kt.max()}")
    off = bio[bio.offshore]
    print(f"Offshore (supply only, A13): {len(off)} sites, {off.kt.sum():,.1f} kt: {off.id.tolist()}")
    print("Airports matched on IATA:")
    print(ap.to_string(index=False))


if __name__ == "__main__":
    main()
