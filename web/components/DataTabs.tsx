"use client";

import { useState } from "react";
import type { Results } from "@/lib/types";
import AirportList from "./AirportList";
import CostChart from "./CostChart";
import { AssumptionsTable, BaselineTable, ChecksTab, CostItemsTable, FacilityTable, FlowTable } from "./Tables";

const TABS = ["Airports", "Facilities", "Costs", "Routes", "Baselines", "Checks", "Assumptions"] as const;
type Tab = (typeof TABS)[number];

/** The seven data tabs beside the map, in the Streamlit app's order. */
export default function DataTabs({ data, query, selectedId, onSelect }: {
  data: Results;
  query: string;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const [tab, setTab] = useState<Tab>("Airports");

  return (
    <div className="min-w-0">
      <div role="tablist" aria-label="Plan data" className="flex flex-wrap gap-x-4 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            id={`tab-${t}`}
            aria-selected={tab === t}
            aria-controls={`panel-${t}`}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 py-2 text-sm ${
              tab === t ? "border-brand font-medium text-slate-900" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="pt-4">
        {tab === "Airports" && (
          <AirportList
            airports={data.airports}
            safDelivered={data.summary.safDelivered}
            selectedId={selectedId}
            onSelect={onSelect}
            flows={data.flows}
          />
        )}
        {tab === "Facilities" && (
          <>
            <FacilityTable data={data} query={query} selectedId={selectedId} onSelect={onSelect} />
            <p className="mt-3 text-xs text-slate-500">
              Depot capacity is biomass in; refinery capacity is SAF out. Small and Large depots cost the same per kt, so
              total capacity per site is the real decision.
            </p>
          </>
        )}
        {tab === "Costs" && (
          <div className="space-y-5">
            <CostChart summary={data.summary} flows={data.flows} />
            <CostItemsTable data={data} />
          </div>
        )}
        {tab === "Routes" && <FlowTable data={data} query={query} selectedId={selectedId} onSelect={onSelect} />}
        {tab === "Baselines" && <BaselineTable data={data} />}
        {tab === "Checks" && <ChecksTab data={data} />}
        {tab === "Assumptions" && <AssumptionsTable data={data} />}
      </div>
    </div>
  );
}
