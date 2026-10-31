import type { Airport, Flow } from "@/lib/types";
import { num } from "@/lib/format";

interface AirportListProps {
  airports: Airport[];
  safDelivered: number;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** Optional: when given, each airport also lists its supplying refineries and average road km. */
  flows?: Flow[];
}

/** Supplying refineries and kt-weighted average road km for one airport. */
function supply(flows: Flow[], id: string) {
  const legs = flows.filter((f) => f.leg === "refinery_airport" && f.to === id);
  const t = legs.reduce((s, f) => s + f.tonnes, 0);
  return {
    from: legs.map((f) => f.from.replace(/^R-/, "")).join(", "),
    km: t ? legs.reduce((s, f) => s + f.tonnes * f.distanceKm, 0) / t : 0,
  };
}

/** SAF delivered per airport against demand. Clicking an airport highlights its flows on the map. */
export default function AirportList({ airports, safDelivered, selectedId, onSelect, flows }: AirportListProps) {
  return (
    <div>
      <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">SAF delivered</h3>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">
        {num(safDelivered)}
        <span className="ml-1 text-sm font-normal text-slate-500">kt/yr</span>
      </p>

      <ul className="mt-4 divide-y divide-slate-100 border-t border-slate-100" aria-label="SAF delivered by airport">
        {airports.map((a) => {
          const pct = a.demandKt > 0 ? Math.min(100, (a.deliveredKt / a.demandKt) * 100) : 100;
          return (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => onSelect(selectedId === a.id ? null : a.id)}
                aria-pressed={selectedId === a.id}
                className={`w-full px-1 py-3 text-left hover:bg-slate-50 ${selectedId === a.id ? "bg-slate-50" : ""}`}
              >
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="text-slate-800">
                    {a.name} <span className="text-xs text-slate-500">{a.id}</span>
                  </span>
                  <span className={`shrink-0 tabular-nums text-xs ${pct >= 99.99 ? "text-slate-600" : "text-rose-700"}`}>
                    {num(pct)}%
                  </span>
                </div>
                <div
                  className="mt-1.5 h-1.5 bg-slate-100"
                  role="progressbar"
                  aria-label={`${a.name} demand met`}
                  aria-valuenow={Math.round(pct)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div className="h-full bg-brand" style={{ width: `${pct}%` }} />
                </div>
                <p className="mt-1 text-xs tabular-nums text-slate-500">
                  {num(a.deliveredKt, 1)} of {num(a.demandKt)} kt/yr
                  {flows && supply(flows, a.id).from && (
                    <>
                      {" "}· from {supply(flows, a.id).from} · avg {num(supply(flows, a.id).km)} road km
                    </>
                  )}
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
