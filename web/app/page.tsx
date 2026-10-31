"use client";

import { useEffect, useMemo, useState } from "react";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import KpiCard from "@/components/KpiCard";
import NetworkMap from "@/components/NetworkMapLoader";
import DataTabs from "@/components/DataTabs";
import { buildKpis } from "@/lib/kpis";
import { solve, solverOnline } from "@/lib/solver";
import { useResults } from "@/lib/useResults";

/** Same layout as the Streamlit app: inputs on the left, map beside the data tabs on the right. */
export default function Dashboard() {
  const { scenarioId, setScenarioId, data, error, loading, reload } = useResults();
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
  const demandKey = JSON.stringify(data?.meta?.demandKt ?? {});
  const demandKt = useMemo(() => JSON.parse(demandKey) as Record<string, number>, [demandKey]);

  const onSolve = async (demand: Record<string, number>, timeLimitS: number) => {
    setSolving(true);
    setSolveError(null);
    try {
      await solve(demand, timeLimitS);
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

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      {data && (
        <Sidebar
          airports={data.airports}
          demandKt={demandKt}
          maxTotalDemandKt={data.meta?.maxTotalDemandKt ?? 1360}
          scenarioId={scenarioId}
          onScenarioChange={setScenarioId}
          onSolve={onSolve}
          solving={solving}
          solveError={solveError}
          solverOnline={online}
        />
      )}

      <main className="mx-auto w-full min-w-0 max-w-[1560px] flex-1 px-4 py-10 sm:px-12 lg:px-20" aria-busy={loading || solving}>
        {error && (
          <p role="alert" className="mb-4 rounded-lg bg-critical-soft p-3 text-sm text-critical">
            {error}
          </p>
        )}
        {data && (
          <div className="space-y-6">
            <Header data={data} />

            <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-5">
              {buildKpis(data).map((k) => (
                <KpiCard key={k.label} {...k} />
              ))}
            </div>

            <div className="grid grid-cols-1 gap-6 xl:grid-cols-[3fr_2fr]">
              <div className="space-y-3">
                <div className="h-[660px]">
                  <NetworkMap data={data} selectedId={selectedId} onSelect={setSelectedId} />
                </div>
                <p className="text-sm text-ink-2">
                  Truck routes follow OpenStreetMap roads (routing by OSRM); arrows show which way the trucks drive.
                  Hover lines and markers for details; click a site to highlight its routes. The layers button (top
                  right) turns groups on and off. © OpenStreetMap contributors.
                </p>
                <p className="rounded-lg bg-warn px-4 py-3 text-sm text-warn-ink">
                  ⚠️ <b>Known limit: Tarakan (TRK) is on an island.</b> Its SAF reaches it by the ferry in the road
                  network, priced at the truck rate. A real plan needs a barge or ferry tariff (assumption A12).
                </p>
              </div>
              <DataTabs data={data} selectedId={selectedId} onSelect={setSelectedId} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
