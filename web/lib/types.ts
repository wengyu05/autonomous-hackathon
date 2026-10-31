// Data contract for /public/data/*.json. Generated from the optimiser outputs by
// scripts/export_results.py; any file with this shape can be dropped in.

export type Size = "Small" | "Large";
export type Leg = "farm_depot" | "depot_refinery" | "refinery_airport";

export interface Summary {
  /** Total annual cost in USD: annualised CapEx + OpEx + logistics. */
  totalCost: number;
  /** Annualised CapEx, USD per year. */
  capex: number;
  /** OpEx, USD per year. */
  opex: number;
  /** Trucking cost across all three legs, USD per year. */
  logistics: number;
  /** SAF delivered to airports, kt per year. */
  safDelivered: number;
  /** totalCost / tonnes of SAF delivered, USD per tonne. */
  costPerTonne: number;
  /** Optional: one-time construction cost, USD. */
  capexOneTime?: number;
}

export interface Farm {
  id: string;
  name?: string;
  lat: number;
  lng: number;
  supplyKt: number;
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
}

export interface Flow {
  from: string;
  to: string;
  leg: Leg;
  tonnes: number;
  distanceKm: number;
  cost: number;
  trucksLarge?: number;
  /** Optional road geometry as [lat, lng] pairs; drawn straight when absent. */
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
