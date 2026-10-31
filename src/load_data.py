"""Read config and input files, validate them, and print the checks.

Run: python -m src.load_data
"""
import copy
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent


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


# Distance modes the dashboards switch between (A9). "official" is the organisers' great-circle x circuity;
# "roads" uses cached OpenStreetMap road km. Each mode keeps its own results folder.
DISTANCE_MODES = {"official": "haversine", "roads": "osrm"}


def distance_config(cfg, mode: str) -> dict:
    return deep_merge(cfg, {"roads": {"source": DISTANCE_MODES[mode]}})


def outputs_dir(mode: str) -> Path:
    return ROOT / "outputs" if mode == "official" else ROOT / "outputs" / mode


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
    """The 4 airports from the organisers' challenge3_airports_4.csv, with their SAF demand."""
    path = ROOT / cfg["data"]["airports_csv"]
    if not path.exists():
        raise FileNotFoundError(f"Airport file missing: put challenge3_airports_4.csv at {path}")
    raw = pd.read_csv(path)
    wanted = cfg["airports"]
    missing = set(wanted) - set(raw.iata)
    if missing:
        raise ValueError(f"IATA codes not found in {path.name}: {sorted(missing)}")
    df = raw[raw.iata.isin(wanted)].set_index("iata").loc[list(wanted)].reset_index()  # config order
    df = df.rename(columns={"latitude": "lat", "longitude": "lon", "saf_demand_kt_per_year": "demand_kt"})
    df["brief_name"] = df.iata.map(wanted)
    df["island"] = df.iata.isin(cfg["sea_leg"]["airports"])
    return df[["iata", "brief_name", "name", "city", "lat", "lon", "island", "demand_kt"]]


def check_parameters(cfg) -> list[str]:
    """Differences between config.yaml and the organisers' challenge3_parameters.xlsx / airports CSV.
    Empty list = config matches the given numbers."""
    issues = []
    xlsx = ROOT / cfg["data"]["parameters_xlsx"]
    if xlsx.exists():
        fac = pd.read_excel(xlsx, "facilities", header=2)
        for r in fac.itertuples():
            mine = cfg["facilities"][r.facility.lower()][r.size]
            for key, given in (("capex_usd", r.capex_usd), ("capacity_kt", r.capacity_kt_biomass_in_per_year),
                               ("variable_opex_usd_per_t", r.variable_opex_usd_per_tonne_in)):
                if abs(mine[key] - given) > 1e-9:
                    issues.append(f"{r.facility} {r.size} {key}: config {mine[key]} vs given {given}")
            if abs(cfg["opex_rate"] * r.capex_usd - r.fixed_opex_usd_per_year) > 1e-6:
                issues.append(f"{r.facility} {r.size} fixed OpEx: config {cfg['opex_rate']} x CapEx vs given {r.fixed_opex_usd_per_year}")
        legs = dict(zip(("biomass_to_depot", "depot_to_refinery", "refinery_to_airport"),
                        pd.read_excel(xlsx, "transport", header=2).cost_usd_per_tonne_km))
        for leg, given in legs.items():
            if abs(cfg["transport"][leg]["usd_per_tkm"] - given) > 1e-9:
                issues.append(f"{leg} rate: config {cfg['transport'][leg]['usd_per_tkm']} vs given {given}")
    ap = load_airports(cfg)
    for r in ap.itertuples():
        if abs(cfg["demand_kt"][r.iata] - r.demand_kt) > 1e-9:
            issues.append(f"{r.iata} demand: config {cfg['demand_kt'][r.iata]} vs given {r.demand_kt}")
    return issues


def main():
    cfg = load_config()
    bio, ap = load_biomass(cfg), load_airports(cfg)
    print(f"Biomass: {len(bio)} sites, {bio.kt.sum():,.1f} kt, min {bio.kt.min()} max {bio.kt.max()}")
    off = bio[bio.offshore]
    print(f"Offshore (supply only, A13): {len(off)} sites, {off.kt.sum():,.1f} kt: {off.id.tolist()}")
    print("Airports (challenge3_airports_4.csv):")
    print(ap.to_string(index=False))
    issues = check_parameters(cfg)
    print("config.yaml matches the organisers' parameters" if not issues else "MISMATCH:\n  " + "\n  ".join(issues))


if __name__ == "__main__":
    main()
