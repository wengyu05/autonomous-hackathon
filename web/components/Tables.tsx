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

/** Plain table in the same style as the facility and flow tables, for the remaining tabs. */
function SimpleTable<T>({ caption, rows, columns }: {
  caption: string;
  rows: T[];
  columns: { label: string; numeric?: boolean; cell: (r: T) => React.ReactNode }[];
}) {
  return (
    <div className="max-h-[420px] overflow-auto border border-slate-200">
      <table className="w-full">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-slate-200">
            {columns.map((c) => (
              <th key={c.label} scope="col" className={`${th} ${c.numeric ? "text-right" : ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-slate-50">
              {columns.map((c) => (
                <td key={c.label} className={`${td} ${c.numeric ? "text-right tabular-nums" : ""}`}>
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const note = "mt-3 text-xs text-slate-500";

/** Costs tab, under the donut: every line of outputs/cost_breakdown.csv (optimised plan only). */
export function CostItemsTable({ data }: { data: Results }) {
  const items = data.summary.costItems;
  if (!items || (data.meta?.scenario ?? "optimised") !== "optimised") {
    return <p className={note}>The detailed cost breakdown is for the optimised plan. Baseline totals are in the Baselines tab.</p>;
  }
  return (
    <SimpleTable
      caption="Cost breakdown"
      rows={items}
      columns={[
        { label: "Item", cell: (r) => r.item },
        { label: "USD", numeric: true, cell: (r) => (r.basis === "USD/t" ? `$${r.usd.toFixed(2)}` : usd(r.usd)) },
        { label: "Basis", cell: (r) => r.basis },
      ]}
    />
  );
}

/** Baselines tab: the three plans side by side, with the MILP's saving. */
export function BaselineTable({ data }: { data: Results }) {
  const plans = data.meta?.comparisons ?? [];
  const opt = plans.find((p) => p.id === "optimised");
  return (
    <>
      <SimpleTable
        caption="Plans compared"
        rows={plans}
        columns={[
          { label: "Plan", cell: (p) => <span className="font-medium text-slate-900">{p.label}</span> },
          { label: "Cost (USD/yr)", numeric: true, cell: (p) => usd(p.totalCost) },
          {
            label: "MILP saves",
            numeric: true,
            cell: (p) => (p.id === "optimised" || !opt ? "" : `${num((100 * (p.totalCost - opt.totalCost)) / p.totalCost, 1)}%`),
          },
          { label: "USD/t SAF", numeric: true, cell: (p) => usd(p.costPerTonne) },
          { label: "Refineries", cell: (p) => p.refinerySizes ?? p.refineries },
          { label: "Depot sites", numeric: true, cell: (p) => p.depotSites },
        ]}
      />
      <p className={note}>
        All three plans use the same road distances and cost function and pass the same independent checks. Savings are
        modelled, not measured, and depend on the demand entered.
      </p>
    </>
  );
}

/** Checks tab: solver result, every independent check, and the refinery mixes the search considered. */
export function ChecksTab({ data }: { data: Results }) {
  const m = data.meta;
  const gap = m?.optimisedGap ?? m?.gap;
  const secs = m?.optimisedSolveTimeS ?? m?.solveTimeS;
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-700">
        Solver: <b className="text-slate-900">{m?.solver ?? "n/a"}</b> · <b className="text-slate-900">{m?.optimisedStatus ?? m?.status}</b>
        {gap != null && ` · gap ${(gap * 100).toFixed(2)}%`}
        {m?.mipGapTarget != null && ` (target ${(m.mipGapTarget * 100).toFixed(1)}%)`}
        {secs != null && ` · ${Math.round(secs)} s`}
      </p>
      <SimpleTable
        caption="Independent checks"
        rows={m?.checks ?? []}
        columns={[
          { label: "", cell: (c) => <span className={c.pass ? "text-emerald-700" : "text-rose-700"}>{c.pass ? "✓" : "✗"}</span> },
          { label: "Check", cell: (c) => c.check },
          { label: "Detail", cell: (c) => <span className="text-xs text-slate-500">{c.detail}</span> },
        ]}
      />
      <p className="text-xs text-slate-500">
        {Object.entries(m?.baselineChecks ?? {})
          .map(([n, b]) => `Baseline ${n}: ${b.passed}/${b.total} checks pass`)
          .join(" · ")}
      </p>
      {!!m?.mixSearch?.length && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Refinery mixes considered</p>
          <SimpleTable
            caption="Refinery mixes considered"
            rows={m.mixSearch}
            columns={[
              { label: "Refinery mix", cell: (r) => r.mix },
              { label: "Result", cell: (r) => r.result },
              { label: "Best plan", numeric: true, cell: (r) => (r.objective_usd != null ? usd(r.objective_usd) : "") },
              { label: "Proven lower bound", numeric: true, cell: (r) => (r.lower_bound_usd != null ? usd(r.lower_bound_usd) : "") },
            ]}
          />
        </div>
      )}
    </div>
  );
}

/** Assumptions tab: every config.yaml value the plan rests on. */
export function AssumptionsTable({ data }: { data: Results }) {
  return (
    <>
      <SimpleTable
        caption="Assumptions"
        rows={data.meta?.assumptions ?? []}
        columns={[
          { label: "ID", cell: (a) => <span className="font-medium text-slate-900">{a.ID}</span> },
          { label: "Assumption", cell: (a) => a.Assumption },
          { label: "Value", cell: (a) => a.Value },
          { label: "Note", cell: (a) => <span className="text-xs text-slate-500">{a.Note}</span> },
        ]}
      />
      <p className={note}>
        Every value here is an assumption from config.yaml, not given by the organisers. Facility costs, capacities and
        transport rates are the brief&apos;s figures.
      </p>
    </>
  );
}
