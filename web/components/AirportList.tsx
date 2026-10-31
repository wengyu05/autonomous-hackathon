import type { Results } from "@/lib/types";
import { num } from "@/lib/format";
import { DataTable, Note } from "./Tables";

/** Airports tab: demand against delivery, the refineries supplying each airport and the average road km. */
export default function AirportList({ data }: { data: Results }) {
  const rows = data.airports.map((a) => {
    const legs = data.flows.filter((f) => f.leg === "refinery_airport" && f.to === a.id);
    const kt = legs.reduce((t, f) => t + f.tonnes / 1000, 0);
    return {
      airport: `${a.id} · ${a.city ?? a.name}`,
      demand: a.demandKt,
      delivered: a.deliveredKt,
      from: legs.map((f) => f.from.replace(/^R-/, "")).join(", "),
      avgKm: kt ? legs.reduce((t, f) => t + (f.tonnes / 1000) * f.distanceKm, 0) / kt : 0,
    };
  });
  const biomass = data.flows.filter((f) => f.leg === "farm_depot");
  const sites = new Set(biomass.map((f) => f.from)).size;
  const saf = data.flows.filter((f) => f.leg === "refinery_airport").reduce((t, f) => t + f.tonnes / 1000, 0);

  return (
    <>
      <DataTable
        caption="SAF demand and delivery by airport"
        rows={rows}
        columns={[
          { label: "Airport", cell: (r) => r.airport },
          { label: "Demand (kt)", numeric: true, cell: (r) => num(r.demand) },
          { label: "Delivered (kt)", numeric: true, cell: (r) => num(r.delivered, 1) },
          { label: "From refineries", cell: (r) => r.from },
          { label: "Avg road km", numeric: true, cell: (r) => num(r.avgKm) },
        ]}
      />
      <Note>
        Biomass used: <b className="text-ink">{num(biomass.reduce((t, f) => t + f.tonnes / 1000, 0))} kt</b> from{" "}
        <b className="text-ink">{sites} of {data.farms.length} sites</b>, making {num(saf)} kt SAF.
      </Note>
    </>
  );
}
