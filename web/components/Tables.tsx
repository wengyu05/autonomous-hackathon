"use client";

import { useMemo, useState } from "react";
import { ArrowDownUp } from "lucide-react";
import type { Facility, Flow, Leg, Results } from "@/lib/types";
import { LEG_STYLE } from "@/lib/legs";
import { coords, num, usd } from "@/lib/format";

const th = "sticky top-0 z-10 bg-white px-3 py-2 text-left text-xs font-medium text-slate-500";
const td = "px-3 py-2 text-sm text-slate-700";

function matches(query: string, ...fields: string[]) {
  const q = query.trim().toLowerCase();
  return !q || fields.some((f) => f.toLowerCase().includes(q));
}

interface TableProps {
  data: Results;
  query: string;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

/** Depots and refineries with capacity and utilisation. Clicking a row highlights it on the map. */
export function FacilityTable({ data, query, selectedId, onSelect }: TableProps) {
  const rows = useMemo(
    () =>
      [
        ...data.refineries.map((f) => ({ ...f, type: "Refinery" as const })),
        ...data.depots.map((f) => ({ ...f, type: "Depot" as const })),
      ].filter((f) => matches(query, f.id, f.site ?? "")),
    [data, query],
  );

  return (
    <div className="max-h-[420px] overflow-auto border border-slate-200">
      <table className="w-full min-w-[720px]">
        <caption className="sr-only">Facilities: {rows.length} rows</caption>
        <thead>
          <tr className="border-b border-slate-200">
            <th scope="col" className={th}>ID</th>
            <th scope="col" className={th}>Type</th>
            <th scope="col" className={th}>Size</th>
            <th scope="col" className={th}>Lat, Long</th>
            <th scope="col" className={`${th} text-right`}>Capacity (kt/yr)</th>
            <th scope="col" className={`${th} text-right`}>Throughput (kt/yr)</th>
            <th scope="col" className={th}>Utilisation</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((f: Facility & { type: "Depot" | "Refinery" }) => {
            const u = f.utilisationPct ?? (f.capacityKt ? (f.throughputKt / f.capacityKt) * 100 : 0);
            return (
              <tr
                key={f.id}
                tabIndex={0}
                onClick={() => onSelect(selectedId === f.id ? null : f.id)}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(selectedId === f.id ? null : f.id))}
                aria-selected={selectedId === f.id}
                className={`cursor-pointer hover:bg-slate-50 ${selectedId === f.id ? "bg-slate-100" : ""}`}
              >
                <td className={`${td} font-medium text-slate-900`}>{f.id}</td>
                <td className={td}>
                  {f.type}
                </td>
                <td className={td}>{f.units ?? f.size}</td>
                <td className={`${td} tabular-nums`}>{coords(f.lat, f.lng)}</td>
                <td className={`${td} text-right tabular-nums`}>
                  {num(f.capacityKt)}
                  <span className="ml-1 text-xs text-slate-500">{f.type === "Refinery" ? "SAF" : "in"}</span>
                </td>
                <td className={`${td} text-right tabular-nums`}>{num(f.throughputKt, 1)}</td>
                <td className={td}>
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-20 overflow-hidden bg-slate-100" aria-hidden>
                      <div className="h-full bg-brand" style={{ width: `${Math.min(100, u)}%` }} />
                    </div>
                    <span className="tabular-nums text-xs">{num(u)}%</span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.length === 0 && <p className="p-4 text-sm text-slate-500">No facilities match “{query}”.</p>}
    </div>
  );
}

type SortKey = "tonnes" | "distanceKm" | "cost";

/** All flows with leg filter and sortable numeric columns. */
export function FlowTable({ data, query, selectedId }: TableProps) {
  const [leg, setLeg] = useState<Leg | "all">("all");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "tonnes", desc: true });

  const rows = useMemo(
    () =>
      data.flows
        .filter((f) => (leg === "all" || f.leg === leg) && matches(query, f.from, f.to))
        .filter((f) => !selectedId || f.from === selectedId || f.to === selectedId)
        .sort((a, b) => (sort.desc ? b[sort.key] - a[sort.key] : a[sort.key] - b[sort.key])),
    [data, leg, query, sort, selectedId],
  );

  const sortHeader = (key: SortKey, label: string) => (
    <th scope="col" className={`${th} text-right`} aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : "none"}>
      <button
        type="button"
        onClick={() => setSort((s) => ({ key, desc: s.key === key ? !s.desc : true }))}
        className="inline-flex items-center gap-1 uppercase hover:text-slate-800"
      >
        {label}
        <ArrowDownUp className="h-3 w-3" aria-hidden />
      </button>
    </th>
  );

  const totalCost = rows.reduce((t, f: Flow) => t + f.cost, 0);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div role="group" aria-label="Filter by leg" className="flex flex-wrap gap-1">
          {(["all", ...Object.keys(LEG_STYLE)] as (Leg | "all")[]).map((l) => (
            <button
              key={l}
              type="button"
              aria-pressed={leg === l}
              onClick={() => setLeg(l)}
              className={`flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs ${
                leg === l ? "border-slate-400 bg-slate-100 text-slate-900" : "border-slate-200 text-slate-600 hover:border-slate-300"
              }`}
            >
              {l !== "all" && <span className="h-0.5 w-3" style={{ background: LEG_STYLE[l].color }} aria-hidden />}
              {l === "all" ? "All legs" : LEG_STYLE[l].label}
            </button>
          ))}
        </div>
        <p className="text-xs text-slate-500">
          {rows.length} flows · {usd(totalCost)}/yr
          {selectedId && <> · connected to {selectedId}</>}
        </p>
      </div>

      <div className="max-h-[420px] overflow-auto border border-slate-200">
        <table className="w-full min-w-[640px]">
          <caption className="sr-only">Material flows: {rows.length} rows</caption>
          <thead>
            <tr className="border-b border-slate-200">
              <th scope="col" className={th}>Leg</th>
              <th scope="col" className={th}>From</th>
              <th scope="col" className={th}>To</th>
              {sortHeader("tonnes", "Tonnes/yr")}
              {sortHeader("distanceKm", "Distance (km)")}
              {sortHeader("cost", "Cost (USD/yr)")}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((f, i) => (
              <tr key={`${f.from}-${f.to}-${i}`} className="hover:bg-slate-50">
                <td className={td}>
                  <span className="inline-flex items-center gap-1.5 text-xs">
                    <span className="h-0.5 w-3" style={{ background: LEG_STYLE[f.leg].color }} aria-hidden />
                    {LEG_STYLE[f.leg].label}
                  </span>
                </td>
                <td className={`${td} font-medium text-slate-900`}>{f.from}</td>
                <td className={td}>{f.to}</td>
                <td className={`${td} text-right tabular-nums`}>{num(f.tonnes)}</td>
                <td className={`${td} text-right tabular-nums`}>{num(f.distanceKm)}</td>
                <td className={`${td} text-right tabular-nums`}>{usd(f.cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="p-4 text-sm text-slate-500">No flows match the current filters.</p>}
      </div>
    </div>
  );
}
