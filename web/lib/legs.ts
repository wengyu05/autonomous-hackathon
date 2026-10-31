import type { Leg } from "./types";

/** One colour per transport leg, shared by the map, tables and charts. */
export const LEG_STYLE: Record<Leg, { color: string; label: string }> = {
  farm_depot: { color: "#a3a33a", label: "Biomass → depot" },
  depot_refinery: { color: "#15803d", label: "Depot → refinery" },
  refinery_airport: { color: "#1e3a5f", label: "Refinery → airport" },
};
