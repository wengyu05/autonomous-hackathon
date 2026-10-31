# Kalimantan SAF Planner (web dashboard)

Next.js + TypeScript + Tailwind dashboard for the SAF supply chain optimiser. It has the same layout
and information as the Streamlit app (`app.py`): airport demand inputs and Solve on the left; title,
solver status and headline costs at the top; the road-route map beside seven data tabs.

It reads static JSON from `public/data/`, so it shows the saved plans with no backend. To re-solve
from the dashboard, also run the FastAPI backend.

## Run

```bash
cd web
npm install
npm run dev          # http://localhost:3000
```

To make **Solve** work, start the backend from the project root in another terminal:

```bash
.venv/bin/uvicorn api:app --port 8000
```

If the backend is not running, the sidebar says the solver is offline and the page keeps showing the
saved plans. Set `NEXT_PUBLIC_API_URL` to use a backend somewhere other than `http://localhost:8000`.

## Data

`public/data/` holds one JSON file per plan, in the contract defined in `lib/types.ts`:

| File | Plan |
|---|---|
| `results.json` | Optimised plan (MILP) |
| `results_b1.json` | Baseline B1: one central refinery |
| `results_b2.json` | Baseline B2: refinery at every airport |
| `scenarios.json` | The plans listed under "Plan on the map" (`id`, `label`, `file`) |

These are generated from the optimiser outputs, not hand-written. To refresh them after a new solve,
run from the project root:

```bash
.venv/bin/python -m src.export_web
```

`POST /api/solve` on the backend re-solves for new airport demand and rewrites these files; the page
then reloads them.

## Layout

| Component | What it shows |
|---|---|
| `Sidebar` | Airport SAF demand boxes (with −/+), solver time limit, Solve, the 1,360 kt feasibility limit, and the "Plan on the map" switch |
| `Header` | Title, description, and the solver status banner (status, gap, solve time, independent checks, demand) |
| `KpiCard` | The five headline numbers: total cost per year, cost per tonne of SAF, one-time CapEx, trucking per year, refinery · depot sites. Baselines show how much more they cost than the optimised plan |
| `NetworkMap` | Leaflet map (client-only via `NetworkMapLoader`) on OpenStreetMap tiles, with the Streamlit map's markers: biomass sites (filled if used, red ring if in the sea), depot diamonds, refinery and airport pins. Routes follow real roads, coloured by leg, width ∝ kt/yr, with arrows showing the direction the trucks drive. Layer switch top right; click a site to highlight its routes |
| `DataTabs` | The seven tabs beside the map: Airports, Facilities, Costs, Routes, Baselines, Checks, Assumptions |
| `AirportList` | Airports tab: demand, delivered, supplying refineries and average road km per airport |
| `CostChart` | Costs tab: annual cost bars and the full cost breakdown |
| `Tables` | Facilities, Routes, Baselines, Checks (with the refinery mixes searched) and Assumptions tabs |

The status banner shows the solver result honestly: "Optimal" only when proven, otherwise the
remaining optimality gap.
