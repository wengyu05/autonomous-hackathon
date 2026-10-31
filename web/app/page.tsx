"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import KpiCard from "@/components/KpiCard";
import NetworkMap from "@/components/NetworkMapLoader";
import DataTabs from "@/components/DataTabs";
import { buildKpis } from "@/lib/kpis";
import { num } from "@/lib/format";
import { solve, solverOnline } from "@/lib/solver";
import { useResults } from "@/lib/useResults";
import type { Distances } from "@/lib/types";

/** Solver result for the optimised plan, shown whichever plan is on the map (as the Streamlit app does). */
function StatusBar({ meta }: { meta: NonNullable<ReturnType<typeof useResults>["data"]>["meta"] }) {
  const status = meta?.optimisedStatus ?? meta?.status ?? "n/a";
  const gap = meta?.optimisedGap ?? meta?.gap;
  const secs = meta?.optimisedSolveTimeS ?? meta?.solveTimeS;
  const ok = status === "Optimal" && meta?.verified;
  const demand = Object.entries(meta?.demandKt ?? {}).map(([k, v]) => `${k} ${num(v)}`).join(" · ");
  return (
    <p
      role="status"
      className={`border-l-2 p-3 text-sm ${ok ? "border-emerald-600 bg-emerald-50 text-emerald-900" : "border-amber-500 bg-amber-50 text-amber-900"}`}
    >
      <b>{ok ? "Proven optimal" : status}</b>
      {gap != null && ` · within ${(gap * 100).toFixed(2)}% of the best possible plan`}
      {secs != null && ` · solved in ${Math.round(secs)} s`}
      {meta?.checksTotal ? ` · independent checks ${meta.checksPassed}/${meta.checksTotal} passed` : ""}
      {demand && ` · demand ${demand} kt SAF/yr`}
    </p>
  );
}

/**
 * Arranged like the Streamlit app: demand inputs on the left; title, solver status and headline numbers
 * on top; the map beside the data tabs.
 */
export default function Dashboard() {
  const [distances, setDistances] = useState<Distances>("official");
  const { scenarios, scenarioId, setScenarioId, data, error, loading, file, reload } = useResults(distances);
  // The sidebar's airports and limit, kept while a mode with no saved plan is selected so it can be switched back.
  const lastData = useRef(data);
  if (data) lastData.current = data;
  const side = data ?? lastData.current;
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [solving, setSolving] = useState(false);
  const [solveError, setSolveError] = useState<string | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);

  // A new plan has different facility IDs, so drop any selection.
  useEffect(() => setSelectedId(null), [scenarioId, data]);
  useEffect(() => {
    solverOnline().then(setOnline);
  }, []);

  // Stable object so the sidebar's boxes only reset when the solved-for demand really changes.
  const demandKey = JSON.stringify(side?.meta?.demandKt ?? {});
  const demandKt = useMemo(() => JSON.parse(demandKey) as Record<string, number>, [demandKey]);

  const onSolve = async (demand: Record<string, number>, timeLimitS: number) => {
    setSolving(true);
    setSolveError(null);
    try {
      await solve(demand, timeLimitS, distances);
      setOnline(true);
      setScenarioId("optimised");
      reload();
    } catch (e) {
      setSolveError((e as Error).message);
      solverOnline().then(setOnline);
    } finally {
      setSolving(false);
    }
  };

  const demand = data?.airports.reduce((t, a) => t + a.demandKt, 0) ?? 0;
  const subtitle = data
    ? `${data.meta?.label ?? "Plan"} · demand ${num(demand)} kt SAF/yr across ${data.airports.length} airports`
    : undefined;

  return (
    <div className="flex min-h-screen flex-col bg-white md:flex-row">
      {side && (
        <Sidebar
          airports={side.airports}
          demandKt={demandKt}
          maxTotalDemandKt={side.meta?.maxTotalDemandKt ?? 1360}
          scenarioId={scenarioId}
          onScenarioChange={setScenarioId}
          distances={distances}
          onDistancesChange={setDistances}
          onSolve={onSolve}
          solving={solving}
          solveError={solveError}
          solverOnline={online}
        />
      )}

      <main className="mx-auto w-full min-w-0 max-w-[1500px] flex-1 space-y-6 px-4 py-6 sm:px-8" aria-busy={loading || solving}>
        <Header
          scenarios={scenarios}
          scenarioId={scenarioId}
          onScenarioChange={setScenarioId}
          file={file}
          query={query}
          onQueryChange={setQuery}
          subtitle={subtitle}
        />

        {error && (
          <p role="alert" className="border-l-2 border-rose-500 bg-rose-50 p-3 text-sm text-rose-800">
            {error}
          </p>
        )}

        {data && (
          <>
            <StatusBar meta={data.meta} />

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
              {buildKpis(data).map((k) => (
                <KpiCard key={k.label} {...k} />
              ))}
            </div>

            <div className="grid grid-cols-1 gap-6 border-t border-slate-200 pt-6 xl:grid-cols-[3fr_2fr]">
              <div className="min-w-0 space-y-3">
                <div className="h-[460px] lg:h-[620px]">
                  <NetworkMap data={data} selectedId={selectedId} onSelect={setSelectedId} />
                </div>
                <p className="text-xs text-slate-500" aria-live="polite">
                  {selectedId ? (
                    <>
                      Showing routes connected to {selectedId}.{" "}
                      <button type="button" onClick={() => setSelectedId(null)} className="underline hover:text-slate-800">
                        Clear
                      </button>
                    </>
                  ) : (
                    `${data.flows.some((f) => f.path) ? "Truck routes follow OpenStreetMap roads (routing by OSRM)" : "Lines are straight: distances are great-circle km × 1.3, as the organisers specify"}; arrows show which way the trucks drive. Hover a marker or line for details; click a site to show only its routes.`
                  )}
                </p>
                <p className="border-l-2 border-sky-600 bg-sky-50 p-3 text-xs text-sky-900">
                  <b>Tarakan (TRK) is on an island.</b> Its last leg is a barge at the same $0.08 per t·km as the truck leg,
                  with no extra fixed cost, as the organisers specify (assumption A12).
                </p>
              </div>
              <DataTabs data={data} query={query} selectedId={selectedId} onSelect={setSelectedId} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
