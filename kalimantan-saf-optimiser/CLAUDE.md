# Handoff: SAF Supply Chain Optimiser for Kalimantan (Hackathon Challenge #3)

Read this whole file before writing code. It is the source of truth for the problem, the data, the assumptions and the build order.

---

## Spec revisions (31 Oct 2026, rev 3)

### Rev 3: team decisions

| # | Change | Sections |
|---|---|---|
| R8 | **A1 decided: `meet_demand`.** The solver produces exactly what the airports need, at the lowest total cost, and chooses which biomass sites to draw from | 3 (A1), 4.5 |
| R9 | **A2 is a user input.** The planner keys in SAF demand (kt/yr) per airport and clicks Solve. The solver re-plans sites, sizes and routes. Default on load: 170 kt per airport, labelled placeholder. Neither data file contains fuel or traffic data | 3 (A2), 3.3, 8 |
| R10 | **Feasibility gate.** Total demand must be ≤ refinery yield × total biomass (1,360 kt at 0.20). Reject larger inputs with a clear message before solving | 3.3, 4.8 |
| R11 | **Offshore biomass sites (A13): supply only.** 13 sites (1,153 kt) are in the sea in the organisers' data. Keep their biomass and coordinates unchanged, but build no depot or refinery there, and drop any k-means candidate that falls in the sea | 3 (A13), 4.2 |
| R12 | **New output: cost per tonne of SAF** (total annual cost ÷ SAF delivered), shown next to total cost | 5, 8 |
| R13 | **Solver: PuLP 3.x + HiGHS** (CBC fallback). PuLP 4 is a rewrite with a different API and no bundled CBC, so pin `pulp>=3.3,<4` | 9 |
| R15 | **Truck distances follow real roads.** OSRM (OpenStreetMap) road km for every route, cached locally; the map draws each route along its road. All 101 points connect, Tarakan included via its ferry. The verifier checks every distance against the cached road matrix | 3 (A9), 8 |
| R14 | **Formulation strengthened** (exact, same optimum): depot capacity as 150 kt modules (Small/Large are a cost tie), flow-to-open-site linking inequalities, and a refinery capacity cover cut. **Search split by refinery mix:** each Small/Large refinery count is solved with the totals fixed or ruled out by its cost floor; the reported gap covers all mixes | 4.9 |

### Rev 2

Changes from rev 1.

| # | Change | Sections |
|---|---|---|
| R1 | **Removed biomass → depot arc pruning.** Rev 1 kept only the 10 nearest depot candidates per biomass site. That limit, not the economics, would have decided where depots go (see 3.2). The full model is still small (~19k continuous variables). Pruning is now an opt-in config value, off by default | 3 (A11), 4.7 |
| R2 | **Documented that depots are pulled toward refineries** under the given data (yield 1.0, leg 2 rate > leg 1 rate). Added depot yield to the sensitivity sweep | 3 (A4), 3.2, 7.2 |
| R3 | **Documented that depot size is a tie.** Small and Large both cost $15k/kt, so the Small/Large choice for depots is arbitrary. Report it as such | 3.2, 5, 8 |
| R4 | **Fixed the input-basis sanity number.** The cheapest mix is 6 Large + 1 Small ($5.07B), not 7 Large ($5.36B) | 3.1 |
| R5 | **Documented that A1 and A2 are coupled.** With the placeholder demand, `meet_demand` gives the same answer as `process_all`. The mode run only means something once real demand figures exist | 3 (A1, A2), 7.2 |
| R6 | **Added an optional sea-leg surcharge for Tarakan (TRK)**, off by default (flag only). The team supplies the rate if it wants it priced | 3 (A12), 4.3, 4.6, 7.3 |
| R7 | Updated the model size estimate and the definition of done to match | 4.7, 12 |

---

## 0. Context

- **Event:** Autonomous SG 2026, AI & Aerospace Track (Airbus problem statements), NUS, 31 Oct 2026.
- **Time budget:** 6 hours total, including the 3-minute pitch. Earlier submission scores points.
- **Team decision:** We chose Challenge #3, the SAF (Sustainable Aviation Fuel) supply chain in Kalimantan.
- **Method decision:** Mixed-integer linear program (MILP) solved by an exact solver (CBC or HiGHS). No heuristic optimisers. See Section 6.

---

## 1. Problem statement (from the organisers)

Kalimantan (Indonesian Borneo) has large agricultural and forestry residues. We must design a supply chain that turns this biomass into SAF and delivers it to Kalimantan's 4 international airports.

**Objective:** Minimise total cost = OpEx + CapEx + Logistics, while meeting SAF demand at the 4 airports.

**Required outputs:**
1. Optimal coordinates of depots and refineries.
2. Facility sizing decisions (Small vs Large).
3. Material flow network.
4. Infrastructure placement (locations and sizes of pre-processing depots and SAF refineries).
5. Optimal routing: biomass sites → depots → refineries → airports.

**Network (every tonne must pass through each stage in order):**

```
80 biomass sites ──truck──> pre-processing depots ──truck──> SAF refineries ──truck──> 4 airports
```

### 1.1 Facility data (given)

| Facility | Size | CapEx (USD) | Capacity (kt) | CapEx per kt |
|---|---|---|---|---|
| Depot | Small | 2,250,000 | 150 | $15,000 |
| Depot | Large | 4,500,000 | 300 | $15,000 |
| Refinery | Small | 480,000,000 | 500 | $960,000 |
| Refinery | Large | 765,000,000 | 1,087 | ~$703,800 |

### 1.2 Transport data (given)

| Leg | Small truck | Large truck | Cost (USD per tonne per km) |
|---|---|---|---|
| Biomass site → depot | 3 t | 9 t | 0.10 |
| Depot → refinery | 18 t | 30 t | 0.12 |
| Refinery → airport | 16 t | 32 t | 0.08 |

Truck size does **not** change cost (same rate per tonne-km). Use truck size only to report trip counts after solving.

### 1.3 Airports (only these 4)

| Name in brief | City | IATA (use to match) |
|---|---|---|
| Supadio Intl | Pontianak | PNK |
| Iskandar Intl | Pangkalan Bun | PKN |
| Sultan Aji Muhammad Sulaiman Sepinggan Intl | Balikpapan | BPN |
| Juwata Intl | Tarakan | TRK |

### 1.4 Biomass

- 80 sites, 20–100 kt each, 6,800 kt total.
- Treat amounts as **annual** tonnes.

---

## 2. Data files

The team will place the files in `data/`. Original paths in the organisers' Drive:

| File | Original path | Notes |
|---|---|---|
| Airports | `Challenge #3 - SAF\Airport location\airport.dat` | Confirmed file name: `airports.dat`. Glob for `airport*.dat`. It is the **full global OpenFlights file** (7,698 rows), not a 4-row file. No header, comma-separated, quoted strings. Columns: ID, Name, City, Country, IATA, ICAO, Latitude, Longitude, Altitude, Timezone, DST, Tz, Type, Source. All 4 IATA codes match. Names do not match the brief ("Supadio Airport", city "Taraken"), so the name fallback would fail. Match on IATA only |
| Biomass | `Challenge #3 - SAF\Biomass locations\kalimantan_80_locations_6800kt_full_range.csv` | Confirmed columns: `location_id, province, district, production_kilotons, production_tonnes, latitude, longitude`. Use `production_kilotons`. Assert `production_tonnes == 1000 × production_kilotons` on load |

Paths contain spaces and `#`. Always quote them.

### 2.1 Data rules

- **Never hardcode coordinates or amounts from memory.** Read them from the files.
- If a file is missing, stop and ask the user to put it in `data/`.
- On load, print and assert:
  - Biomass: 80 rows, sum ≈ 6,800 kt, min ≥ 20, max ≤ 100, all coordinates inside roughly lat −4.5 to 4.5, lon 108 to 119.5 (Kalimantan bounding box).
  - Airports: exactly 4 rows after filtering by IATA code. Print the matched rows so a human can confirm. If an IATA match fails, fall back to a case-insensitive name match and print a warning.

---

## 3. Open decisions and default assumptions

The organisers left key numbers out. Every item below must live in `config.yaml`, never inline in code. Every default is an **assumption** and must be shown in the dashboard's Assumptions panel.

| # | Item | Default | Why it matters |
|---|---|---|---|
| A1 | **Mode**: `process_all` (all 6,800 kt must be processed) or `meet_demand` (use only the biomass needed) | `meet_demand` | **Decided (rev 3).** `process_all` stays available for sensitivity runs |
| A2 | Airport SAF demand (kt/year), config key `demand_kt` | 170 kt per airport (placeholder). **User input** in the dashboard | Not given in the brief, and neither data file has fuel or traffic data. See 3.3 |
| A3 | Refinery yield (t SAF per t biomass input) | 0.20 | Not given. Test 0.15–0.30 |
| A4 | Depot mass yield (t out per t in) | 1.00 (no mass loss) | Not given. At 1.00 depots add no logistics value and get pulled toward refineries (see 3.2). Test 0.6–1.0 |
| A5 | Refinery capacity basis: `input` (biomass in) or `output` (SAF out) | `output` (the brief says "Production Capacity") | Changes refinery count by ~5x. Run both |
| A6 | Depot capacity basis | `input` (biomass throughput) | |
| A7 | OpEx | 5% of CapEx per year | Brief names OpEx but gives no numbers |
| A8 | CapEx annualisation | 20 years at 8% → capital recovery factor ≈ 0.1019 | CapEx is one-time, logistics is yearly. Without this the model just minimises refinery count |
| A9 | Road distance | **Real roads (rev 3, R15):** OpenStreetMap road km from OSRM (`router.project-osrm.org`), cached in `data/road_matrix.json`, plus the off-road stretch from each site to its nearest road (straight line × 1.3). Ferries count as road at the truck rate. `roads.source: haversine` restores straight line × 1.3 for comparison | Straight-line × 1.3 understated Borneo roads by about half |
| A10 | Max facilities per candidate site | Depots: 4, Refineries: 2 | Keeps the model bounded. Caps one site at 1,200 kt of depot capacity, so depots must spread over ≥ 6 sites in `process_all` |
| A11 | Biomass → depot arc pruning, config key `nearest_depots_per_site` | `null` = keep all arcs | Pruning changes the answer (see 3.2). Only set a number if solve time is a problem, and report it in the Assumptions panel |
| A12 | Sea leg to Tarakan (TRK), config keys `sea_leg.airports: [TRK]`, `sea_leg.surcharge_usd_per_t` | Surcharge `0` = flag only, priced as road | Tarakan is an island; no truck route exists. Team supplies a barge rate if it wants this priced |
| A13 | Offshore biomass sites, config key `offshore_sites` | `supply_only`: keep their biomass, build nothing there | 13 sites sit in the sea in the organisers' data (checked against Natural Earth 1:10m coastline, `data/borneo_geo.json`) |

If the user gives a different value for any of these, update `config.yaml` and re-run. Do not silently change a default.

### 3.1 Sanity numbers to check results against

- `process_all` needs at least 23 Large depots' worth of capacity (6,800 / 300 = 22.7). Depot CapEx floor: 46 × 150 kt units ≈ $104M (~$16M/year annualised with OpEx).
- Refinery count swings by capacity basis:

| Reading | Refinery capacity needed | Cheapest mix (CapEx only) |
|---|---|---|
| A5 = `input`, A1 = `process_all` | 6,800 kt input | **6 Large + 1 Small** = 7,022 kt, **$5.07B** (7 Large = $5.36B is dearer) |
| A5 = `output`, yield 0.20 | 1,360 kt SAF | 1 Large + 1 Small = 1,587 kt, $1.245B (3 Small = $1.44B, 2 Large = $1.53B) |

- The solver may pick a dearer CapEx mix if it saves more in logistics (for example, refineries at two sites). That is not a bug, but check that the trade-off adds up.
- Annualisation factor (CRF + OpEx) ≈ 0.152. One Large refinery ≈ $116M/year, one Small ≈ $73M/year.
- Rough logistics scale: 6,800 kt × 100 km × $0.10 ≈ $68M/year per heavy leg. CapEx dominates unless annualised.

### 3.2 Known properties of the given data (explain these, do not hide them)

These follow from the organisers' numbers, not from bugs. Put them in the README and the dashboard.

1. **Depots are pulled toward refineries.** With depot yield 1.0, a tonne going from biomass site i to refinery k costs `0.10·d_ik` if the depot sits at the refinery, and `0.12·d_ik` if it sits at the biomass site. The optimiser will co-locate depots with refineries as far as A10 allows. Real depots sit near fields because they dry or densify biomass, which is what A4 < 1 models. The A4 sensitivity row shows how the depot map changes.
2. **Depot size is a tie.** Small and Large depots both cost $15,000 per kt. Apart from the A10 per-site cap, the solver's Small/Large choice for depots is arbitrary and other optimal plans exist. Report total depot capacity per site as the decision, and say the size split is indifferent.
3. **Large refineries have economies of scale** ($704k/kt vs $960k/kt), so the solver prefers few, large refineries.
4. **Leg 3 carries only yield × biomass** (1,360 kt at 0.20 vs 6,800 kt on legs 1–2), so refineries sit near biomass, not near airports.
5. **Refineries come in big steps.** One Small refinery makes 500 kt SAF/yr (output basis). Low demand still pays for a whole refinery, so cost per tonne of SAF rises sharply at low demand. Show it.

### 3.3 Demand as user input (rev 3)

- The dashboard has one number input per airport (PNK, PKN, BPN, TRK), in kt SAF/yr, and a **Solve** button. Do not re-solve on every keystroke.
- Default on load: `demand_kt` from `config.yaml` (170 each), labelled "placeholder".
- **Feasibility gate:** if Σ demand > refinery yield × Σ biomass (1,360 kt at 0.20), show "Demand exceeds what all 6,800 kt of biomass can make" with both numbers, and do not solve.
- Demand of 0 at an airport is allowed (no deliveries there).
- Every result shows the demand it was solved for, so a screenshot is never ambiguous.

---

## 4. Mathematical model (MILP)

### 4.1 Sets

- `I` = biomass sites (80)
- `J` = depot candidate sites
- `K` = refinery candidate sites
- `A` = airports (4)
- `S` = sizes {Small, Large}

### 4.2 Candidate sites

Exact free-floating coordinates make the problem nonlinear. Use a fixed candidate list so the solver stays exact.

- **Depot candidates `J`:** the 80 biomass sites + k-means centroids of biomass sites (k = 20, weighted by kt).
- **Refinery candidates `K`:** the 80 biomass sites + the same centroids + the 4 airport locations.
- Every depot candidate is also a refinery candidate, so depot/refinery co-location (3.2 item 1) is always possible.
- **Offshore filter (A13):** biomass sites flagged offshore in `data/borneo_geo.json` are not candidates. Centroids are tested against the land polygons in the same file and dropped if in the sea. Log every dropped candidate.
- Check every centroid lies inside the Kalimantan bounding box. Log any that look offshore.
- In the pitch, say: "Optimal over N candidate sites." That is the honest claim.

### 4.3 Parameters

- `S_i` = biomass at site i (kt)
- `d_ij`, `d_jk`, `d_ka` = road distance in km (haversine × circuity)
- `c1 = 0.10`, `c2 = 0.12`, `c3 = 0.08` USD per tonne-km
- `cap_depot[s]`, `cap_ref[s]` (kt), `capex_depot[s]`, `capex_ref[s]` (USD)
- `y_dep` = depot mass yield, `y_ref` = refinery yield
- `D_a` = SAF demand at airport a (kt)
- `CRF` = capital recovery factor, `opex_rate`
- `sea_a` = sea surcharge in USD per tonne for airport a (A12; `sea_surcharge_usd_per_t` for airports in `sea_leg_airports`, else 0)

### 4.4 Variables

- `n_dep[j,s]` ∈ {0..max} integer = number of depots of size s at site j
- `n_ref[k,s]` ∈ {0..max} integer = number of refineries of size s at site k
- `x[i,j]` ≥ 0 = biomass kt from site i to depot j
- `w[j,k]` ≥ 0 = pre-processed kt from depot j to refinery k
- `z[k,a]` ≥ 0 = SAF kt from refinery k to airport a

### 4.5 Constraints

1. **Supply:** `Σ_j x[i,j] = S_i` (process_all) or `≤ S_i` (meet_demand).
2. **Depot capacity:** `Σ_i x[i,j] ≤ Σ_s cap_depot[s] · n_dep[j,s]`.
3. **Depot balance:** `Σ_k w[j,k] = y_dep · Σ_i x[i,j]`.
4. **Refinery capacity:**
   - basis `input`: `Σ_j w[j,k] ≤ Σ_s cap_ref[s] · n_ref[k,s]`
   - basis `output`: `y_ref · Σ_j w[j,k] ≤ Σ_s cap_ref[s] · n_ref[k,s]`
5. **Refinery balance:** `Σ_a z[k,a] = y_ref · Σ_j w[j,k]`.
6. **Demand:** `Σ_k z[k,a] ≥ D_a` for every airport a.
7. **Facility limits:** `Σ_s n_dep[j,s] ≤ max_dep`, `Σ_s n_ref[k,s] ≤ max_ref`.

### 4.6 Objective (USD per year)

```
min  (CRF + opex_rate) · [ Σ capex_depot[s]·n_dep[j,s] + Σ capex_ref[s]·n_ref[k,s] ]
   + 1000 · [ c1·Σ d_ij·x[i,j] + c2·Σ d_jk·w[j,k] + c3·Σ d_ka·z[k,a] ]
   + 1000 · Σ_a sea_a · Σ_k z[k,a]
```

The last term is zero by default (A12). Report it as its own line in `cost_breakdown.csv`.

**Units warning:** flows are in kt, rates are per tonne. The factor 1000 converts kt to t. Add a unit test for this.

### 4.7 Model size control

- Keep all arcs on every leg by default (A11 = `null`): x = 80 × 100 = 8,000, w = 100 × 104 = 10,400, z = 104 × 4 = 416.
- Expect about 400 integer and ~19k continuous variables. CBC or HiGHS should solve this in minutes.
- If the full model does not reach the gap within the time limit, set A11 to a number (try 30 before going lower), re-run and report it in the Assumptions panel. Never prune silently.
- Set a time limit (default 180 s; 60 s for dashboard re-solves) and a relative MIP gap target (default 0.5%).

### 4.8 Pre-solve checks

Before building the model, check Σ demand ≤ y_ref · Σ S_i and that every demand is ≥ 0. On failure, return status `Infeasible input` with the reason, and never call the solver.

### 4.9 Solve strategy (rev 3)

- **Depot modules.** When Large = 2 × Small capacity at the same cost per kt (true for the given data), a depot site's capacity is one integer count of 150 kt modules, packed into Large + Small for the report. Exact; removes symmetric Small/Large choices.
- **Valid inequalities** (cut fractional facilities from the LP, never an integer plan): `x[i,j] ≤ S_i · units_j`, `z[k,a] ≤ D_a · Σ_s n_ref[k,s]`, and `Σ cap_ref[s] · N_s ≥ required refinery capacity`.
- **Refinery-mix split** (`solve_by_mix`). List every Small/Large refinery count with enough capacity, cheapest first. For each: if its annualised refinery CapEx plus the cheapest possible depots ≥ the best plan so far, rule it out; else solve with the totals fixed. Proven lower bound = min over all mixes. `solution.json` records each mix's result.

---

## 5. Required outputs

Write to `outputs/`:

| File | Contents |
|---|---|
| `solution.json` | Solver status, objective, optimality gap, solve time, demand solved for, SAF delivered, cost per tonne of SAF, config used |
| `facilities.csv` | type, size, count, lat, lon, throughput kt, utilisation %. For depots, also total capacity kt per site (the real decision; the size split is a tie, see 3.2) |
| `flows.csv` | leg, from, to, kt, distance km, cost USD, truck trips (Small and Large) |
| `cost_breakdown.csv` | CapEx (one-time and annualised), OpEx, logistics per leg, sea surcharge, total |
| `baselines.csv` | Cost of each baseline vs the MILP |
| `sensitivity.csv` | One row per scenario (see Section 7) |

---

## 6. Non-negotiable rules

1. **Exact solver only.** Use PuLP with CBC, or HiGHS (`highspy`). Do not use genetic algorithms, simulated annealing, particle swarm, `scipy.optimize.minimize`, or any LLM to make location, sizing or routing decisions. The judging rubric marks down opaque or heuristic answers.
2. **Always report solver status and gap.** If the status is not Optimal (or Feasible within gap), say so in the UI. Never present an infeasible or unsolved result as a plan.
3. **Independent verification.** `verify.py` must reload `flows.csv` and `facilities.csv`, recompute every constraint and the total cost from scratch, and report pass/fail per constraint with tolerance 1e-6. It must not import the model code.
4. **One shared cost function.** Baselines and the MILP must be scored by the same evaluator so the comparison is fair.
5. **LLM role is explanation only.** An optional `explain.py` may turn `solution.json` into a plain-English summary. It may only quote numbers present in the JSON. A template-based summary is fine if time is short.
6. **All assumptions in `config.yaml`.** No magic numbers in code.

---

## 7. Evaluation (judges weight this at 20%)

### 7.1 Baselines (score with the shared cost function)

- **B1, one central refinery:** a depot at every biomass site, sized to fit. All depot output goes to enough Large refineries at the biomass-weighted centroid. SAF goes to airports by demand.
- **B2, refinery at every airport:** depots at every biomass site. Each depot sends to its nearest airport refinery, sized to fit.

Report % saving of the MILP vs each baseline. Expect B2 to lose by a wide margin (it needs at least 4 refineries) and B1 to be the closer comparison. Lead with B1 in the pitch.

### 7.2 Sensitivity runs

| Parameter | Values |
|---|---|
| Refinery yield (A3) | 0.15, 0.20, 0.25, 0.30 |
| Depot yield (A4) | 1.0, 0.8, 0.6 |
| Circuity (A9) | 1.0, 1.3, 1.6 |
| Capacity basis (A5) | input, output |
| Total demand (A2), equal split | 200, 400, 680, 1,000, 1,360 kt |
| Mode (A1) | meet_demand (decided), process_all (comparison) |

For each run record: total cost, # depots, # depot sites, # refineries by size, # depots co-located with a refinery, logistics share of cost, solve status, gap. Keep total runtime reasonable (lower the time limit for sweeps if needed).

### 7.3 Known failure cases (show at least one in the pitch)

- **Tarakan (TRK) is on an island.** Trucks cannot drive to Juwata airport. By default (A12 surcharge = 0) the model assumes a road leg that does not exist. A real plan needs a barge or ship leg. Flag this in the UI, and if the team supplies a barge rate, show the cost with and without it.
- **Straight-line distance.** Borneo has sparse roads and relies on rivers. Circuity 1.3 is a guess. Show how the plan changes at 1.6.
- **Wrong yield or capacity basis** can flip the refinery count. The sensitivity table makes this visible.
- **Depot placement depends on depot yield** (3.2 item 1). The A4 rows show depots moving from refineries out toward the fields.

---

## 8. Dashboard (Streamlit)

Keep it simple and working. One page is fine.

1. **Map** (folium via `streamlit-folium`, or pydeck): biomass sites sized by kt, depots and refineries with size-coded markers, the 4 airports, and flow lines with width ∝ kt and colour by leg.
2. **Cost breakdown** table and bar chart.
3. **Facility table** with coordinates and utilisation. Note under it that the depot Small/Large split is a cost tie.
4. **Baseline comparison** and **sensitivity table**.
5. **Verification panel:** solver status, gap, and each constraint check from `verify.py`.
6. **Assumptions panel:** every value from `config.yaml`, labelled as assumption, plus the properties in 3.2.
7. **Demand inputs (required, rev 3):** one number box per airport (kt SAF/yr) and a Solve button, with the feasibility gate from 3.3, a spinner and a 60 s time limit. Headline numbers: total annual cost and cost per tonne of SAF.
8. Sidebar controls for yield and circuity that trigger a re-solve (nice-to-have).

---

## 9. Project structure

```
saf/
├── CLAUDE.md            # this file
├── config.yaml          # all assumptions and solver settings
├── data/                # input files (placed by the team)
├── src/
│   ├── load_data.py     # read + validate inputs, print checks
│   ├── candidates.py    # build candidate depot/refinery sites
│   ├── distances.py     # haversine × circuity matrices
│   ├── model.py         # MILP build + solve
│   ├── evaluate.py      # shared cost function
│   ├── baselines.py     # B1, B2
│   ├── verify.py        # independent constraint + cost check
│   ├── sensitivity.py   # scenario sweep
│   ├── explain.py       # optional plain-English summary
│   ├── geo_extract.py   # coastline clip + offshore check -> data/borneo_geo.json
│   ├── plot_map.py      # pre-solve folium map (local)
│   └── build_map_page.py # self-contained shareable map page
├── app.py               # Streamlit dashboard
├── outputs/
└── tests/               # unit test for kt→t conversion, haversine sanity, tiny toy model
```

**Stack:** Python 3.11, pandas, numpy, pulp (CBC bundled) or highspy, scikit-learn (KMeans), pyyaml, streamlit, folium, streamlit-folium, pytest.

---

## 10. Build order with checkpoints

Stop at each checkpoint and confirm it works before moving on.

| Step | Time | Task | Checkpoint |
|---|---|---|---|
| 1 | 0:00–0:30 | `load_data.py`, `config.yaml`, data checks | 80 sites, 6,800 kt, 4 airports printed |
| 2 | 0:30–1:00 | `candidates.py`, `distances.py`, tests | Distance matrices built, haversine test passes |
| 3 | 1:00–2:15 | `model.py` on a 10-site toy, then the full set | Status Optimal, gap reported, outputs written |
| 4 | 2:15–2:45 | `evaluate.py`, `verify.py` | All constraints pass, recomputed cost matches objective |
| 5 | 2:45–3:15 | `baselines.py` | MILP beats both baselines, % shown |
| 6 | 3:15–4:45 | `app.py` dashboard | Map, tables, verification and assumptions visible |
| 7 | 4:45–5:15 | `sensitivity.py` | Sensitivity table in dashboard |
| 8 | 5:15–5:45 | Polish, failure-case callout, README | Ready to submit |

**MVP if time runs short:** steps 1–4 plus a map. Sensitivity and sliders are nice-to-have.

---

## 11. Judging rubric (what the build must prove)

| Criterion | Weight | How this build scores |
|---|---|---|
| Problem realism | 20% | User = SAF supply-chain planner choosing where to build. Status quo = spreadsheet guesses on $1B+ capital decisions |
| Technical soundness | 25% | Exact MILP with explicit constraints. LLM limited to explanation |
| Honest evaluation | 20% | Two baselines, sensitivity sweep, Tarakan island failure case, data properties in 3.2 explained |
| Trust and traceability | 20% | Solver status + gap, independent verifier, every assumption visible |
| Impact | 10% | % cost saving vs baselines, clearly labelled as modelled, not measured |
| Time discipline | 5% | Submit early, 3-minute pitch |

---

## 12. Definition of done

- [ ] Data loads and passes all checks.
- [ ] MILP solves to Optimal (or within gap) in under 3 minutes on the full data, with all arcs (A11 = `null`), or the pruning used is shown in the Assumptions panel.
- [ ] `verify.py` passes every constraint and cost matches within $1.
- [ ] MILP cost < both baselines, with % shown.
- [ ] Dashboard shows map, costs, facilities, verification, assumptions.
- [ ] Sensitivity table covers refinery yield, depot yield, circuity, capacity basis.
- [ ] Tarakan failure case is visible in the UI.
- [ ] Depot co-location and the depot size tie (3.2) are explained in the UI and README.
- [ ] Changing airport demand in the dashboard re-solves and redraws the plan in under a minute; over-limit demand is rejected with a message.
- [ ] No depot or refinery is placed at an offshore site.
- [ ] Cost per tonne of SAF is shown next to total cost.
- [ ] README explains how to run: `pip install -r requirements.txt`, `python -m src.model`, `streamlit run app.py`.
