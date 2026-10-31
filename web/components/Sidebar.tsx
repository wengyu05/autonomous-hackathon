"use client";

import { useEffect, useState } from "react";
import { Minus, Plus } from "lucide-react";
import type { Airport } from "@/lib/types";
import { num } from "@/lib/format";
import { START_COMMAND } from "@/lib/solver";

const TIME_LIMITS = [60, 120, 300];
const STEP_KT = 10;

// Same plans and labels as the Streamlit app's "Plan on the map" radio.
export const PLAN_OPTIONS = [
  { id: "optimised", label: "Optimised (MILP)" },
  { id: "b1", label: "B1 · one central refinery" },
  { id: "b2", label: "B2 · refinery at every airport" },
];

interface SidebarProps {
  airports: Airport[];
  /** Demand the current plan was solved for; the boxes start from it. */
  demandKt: Record<string, number>;
  maxTotalDemandKt: number;
  scenarioId: string;
  onScenarioChange: (id: string) => void;
  onSolve: (demandKt: Record<string, number>, timeLimitS: number) => void;
  solving: boolean;
  solveError: string | null;
  solverOnline: boolean | null;
}

const label = "text-xs font-medium uppercase tracking-wide text-slate-500";

/**
 * Left panel, arranged as in the Streamlit app: airport demand inputs and Solve, then the plan shown on
 * the map. On mobile it sits above the content.
 */
export default function Sidebar(p: SidebarProps) {
  const [demand, setDemand] = useState<Record<string, number>>(p.demandKt);
  const [limitIdx, setLimitIdx] = useState(0);

  // A new solve (or the first load) resets the boxes to the demand the plan was solved for.
  useEffect(() => setDemand(p.demandKt), [p.demandKt]);

  const set = (id: string, v: number) => setDemand((d) => ({ ...d, [id]: Math.max(0, Math.min(p.maxTotalDemandKt, v)) }));
  const total = Object.values(demand ?? {}).reduce((t, v) => t + (Number.isFinite(v) ? v : 0), 0);
  const overLimit = total > p.maxTotalDemandKt + 1e-9;

  return (
    <aside className="w-full shrink-0 border-b border-slate-200 bg-white px-5 py-6 md:sticky md:top-0 md:h-screen md:w-[290px] md:overflow-y-auto md:border-b-0 md:border-r">
      <span className="text-sm font-bold tracking-wide text-brand">SAF</span>

      <form
        className="mt-6 space-y-5"
        aria-labelledby="demand-title"
        onSubmit={(e) => {
          e.preventDefault();
          if (!overLimit && !p.solving) p.onSolve(demand, TIME_LIMITS[limitIdx]);
        }}
      >
        <div>
          <h2 id="demand-title" className={label}>
            Airport SAF demand
          </h2>
          <p className="mt-1 text-xs text-slate-500">kt SAF per year. The brief gives no demand figures, so these are inputs.</p>
        </div>

        {p.airports.map((a) => (
          <div key={a.id}>
            <label htmlFor={`d_${a.id}`} className="block text-sm text-slate-800">
              {a.name} <span className="text-xs text-slate-500">{a.id}</span>
            </label>
            <div className="mt-1.5 flex h-9 items-center rounded-md border border-slate-200 bg-white focus-within:border-slate-400">
              <input
                id={`d_${a.id}`}
                type="number"
                inputMode="decimal"
                min={0}
                step={STEP_KT}
                value={Number.isFinite(demand?.[a.id]) ? demand[a.id] : ""}
                onChange={(e) => set(a.id, parseFloat(e.target.value))}
                onBlur={(e) => e.target.value === "" && set(a.id, 0)}
                className="h-full min-w-0 flex-1 bg-transparent px-3 text-sm tabular-nums text-slate-900 outline-none"
              />
              <button type="button" aria-label={`Decrease ${a.id} demand`} onClick={() => set(a.id, (demand[a.id] || 0) - STEP_KT)}
                className="grid h-full w-8 place-items-center text-slate-500 hover:bg-slate-50 hover:text-slate-800">
                <Minus className="h-3.5 w-3.5" aria-hidden />
              </button>
              <button type="button" aria-label={`Increase ${a.id} demand`} onClick={() => set(a.id, (demand[a.id] || 0) + STEP_KT)}
                className="grid h-full w-8 place-items-center text-slate-500 hover:bg-slate-50 hover:text-slate-800">
                <Plus className="h-3.5 w-3.5" aria-hidden />
              </button>
            </div>
          </div>
        ))}

        <div>
          <label htmlFor="time-limit" className="flex items-baseline justify-between text-sm text-slate-800">
            Solver time limit
            <span className="tabular-nums text-xs text-slate-500">{TIME_LIMITS[limitIdx]} s</span>
          </label>
          <input
            id="time-limit"
            type="range"
            min={0}
            max={TIME_LIMITS.length - 1}
            step={1}
            value={limitIdx}
            onChange={(e) => setLimitIdx(Number(e.target.value))}
            aria-valuetext={`${TIME_LIMITS[limitIdx]} seconds`}
            className="mt-2 w-full accent-brand"
          />
          <p className="mt-1 text-xs text-slate-500">Longer runs can prove the plan optimal; shorter runs report how close they got.</p>
        </div>

        <button
          type="submit"
          disabled={p.solving || overLimit}
          className="h-9 w-full rounded-md bg-brand text-sm font-medium text-white hover:bg-green-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {p.solving ? `Solving (up to ${TIME_LIMITS[limitIdx]} s)…` : "Solve"}
        </button>

        {overLimit && (
          <p role="alert" className="border-l-2 border-rose-500 bg-rose-50 p-2.5 text-xs text-rose-800">
            Demand exceeds what all 6,800 kt of biomass can make: {num(total, 1)} kt SAF asked,{" "}
            {num(p.maxTotalDemandKt, 1)} kt SAF possible.
          </p>
        )}
        {p.solveError && (
          <p role="alert" className="break-words border-l-2 border-rose-500 bg-rose-50 p-2.5 text-xs text-rose-800">
            {p.solveError}
          </p>
        )}
        {p.solverOnline === false && !p.solveError && (
          <p className="border-l-2 border-amber-500 bg-amber-50 p-2.5 text-xs leading-relaxed text-amber-800">
            Solver offline: showing saved plans. To re-solve, start it from the project folder with{" "}
            <code className="break-all">{START_COMMAND}</code>
          </p>
        )}
        <p className="text-xs text-slate-500">
          The 6,800 kt of biomass can make at most <b className="text-slate-700">{num(p.maxTotalDemandKt)} kt</b> SAF a year.
        </p>
      </form>

      <fieldset className="mt-6 border-t border-slate-200 pt-5">
        <legend className={`${label} float-left mb-3 w-full`}>Plan on the map</legend>
        <div className="clear-both space-y-1">
          {PLAN_OPTIONS.map((o) => (
            <label
              key={o.id}
              className={`flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm ${
                p.scenarioId === o.id ? "bg-slate-100 text-slate-900" : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <input
                type="radio"
                name="plan"
                value={o.id}
                checked={p.scenarioId === o.id}
                onChange={() => p.onScenarioChange(o.id)}
                className="h-3.5 w-3.5 accent-brand"
              />
              {o.label}
            </label>
          ))}
        </div>
      </fieldset>
    </aside>
  );
}
