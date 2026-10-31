"use client";

import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import Header from "@/components/Header";
import KpiCard from "@/components/KpiCard";
import NetworkMap from "@/components/NetworkMapLoader";
import AirportList from "@/components/AirportList";
import CostChart from "@/components/CostChart";
import { FacilityTable, FlowTable } from "@/components/Tables";
import { buildKpis, statusText } from "@/lib/kpis";
import { num } from "@/lib/format";
import { useResults } from "@/lib/useResults";

/** Report section with a plain heading and an optional note on the right. */
function Section({ id, title, note, children }: { id: string; title: string; note?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-4 border-t border-slate-200 pt-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={`${id}-title`} className="text-base font-semibold text-slate-900">
          {title}
        </h2>
        {note && <div className="text-xs text-slate-500">{note}</div>}
      </div>
      {children}
    </section>
  );
}

export default function Dashboard() {
  const { scenarios, scenarioId, setScenarioId, data, error, loading, file } = useResults();
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // A new scenario has different facility IDs, so drop any selection.
  useEffect(() => setSelectedId(null), [scenarioId]);

  const demand = data?.airports.reduce((t, a) => t + a.demandKt, 0) ?? 0;
  const subtitle = data
    ? `${data.meta?.label ?? "Plan"} · demand ${num(demand)} kt SAF/yr across ${data.airports.length} airports`
    : undefined;

  return (
    <div className="flex min-h-screen flex-col bg-white md:flex-row">
      <Sidebar />

      <main className="mx-auto w-full min-w-0 max-w-[1400px] flex-1 space-y-8 px-4 py-6 sm:px-8" aria-busy={loading}>
        <section id="overview" className="scroll-mt-4 space-y-6">
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
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
              {buildKpis(data).map((k) => (
                <KpiCard key={k.label} {...k} />
              ))}
            </div>
          )}
        </section>

        {data && (
          <>
            <Section
              id="network"
              title="Network map"
              note={
                <>
                  Solver: {data.meta?.solver ?? "n/a"} · {statusText(data)}
                  {data.meta?.checksTotal ? ` · independent checks ${data.meta.checksPassed}/${data.meta.checksTotal} passed` : ""}
                </>
              }
            >
              <div className="grid gap-6 lg:grid-cols-3">
                <div className="h-[460px] lg:col-span-2 lg:h-[560px]">
                  <NetworkMap data={data} selectedId={selectedId} onSelect={setSelectedId} />
                </div>
                <AirportList
                  airports={data.airports}
                  safDelivered={data.summary.safDelivered}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              </div>

              <p className="mt-3 text-xs text-slate-500" aria-live="polite">
                {selectedId ? (
                  <>
                    Showing flows connected to {selectedId}.{" "}
                    <button type="button" onClick={() => setSelectedId(null)} className="underline hover:text-slate-800">
                      Clear
                    </button>
                  </>
                ) : (
                  "Hover a marker or line for details. Click a facility to show only its flows. Tarakan (TRK) is on an island: its leg uses the ferry, priced at the truck rate."
                )}
              </p>
            </Section>

            <Section id="costs" title="Annual cost">
              <CostChart summary={data.summary} flows={data.flows} />
            </Section>

            <Section
              id="facilities"
              title="Facilities"
              note="Depot capacity is biomass in; refinery capacity is SAF out. Small and Large depots cost the same per kt."
            >
              <FacilityTable data={data} query={query} selectedId={selectedId} onSelect={setSelectedId} />
            </Section>

            <Section id="flows" title="Flows">
              <FlowTable data={data} query={query} selectedId={selectedId} onSelect={setSelectedId} />
            </Section>
          </>
        )}
      </main>
    </div>
  );
}
