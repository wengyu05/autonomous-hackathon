import type { KpiCardProps } from "@/components/KpiCard";
import type { Results } from "./types";
import { usdShort } from "./format";

/**
 * The five headline numbers of the Streamlit app, in its order. A baseline also shows how much
 * more it costs per year than the optimised plan.
 */
export function buildKpis(d: Results): KpiCardProps[] {
  const s = d.summary;
  const optimised = d.meta?.comparisons?.find((p) => p.id === "optimised");
  const isOptimised = (d.meta?.scenario ?? "optimised") === "optimised";
  return [
    {
      label: "Total cost per year",
      value: usdShort(s.totalCost),
      delta: !isOptimised && optimised ? `▲ ${usdShort(s.totalCost - optimised.totalCost)} more than optimised` : undefined,
    },
    { label: "Cost per tonne of SAF", value: `$${Math.round(s.costPerTonne).toLocaleString("en-US")}` },
    { label: "One-time CapEx", value: usdShort(s.capexOneTime ?? 0) },
    { label: "Trucking per year", value: usdShort(s.logistics) },
    { label: "Refinery · depot sites", value: `${d.refineries.length} · ${d.depots.length}` },
  ];
}
