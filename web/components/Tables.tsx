"use client";

import type { ReactNode } from "react";
import type { Flow, Results } from "@/lib/types";
import { LEG_STYLE } from "@/lib/legs";
import { coords, num, usd } from "@/lib/format";

export interface Column<T> {
  label: string;
  /** Right-align numeric columns. */
  numeric?: boolean;
  cell: (row: T) => ReactNode;
}

/** A Streamlit-style dataframe: bordered, rounded, grey header, scrolls inside its own box. */
export function DataTable<T>({ columns, rows, maxHeight, onRowClick, selected, caption }: {
  columns: Column<T>[];
  rows: T[];
  maxHeight?: number;
  onRowClick?: (row: T) => void;
  selected?: (row: T) => boolean;
  caption: string;
}) {
  return (
    <div className="overflow-auto rounded-lg border border-line bg-white" style={maxHeight ? { maxHeight } : undefined}>
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.label}
                scope="col"
                className={`sticky top-0 border-b border-r border-line bg-[#fafbfa] px-2.5 py-2 font-normal text-ink-2 last:border-r-0 ${c.numeric ? "text-right" : "text-left"}`}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={`${onRowClick ? "cursor-pointer hover:bg-page" : ""} ${selected?.(r) ? "bg-ok/60" : ""}`}
            >
              {columns.map((c) => (
                <td
                  key={c.label}
                  className={`border-b border-r border-line px-2.5 py-2 text-ink last:border-r-0 ${c.numeric ? "text-right tabular-nums" : ""}`}
                >
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

export const Note = ({ children }: { children: ReactNode }) => <p className="mt-3 text-sm text-ink-2">{children}</p>;

const site = (id: string) => id.replace(/^[DR]-/, "");

interface SelectProps {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

/** Facilities tab: refineries then depots, with size, coordinates, throughput and use. */
export function FacilityTable({ data, selectedId, onSelect }: { data: Results } & SelectProps) {
  const rows = [
    ...data.refineries.map((f) => ({ ...f, type: "Refinery" })),
    ...data.depots.map((f) => ({ ...f, type: "Depot" })),
  ];
  return (
    <>
      <DataTable
        caption={`Facilities: ${rows.length} rows`}
        rows={rows}
        maxHeight={460}
        onRowClick={(r) => onSelect(selectedId === r.id ? null : r.id)}
        selected={(r) => r.id === selectedId}
        columns={[
          { label: "Type", cell: (r) => r.type },
          { label: "Site", cell: (r) => r.site ?? site(r.id) },
          { label: "Size", cell: (r) => r.units ?? r.size },
          { label: "Lat, Lon", cell: (r) => coords(r.lat, r.lng) },
          { label: "In (kt/yr)", numeric: true, cell: (r) => num(r.throughputKt, 1) },
          { label: "Out (kt/yr)", numeric: true, cell: (r) => num(r.outputKt ?? r.throughputKt, 1) },
          {
            label: "Used",
            cell: (r) => (
              <span className="flex items-center gap-2">
                <span className="h-1.5 flex-1 rounded bg-side" aria-hidden>
                  <span className="block h-full rounded bg-brand" style={{ width: `${Math.min(100, r.utilisationPct ?? 0)}%` }} />
                </span>
                <span className="w-9 text-right tabular-nums">{num(r.utilisationPct ?? 0)}%</span>
              </span>
            ),
          },
        ]}
      />
      <Note>
        Small and Large depots cost the same per kt, so the depot Small/Large split is a cost tie; total capacity per
        site is the real decision.
      </Note>
    </>
  );
}

/** Routes tab: every truck route with tonnes, road km, cost and trips. */
export function FlowTable({ data, selectedId, onSelect }: { data: Results } & SelectProps) {
  return (
    <>
      <DataTable<Flow>
        caption={`Routes: ${data.flows.length} rows`}
        rows={data.flows}
        maxHeight={460}
        onRowClick={(f) => onSelect(selectedId === f.from ? null : f.from)}
        selected={(f) => selectedId != null && (f.from === selectedId || f.to === selectedId)}
        columns={[
          { label: "Leg", cell: (f) => LEG_STYLE[f.leg].label },
          { label: "From", cell: (f) => site(f.from) },
          { label: "To", cell: (f) => site(f.to) },
          { label: "kt/yr", numeric: true, cell: (f) => num(f.tonnes / 1000, 1) },
          { label: "Road km", numeric: true, cell: (f) => num(f.distanceKm) },
          { label: "USD/yr", numeric: true, cell: (f) => usd(f.cost) },
          { label: "Large-truck trips/yr", numeric: true, cell: (f) => num(f.trucksLarge ?? 0) },
        ]}
      />
      <Note>
        Road km = OpenStreetMap route between the nearest road points + the straight stretch from each site to its road
        × 1.3. A depot at the same site as its refinery has a 0 km leg.
      </Note>
    </>
  );
}

/** Baselines tab: the three plans side by side. */
export function BaselineTable({ data }: { data: Results }) {
  const plans = data.meta?.comparisons ?? [];
  const opt = plans.find((p) => p.id === "optimised");
  const name = (id: string, label: string) =>
    id === "optimised" ? "Optimised (MILP)" : `${id.toUpperCase()} · ${label.replace(/^Baseline \w+: /, "")}`;
  return (
    <>
      <DataTable
        caption="Plans compared"
        rows={plans}
        columns={[
          { label: "Plan", cell: (p) => name(p.id, p.label) },
          { label: "Cost per year", numeric: true, cell: (p) => usd(p.totalCost) },
          {
            label: "MILP saves",
            numeric: true,
            cell: (p) => (p.id === "optimised" || !opt ? "" : `${num((100 * (p.totalCost - opt.totalCost)) / p.totalCost, 1)}%`),
          },
          { label: "$/t SAF", numeric: true, cell: (p) => usd(p.costPerTonne) },
          { label: "Refineries", cell: (p) => p.refinerySizes ?? String(p.refineries) },
          { label: "Depot sites", numeric: true, cell: (p) => p.depotSites },
        ]}
      />
      <Note>
        All three plans use the same road distances and cost function and pass the same independent checks. Savings
        are modelled, not measured, and depend on the demand entered.
      </Note>
    </>
  );
}

/** Checks tab: solver result, every independent check, and the refinery mixes the search considered. */
export function ChecksTab({ data }: { data: Results }) {
  const m = data.meta;
  const status = m?.optimisedStatus ?? m?.status;
  const gap = m?.optimisedGap ?? m?.gap;
  const secs = m?.optimisedSolveTimeS ?? m?.solveTimeS;
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink">
        <b>Solver:</b> {m?.solver ?? "n/a"} · <b>{status}</b> · gap {gap != null ? `${(gap * 100).toFixed(2)}%` : "n/a"}
        {m?.mipGapTarget != null && ` (target ${(m.mipGapTarget * 100).toFixed(1)}%)`}
        {secs != null && ` · ${Math.round(secs)} s`}
      </p>
      <DataTable
        caption="Independent checks"
        rows={m?.checks ?? []}
        columns={[
          { label: "", cell: (c) => (c.pass ? "✅" : "❌") },
          { label: "Check", cell: (c) => c.check },
          { label: "Detail", cell: (c) => <span className="text-ink-2">{c.detail}</span> },
        ]}
      />
      {Object.entries(m?.baselineChecks ?? {}).map(([n, b]) => (
        <p key={n} className="text-sm text-ink-2">
          Baseline {n}: {b.passed}/{b.total} checks pass
        </p>
      ))}
      {!!m?.mixSearch?.length && (
        <>
          <p className="pt-2 text-sm font-semibold text-ink">Refinery mixes considered</p>
          <DataTable
            caption="Refinery mixes considered"
            rows={m.mixSearch}
            columns={[
              { label: "Refinery mix", cell: (r) => r.mix },
              { label: "Result", cell: (r) => r.result },
              { label: "Best plan", numeric: true, cell: (r) => (r.objective_usd != null ? usd(r.objective_usd) : "") },
              { label: "Proven lower bound", numeric: true, cell: (r) => (r.lower_bound_usd != null ? usd(r.lower_bound_usd) : "") },
              { label: "Seconds", numeric: true, cell: (r) => (r.seconds != null ? num(r.seconds) : "") },
            ]}
          />
        </>
      )}
    </div>
  );
}

/** Assumptions tab: every config.yaml value the plan rests on. */
export function AssumptionsTable({ data }: { data: Results }) {
  return (
    <>
      <DataTable
        caption="Assumptions"
        rows={data.meta?.assumptions ?? []}
        columns={[
          { label: "ID", cell: (a) => a.ID },
          { label: "Assumption", cell: (a) => a.Assumption },
          { label: "Value", cell: (a) => a.Value },
          { label: "Note", cell: (a) => <span className="text-ink-2">{a.Note}</span> },
        ]}
      />
      <Note>
        Every value here is an assumption from config.yaml, not given by the organisers. Facility costs, capacities and
        transport rates are the brief&apos;s figures.
      </Note>
    </>
  );
}
