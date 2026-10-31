"""Shared cost function: the MILP and the baselines are scored by this one evaluator.

All flows are in kt and all transport rates are USD per tonne-km, so logistics
cost = kt x KT_TO_T x km x rate.
"""
import math

import pandas as pd

KT_TO_T = 1000.0
LEGS = ("biomass_to_depot", "depot_to_refinery", "refinery_to_airport")


def capital_recovery_factor(rate: float, years: int) -> float:
    return rate / (1 - (1 + rate) ** -years)


def annual_capex_factor(cfg) -> float:
    """Per USD of CapEx: annualised capital (A8) + OpEx (A7)."""
    a = cfg["capex_annualisation"]
    return capital_recovery_factor(a["rate"], a["years"]) + cfg["opex_rate"]


def leg_cost_usd(kt: float, km: float, usd_per_tkm: float) -> float:
    return kt * KT_TO_T * km * usd_per_tkm


def truck_trips(kt: float, truck_t: float) -> int:
    return math.ceil(kt * KT_TO_T / truck_t - 1e-9) if kt > 0 else 0


def evaluate(cfg, facilities: pd.DataFrame, flows: pd.DataFrame) -> dict:
    """facilities: type ('depot'|'refinery'), n_small, n_large.
    flows: leg, to_id, kt, km. Returns the annual cost breakdown in USD."""
    fac = cfg["facilities"]
    capex = {}
    for t in ("depot", "refinery"):
        f = facilities[facilities.type == t]
        capex[t] = float((f.n_small * fac[t]["Small"]["capex_usd"] + f.n_large * fac[t]["Large"]["capex_usd"]).sum())
    capex_total = capex["depot"] + capex["refinery"]
    a = cfg["capex_annualisation"]
    crf = capital_recovery_factor(a["rate"], a["years"])

    logistics = {}
    for leg in LEGS:
        f = flows[flows.leg == leg]
        logistics[leg] = float((f.kt * KT_TO_T * f.km * cfg["transport"][leg]["usd_per_tkm"]).sum())

    to_air = flows[flows.leg == "refinery_to_airport"]
    sea_ids = {f"AIRPORT_{c}" for c in cfg["sea_leg"]["airports"]} | set(cfg["sea_leg"]["airports"])
    sea_kt = float(to_air[to_air.to_id.isin(sea_ids)].kt.sum())
    sea_cost = sea_kt * KT_TO_T * cfg["sea_leg"]["surcharge_usd_per_t"]

    total = (crf + cfg["opex_rate"]) * capex_total + sum(logistics.values()) + sea_cost
    saf_kt = float(to_air.kt.sum())
    return {
        "capex_onetime_depot_usd": capex["depot"],
        "capex_onetime_refinery_usd": capex["refinery"],
        "capex_onetime_total_usd": capex_total,
        "capex_annualised_usd": crf * capex_total,
        "opex_usd": cfg["opex_rate"] * capex_total,
        **{f"logistics_{leg}_usd": v for leg, v in logistics.items()},
        "logistics_total_usd": sum(logistics.values()),
        "sea_surcharge_usd": sea_cost,
        "total_annual_usd": total,
        "saf_delivered_kt": saf_kt,
        "cost_per_t_saf_usd": total / (saf_kt * KT_TO_T) if saf_kt > 0 else float("nan"),
    }
