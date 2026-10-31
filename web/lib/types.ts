// Data contract for /public/data/*.json. Generated from the optimiser outputs by
// scripts/export_results.py; any file with this shape can be dropped in.

export type Size = "Small" | "Large";
export type Leg = "farm_depot" | "depot_refinery" | "refinery_airport";

/** Distance rule a plan was solved with: the organisers' great-circle × 1.3, or OpenStreetMap road km. */
export type Distances = "official" | "roads";

export interface Summary {
  /** Total annual cost in USD: annualised CapEx + fixed OpEx + variable OpEx + logistics. */
  totalCost: number;
  /** Annualised CapEx, USD per year. */
  capex: number;
  /** Fixed OpEx (a share of CapEx), USD per year. */
  opex: number;
  /** Variable OpEx (per tonne of biomass into depots and refineries), USD per year. Optional for older files. */
  variableOpex?: number;
  /** Trucking cost across all three legs, USD per year. */
  logistics: number;
  /** SAF delivered to airports, kt per year. */
  safDelivered: number;
  /** totalCost / tonnes of SAF delivered, USD per tonne. */
  costPerTonne: number;
  /** Optional: one-time construction cost, USD. */
  capexOneTime?: number;
  /** Optional: the optimised plan's full cost breakdown (outputs/cost_breakdown.csv rows). */
  costItems?: CostItem[];
}

export interface CostItem {
  item: string;
  usd: number;
  /** "one-time" | "per year" | "USD/t" */
  basis: string;
}

export interface Farm {
  id: string;
  name?: string;
  lat: number;
  lng: number;
  supplyKt: number;
  /** In the sea in the organisers' data: supply only, no facility (assumption A13). */
  offshore?: boolean;
  coastKm?: number | null;
}

export interface Facility {
  id: string;
  site?: string;
  lat: number;
  lng: number;
  size: Size;
  /** Optional exact unit mix, e.g. "1 Large + 1 Small". */
  units?: string;
  capacityKt: number;
  /** Material entering the facility, kt per year. */
  throughputKt: number;
  /** Optional: material leaving (SAF for refineries), kt per year. */
  outputKt?: number;
  utilisationPct?: number;
}

export interface Airport {
  id: string;
  name: string;
  lat: number;
  lng: number;
  demandKt: number;
  deliveredKt: number;
  city?: string;
  /** On an island: its SAF arrives by barge, priced per t·km like the truck leg. */
  island?: boolean;
}

export interface Flow {
  from: string;
  to: string;
  leg: Leg;
  tonnes: number;
  distanceKm: number;
  cost: number;
  trucksLarge?: number;
  /** Optional road geometry as [lat, lng] pairs (real-road runs only); drawn straight when absent. */
  path?: [number, number][];
}

export interface PlanComparison {
  id: string;
  label: string;
  totalCost: number;
  costPerTonne: number;
  safDelivered: number;
  depotSites: number;
  refineries: number;
  /** e.g. "1 Small, 1 Small" */
  refinerySizes?: string;
  logistics?: number;
  capexOneTime?: number;
}

export interface Check {
  check: string;
  pass: boolean;
  detail: string;
}

export interface MixRun {
  mix: string;
  result: string;
  objective_usd?: number | null;
  lower_bound_usd?: number | null;
  seconds?: number | null;
}

export interface AssumptionRow {
  ID: string;
  Assumption: string;
  Value: string;
  Note: string;
}

export interface Meta {
  scenario: string;
  label: string;
  status: string;
  gap: number | null;
  solveTimeS: number | null;
  solver?: string;
  verified?: boolean;
  checksPassed?: number;
  checksTotal?: number;
  demandKt?: Record<string, number>;
  comparisons?: PlanComparison[];
  // Shared by every plan, for the Checks and Assumptions tabs and the sidebar.
  checks?: Check[];
  baselineChecks?: Record<string, { passed: number; total: number }>;
  mixSearch?: MixRun[];
  assumptions?: AssumptionRow[];
  mipGapTarget?: number;
  maxTotalDemandKt?: number;
  /** The optimised solve's result; the status banner shows it on every plan, as the Streamlit app does. */
  optimisedStatus?: string;
  optimisedGap?: number | null;
  optimisedSolveTimeS?: number | null;
}

export interface Results {
  meta?: Meta;
  summary: Summary;
  farms: Farm[];
  depots: Facility[];
  refineries: Facility[];
  airports: Airport[];
  flows: Flow[];
}

export interface ScenarioOption {
  id: string;
  label: string;
  file: string;
}
