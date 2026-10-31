"use client";

import { useState } from "react";
import type { Results } from "@/lib/types";
import AirportList from "./AirportList";
import CostChart from "./CostChart";
import { AssumptionsTable, BaselineTable, ChecksTab, FacilityTable, FlowTable } from "./Tables";

const TABS = ["Airports", "Facilities", "Costs", "Routes", "Baselines", "Checks", "Assumptions"] as const;
type Tab = (typeof TABS)[number];

/** The seven data tabs beside the map, in the Streamlit app's order. */
export default function DataTabs({ data, selectedId, onSelect }: {
  data: Results;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const [tab, setTab] = useState<Tab>("Airports");

  return (
    <div>
      <div role="tablist" aria-label="Plan data" className="flex flex-wrap gap-x-5 border-b-2 border-line">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            id={`tab-${t}`}
            aria-selected={tab === t}
            aria-controls={`panel-${t}`}
            onClick={() => setTab(t)}
            className={`-mb-0.5 border-b-2 py-2 text-[0.95rem] ${tab === t ? "border-brand text-brand" : "border-transparent text-ink hover:text-brand"}`}
          >
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="pt-5">
        {tab === "Airports" && <AirportList data={data} />}
        {tab === "Facilities" && <FacilityTable data={data} selectedId={selectedId} onSelect={onSelect} />}
        {tab === "Costs" && <CostChart data={data} />}
        {tab === "Routes" && <FlowTable data={data} selectedId={selectedId} onSelect={onSelect} />}
        {tab === "Baselines" && <BaselineTable data={data} />}
        {tab === "Checks" && <ChecksTab data={data} />}
        {tab === "Assumptions" && <AssumptionsTable data={data} />}
      </div>
    </div>
  );
}
