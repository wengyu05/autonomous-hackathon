# SAF Supply Chain Optimiser: Kalimantan (Challenge #3)

Chooses where to build biomass depots and SAF refineries in Kalimantan, what size to make them, which
biomass sites to draw from, and how to truck everything to the 4 international airports, at the lowest
annual cost (CapEx + OpEx + logistics). The planner keys in each airport's SAF demand; the model re-plans.

The decisions come from an exact mixed-integer linear program (PuLP + HiGHS). Every assumption lives in
[config.yaml](config.yaml); [CLAUDE.md](CLAUDE.md) is the full spec.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.load_data                     # data checks
.venv/bin/python -m src.model                         # solve with demand from config.yaml
.venv/bin/python -m src.model --demand PNK=250 TRK=50 # override some airports
.venv/bin/python -m src.baselines                     # B1 central refinery, B2 refinery per airport
.venv/bin/python -m src.verify                        # independent check of the MILP and both baselines
.venv/bin/python -m pytest -q
.venv/bin/streamlit run app.py                        # dashboard: map + data, demand inputs, re-solve
.venv/bin/python -m src.export_html                   # save the current plan as one HTML file
```

`src.export_html` writes `outputs/kalimantan_saf_dashboard.html`: the optimised plan and both baselines with
their road-route maps and tables, in one file you can open or share without Python. Map tiles load from
the internet when it is opened.

The dashboard opens on the last plan in `outputs/`. Enter demand per airport and press **Solve**. A 60 s
limit gives a quick plan with its gap shown; pick 300 s to prove the plan optimal (about 3.5 minutes at the
default demand).

Outputs land in `outputs/`: `solution.json`, `facilities.csv`, `flows.csv`, `cost_breakdown.csv`,
`verification.json`.

### Solver API and web dashboard

```bash
.venv/bin/uvicorn api:app --reload --port 8000   # FastAPI solver backend, docs at http://localhost:8000/docs
.venv/bin/python -m src.export_web               # refresh web/public/data/*.json from outputs/
cd web && npm install && npm run dev             # Next.js dashboard at http://localhost:3000
```

`api.py` endpoints: `GET /api/health`, `GET /api/config` (airports, default demand, feasibility limit),
`GET /api/scenarios`, `GET /api/results/{optimised|b1|b2}`, and `POST /api/solve` with
`{"demandKt": {"PNK": 200, ...}, "timeLimitS": 60}`. A solve runs the same pipeline as the Streamlit app
(feasibility gate, MILP, baselines, independent verifier), returns the plan in the dashboard's JSON
contract and rewrites `web/public/data/`. Over-limit or invalid demand returns 422 without calling the
solver; a second solve while one is running returns 409.

The Next.js dashboard (`web/`) reads static JSON from `web/public/data/`, so it runs without the API. See
`web/README.md`.

## Truck distances

Every truck route uses real road distance from OpenStreetMap, routed by the public OSRM server
(`router.project-osrm.org`). Road km = the OSRM route between the nearest road points + the straight
stretch from each site to its road × 1.3. Distances are cached in `data/road_matrix.json` and route
shapes in `data/road_routes.json`, so solves run offline once the cache is filled:

```bash
.venv/bin/python -m src.roads            # fill the distance cache for all candidate sites (~20 s)
.venv/bin/python -m src.roads --routes   # fetch route shapes for the plans in outputs/ (~1 per second)
```

Set `roads.source: haversine` in config.yaml to compare against straight line × 1.3.

## How the solve works

1. **Candidates.** Depots can go at any on-land biomass site or at one of 20 k-means centres of the
   biomass. Refineries can also go at the 4 airports. Candidates in the sea are dropped.
2. **MILP.** Integer facility counts per site and size; continuous kt flows on every route; constraints
   for supply, depot and refinery capacity, mass balance, airport demand and facilities per site.
3. **Split by refinery mix.** Refineries come in a few big, expensive units, so the search is split by
   how many Small and Large refineries are built. Each mix is solved with that count fixed, or ruled out
   when its refinery cost alone exceeds the best plan found. The reported gap covers all mixes.
4. **Verify.** `src/verify.py` reloads the CSVs and raw data files and recomputes every constraint and
   the total cost without importing any model code.

## Things the data does that you should know

- **13 of the 80 biomass sites (1,153 kt) sit in the sea** in the organisers' file, almost all off
  Ketapang. Their biomass is still available, but no facility is built there (assumption A13).
- **Tarakan (TRK) is on an island.** Trucks cannot reach it; the model prices that leg as road unless a
  barge surcharge is set (A12).
- **Neither data file has airport fuel demand.** Demand is a user input (170 kt per airport by default,
  a placeholder).
- **Depots cluster next to refineries.** With no depot mass loss and leg 2 costing more per tonne-km
  than leg 1, the cheapest place to pre-process is at the refinery.
- **Depot Small/Large is a cost tie** ($15k per kt either way); the model reports capacity as
  Large + Small packing.

## Data sources

| File | Source | Licence |
|---|---|---|
| `data/kalimantan_80_locations_6800kt_full_range.csv` | Hackathon organisers (Autonomous SG 2026, Challenge #3) | Organisers' terms |
| `data/airports.dat` | OpenFlights / OurAirports, as supplied by the organisers | ODbL / public domain |
| `data/road_matrix.json`, `data/road_routes.json` | Road distances and shapes from OSRM on OpenStreetMap data | © OpenStreetMap contributors, ODbL |
| `data/borneo_geo.json` | Natural Earth 1:10m land and borders, clipped to Borneo | Public domain |

## Maps

- `python -m src.plot_map` builds a local folium map of the input data.
- `python -m src.build_map_page` builds the self-contained shareable map page.
- `src/geo_extract.py` clips Natural Earth 1:10m coastline (public domain) to Borneo and flags offshore
  sites; it needs the Natural Earth GeoJSON files downloaded separately.
