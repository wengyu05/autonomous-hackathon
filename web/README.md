# SAF Supply Chain Report: Kalimantan (web dashboard)

Next.js + TypeScript + Tailwind dashboard for the SAF supply chain optimiser. It reads static JSON
from `public/data/`, so it runs with no backend.

## Run

```bash
cd web
npm install
npm run dev          # http://localhost:3000
```

## Data

`public/data/` holds one JSON file per plan, in the contract defined in `lib/types.ts`:

| File | Plan |
|---|---|
| `results.json` | Optimised plan (MILP) |
| `results_b1.json` | Baseline B1: one central refinery |
| `results_b2.json` | Baseline B2: refinery at every airport |
| `scenarios.json` | Entries for the scenario dropdown (`id`, `label`, `file`) |

These are generated from the optimiser outputs, not hand-written. To refresh them after a new solve,
run from the project root:

```bash
.venv/bin/python -m src.export_web
```

`POST /api/solve` on the FastAPI backend (`api.py` at the project root) re-solves for new airport demand
and rewrites these files too. To add a sensitivity scenario, drop another file with the same shape
into `public/data/` and add a line to `scenarios.json`.

## Layout

| Component | What it shows |
|---|---|
| `Sidebar` | Slim icon rail (horizontal bar on mobile) linking to each section |
| `Header` | Title, table search, scenario dropdown, data download |
| `KpiCard` | Total cost, SAF delivered, facilities, cost per tonne, each compared with another plan |
| `NetworkMap` | Leaflet map (client-only via `NetworkMapLoader`): biomass sites, depots, refineries, airports and flows along real roads. Toggle layers in the legend; click a node to highlight its flows |
| `AirportList` | SAF delivered per airport against demand |
| `CostChart` | Annual cost donut and logistics by leg |
| `Tables` | Facility table and sortable, filterable flow table |

The status badge shows the solver result honestly: "Optimal" only when proven, otherwise
"Feasible" with the remaining optimality gap.
