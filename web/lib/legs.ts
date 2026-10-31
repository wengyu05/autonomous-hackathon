import type { Leg } from "./types";

/**
 * One colour per transport leg, shared by the map, tables and charts. Same colours as the
 * Streamlit app (src/plan_map.py LEGS): the first three slots of the dataviz reference palette.
 */
export const LEG_STYLE: Record<Leg, { color: string; label: string }> = {
  farm_depot: { color: "#2a78d6", label: "Biomass → depot" },
  depot_refinery: { color: "#eb6834", label: "Depot → refinery" },
  refinery_airport: { color: "#1baf7a", label: "Refinery → airport" },
};
