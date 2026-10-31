"use client";

import { useEffect, useState } from "react";
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

/** Left panel, as in the Streamlit app: airport demand inputs, Solve, and the plan shown on the map. */
export default function Sidebar(p: SidebarProps) {
  const [demand, setDemand] = useState<Record<string, number>>(p.demandKt);
  const [limitIdx, setLimitIdx] = useState(0);

  // A new solve (or the first load) resets the boxes to the demand the plan was solved for.
  useEffect(() => setDemand(p.demandKt), [p.demandKt]);

  const set = (id: string, v: number) => setDemand((d) => ({ ...d, [id]: Math.max(0, Math.min(p.maxTotalDemandKt, v)) }));
  const total = Object.values(demand ?? {}).reduce((t, v) => t + (Number.isFinite(v) ? v : 0), 0);
  const overLimit = total > p.maxTotalDemandKt + 1e-9;

  return (
    <aside className="w-full shrink-0 bg-side px-4 py-8 md:sticky md:top-0 md:h-screen md:w-[330px] md:overflow-y-auto">
      <h2 className="text-[1.35rem] font-semibold text-ink">Airport SAF demand</h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-2">
        kt of SAF per year. The brief gives no demand figures, so these are inputs.
      </p>

      <form
        className="mt-5 space-y-4 rounded-lg border border-line bg-side p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!overLimit && !p.solving) p.onSolve(demand, TIME_LIMITS[limitIdx]);
        }}
      >
        {p.airports.map((a) => (
          <div key={a.id}>
            <label htmlFor={`d_${a.id}`} className="block text-sm text-ink">
              {a.id} · {a.name}
            </label>
            <div className="mt-1.5 flex h-11 items-center rounded-md bg-white">
              <input
                id={`d_${a.id}`}
                type="number"
                inputMode="decimal"
                min={0}
                step={STEP_KT}
                value={Number.isFinite(demand[a.id]) ? demand[a.id] : ""}
                onChange={(e) => set(a.id, parseFloat(e.target.value))}
                onBlur={(e) => e.target.value === "" && set(a.id, 0)}
                className="h-full min-w-0 flex-1 bg-transparent px-3.5 text-sm tabular-nums text-ink outline-none"
              />
              <button type="button" aria-label={`Decrease ${a.id} demand`} onClick={() => set(a.id, (demand[a.id] || 0) - STEP_KT)}
                className="grid h-full w-9 place-items-center text-lg text-ink hover:bg-side">−</button>
              <button type="button" aria-label={`Increase ${a.id} demand`} onClick={() => set(a.id, (demand[a.id] || 0) + STEP_KT)}
                className="grid h-full w-9 place-items-center text-lg text-ink hover:bg-side">+</button>
            </div>
          </div>
        ))}

        <div>
          <label htmlFor="time-limit" className="flex items-center justify-between text-sm text-ink">
            Solver time limit (s)
            <span className="text-ink-2" title="Longer runs can prove the plan optimal; shorter runs report how close they got.">ⓘ</span>
          </label>
          <p className="mt-1 text-sm tabular-nums text-brand">{TIME_LIMITS[limitIdx]}</p>
          <input
            id="time-limit"
            type="range"
            min={0}
            max={TIME_LIMITS.length - 1}
            step={1}
            value={limitIdx}
            onChange={(e) => setLimitIdx(Number(e.target.value))}
            aria-valuetext={`${TIME_LIMITS[limitIdx]} seconds`}
            className="mt-1 w-full accent-brand"
          />
        </div>

        <button
          type="submit"
          disabled={p.solving || overLimit}
          className="h-11 w-full rounded-md bg-brand text-sm font-medium text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60"
        >
          {p.solving ? `Solving (up to ${TIME_LIMITS[limitIdx]} s)…` : "Solve"}
        </button>

        {overLimit && (
          <p role="alert" className="text-sm text-critical">
            Demand exceeds what all 6,800 kt of biomass can make: {num(total, 1)} kt SAF asked,{" "}
            {num(p.maxTotalDemandKt, 1)} kt SAF possible.
          </p>
        )}
        {p.solveError && (
          <p role="alert" className="break-words text-sm text-critical">
            {p.solveError}
          </p>
        )}
        {p.solverOnline === false && !p.solveError && (
          <p className="text-xs leading-relaxed text-ink-2">
            Solver offline: showing saved plans. To re-solve, start it from the project folder with{" "}
            <code className="rounded bg-white px-1">{START_COMMAND}</code>.
          </p>
        )}
      </form>

      <p className="mt-4 text-sm leading-relaxed text-ink-2">
        The 6,800 kt of biomass can make at most <b className="text-ink">{num(p.maxTotalDemandKt)} kt</b> SAF a year.
      </p>

      <hr className="my-6 border-line" />

      <fieldset>
        <legend className="text-sm text-ink">Plan on the map</legend>
        <div className="mt-2 space-y-1.5">
          {PLAN_OPTIONS.map((o) => (
            <label key={o.id} className="flex cursor-pointer items-center gap-2.5 text-sm text-ink">
              <input
                type="radio"
                name="plan"
                value={o.id}
                checked={p.scenarioId === o.id}
                onChange={() => p.onScenarioChange(o.id)}
                className="h-4 w-4 accent-brand"
              />
              {o.label}
            </label>
          ))}
        </div>
      </fieldset>
    </aside>
  );
}
