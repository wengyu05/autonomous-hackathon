"""FastAPI solver backend for the Next.js dashboard (web/).

Run:  uvicorn api:app --reload --port 8000        (docs at http://localhost:8000/docs)

Endpoints
  GET  /api/health                 solver, data and plan status
  GET  /api/config                 airports, default demand, feasibility limit, assumptions
  GET  /api/scenarios              dropdown entries for the plans in outputs/ (?distances=official|roads)
  GET  /api/results/{scenario}     one plan (optimised | b1 | b2) in the dashboard JSON contract
  POST /api/solve                  re-plan for new airport demand; returns the optimised plan

A solve runs src/pipeline.py for one distance mode: feasibility gate -> MILP (solve_by_mix) ->
outputs/ (outputs/roads/ for real roads) -> baselines -> independent verifier. Results are converted by src/export_web.py, the
same converter that writes the dashboard's static JSON. All numbers come from config.yaml and
the data files; nothing here changes an assumption except the demand sent by the client.
"""
import threading
import time
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src import pipeline
from src.export_web import WEB_DATA, NoPlan, build_all, scenario_index
from src.load_data import ROOT, load_airports, load_biomass, load_config, load_geo, outputs_dir
from src.model import check_inputs

Distances = Literal["official", "roads"]

app = FastAPI(title="Kalimantan SAF Planner API", version="1.0")

# The Next.js dev server runs on another port, so allow it to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# One solve at a time: every solve writes outputs/, which the other endpoints read.
_solve_lock = threading.Lock()

# Inputs never change while the server runs, so load them once.
_CFG = load_config()
_GEO = load_geo(_CFG)
_BIO = load_biomass(_CFG)  # same call the solver makes when given no inputs
_AP = load_airports(_CFG)


class SolveRequest(BaseModel):
    demandKt: dict[str, float] = Field(
        ..., description="SAF demand per airport in kt/yr, keyed by IATA code (PNK, PKN, BPN, TRK). "
                         "Missing airports keep their config.yaml default.",
        examples=[{"PNK": 200, "PKN": 800, "BPN": 170, "TRK": 170}])
    timeLimitS: int = Field(60, ge=10, le=600, description="Solver time limit in seconds (CLAUDE.md 4.7).")
    distances: Distances = Field("official", description="official = great-circle x 1.3 (the organisers' rule); "
                                                           "roads = cached OpenStreetMap road km.")
    fetchRoutes: bool = Field(False, description="Roads mode: fetch road shapes for new routes from the public OSRM "
                                                 "server (about 1 request per second). Off: new routes draw straight.")
    writeStatic: bool = Field(True, description="Also refresh web/public/data/*.json so the static dashboard "
                                                "shows the new plan.")


def _max_saf_kt(cfg) -> float:
    return cfg["refinery_yield"] * cfg["depot_yield"] * float(_BIO.kt.sum())


def _docs(distances: Distances = "official"):
    try:
        return build_all(outputs_dir(distances))
    except NoPlan as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/health")
def health():
    try:
        build_all()
        plan = "ready"
    except NoPlan as e:
        plan = str(e)
    return {"ok": True, "solver": _CFG["solver"]["name"], "biomassSites": len(_BIO),
            "biomassKt": float(_BIO.kt.sum()), "airports": list(_CFG["airports"]), "plan": plan,
            "solving": _solve_lock.locked()}


@app.get("/api/config")
def config():
    """What a demand form needs: airport names, defaults and the feasibility limit."""
    return {
        "airports": [{"id": r.iata, "name": r.brief_name, "lat": float(r.lat), "lng": float(r.lon),
                      "island": bool(r.island)} for r in _AP.itertuples()],
        "defaultDemandKt": _CFG["demand_kt"],
        "maxTotalDemandKt": _max_saf_kt(_CFG),
        "timeLimitS": {"default": 60, "min": 10, "max": 600},
        "assumptions": {k: _CFG[k] for k in ("mode", "refinery_yield", "depot_yield", "refinery_capacity_basis",
                                             "depot_capacity_basis", "opex_rate", "capex_annualisation",
                                             "circuity", "max_per_site", "sea_leg", "offshore_sites")},
    }


@app.get("/api/scenarios")
def scenarios(distances: Distances = "official"):
    return scenario_index(_docs(distances), prefix="/api/results/")


@app.get("/api/results/{scenario}")
def results(scenario: str, distances: Distances = "official"):
    docs = _docs(distances)
    if scenario not in docs:
        raise HTTPException(status_code=404, detail=f"Unknown scenario '{scenario}'. Options: {sorted(docs)}")
    return docs[scenario]


@app.post("/api/solve")
def solve(req: SolveRequest):
    # Plain `def`: FastAPI runs it in a worker thread, so a long solve does not block other requests.
    unknown = set(req.demandKt) - set(_CFG["airports"])
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown airport codes: {sorted(unknown)}. "
                                                    f"Use {list(_CFG['airports'])}.")
    cfg = load_config(overrides={"demand_kt": {**_CFG["demand_kt"], **req.demandKt}})

    # Feasibility gate (CLAUDE.md 3.3 / 4.8): reject before the solver is ever called.
    err = check_inputs(cfg, _BIO)
    if err:
        raise HTTPException(status_code=422, detail=err)

    if not _solve_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A solve is already running. Try again when it finishes.")
    try:
        t0 = time.perf_counter()
        res, docs = pipeline.run(cfg, req.distances, req.timeLimitS, bio=_BIO, ap=_AP, geo=_GEO,
                                 fetch_routes=req.fetchRoutes, static=req.writeStatic and WEB_DATA.parent.exists(),
                                 log=lambda *_: None)
        if not res.ok:
            # Never present an unsolved result as a plan (CLAUDE.md 6.2).
            raise HTTPException(status_code=422, detail=f"{res.status}: {res.message}")
        doc = docs["optimised"]
        doc["meta"]["pipelineSeconds"] = round(time.perf_counter() - t0, 1)
        return doc
    finally:
        _solve_lock.release()


if __name__ == "__main__":
    import uvicorn

    print(f"Serving from {ROOT}")
    uvicorn.run(app, host="127.0.0.1", port=8000)
