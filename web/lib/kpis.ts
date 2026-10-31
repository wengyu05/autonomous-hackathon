import type { KpiCardProps } from "@/components/KpiCard";
import type { PlanComparison, Results } from "./types";
import { num, pctChange, usdM, usdShort } from "./format";

/** Plain-text solver status: "Optimal" only when proven, otherwise the remaining gap. */
export function statusText(d: Results): string {
  const m = d.meta;
  if (!m) return "Mock data";
  if (m.scenario !== "optimised") return "Rule-based baseline";
  if (m.status === "Optimal") return "Proven optimal";
  return m.gap != null ? `Not proven optimal (gap ${(m.gap * 100).toFixed(0)}%)` : m.status;
}

/**
 * The plan the cards compare against: the optimised plan is compared with baseline B1
 * (one central refinery, the closest simple alternative); a baseline is compared with the optimised plan.
 */
export function referencePlan(d: Results): PlanComparison | undefined {
  const plans = d.meta?.comparisons ?? [];
  const current = d.meta?.scenario ?? "optimised";
  return current === "optimised" ? plans.find((p) => p.id === "b1") : plans.find((p) => p.id === "optimised");
}

function shortName(p: PlanComparison): string {
  return p.id === "optimised" ? "the optimised plan" : p.id.toUpperCase();
}

/** Lower-is-better comparison text, e.g. "47.1% lower than B1". */
function costTrend(value: number, ref?: PlanComparison, refValue?: number): Pick<KpiCardProps, "trendText" | "trend"> {
  if (!ref || refValue == null) return { trendText: "No comparison plan", trend: "neutral" };
  const pct = pctChange(value, refValue);
  return {
    trendText: `${Math.abs(pct).toFixed(1)}% ${pct < 0 ? "lower" : "higher"} than ${shortName(ref)}`,
    trend: pct < 0 ? "good" : "bad",
  };
}

/** The Streamlit app's five headline numbers, in its order, each compared with the reference plan. */
export function buildKpis(d: Results): KpiCardProps[] {
  const s = d.summary;
  const ref = referencePlan(d);
  const refineryUnits = d.refineries.reduce((t, r) => t + (r.units ? countUnits(r.units) : 1), 0);
  const isOptimised = (d.meta?.scenario ?? "optimised") === "optimised";

  return [
    {
      label: "Total cost",
      value: usdM(s.totalCost),
      unit: "per year",
      ...costTrend(s.totalCost, ref, ref?.totalCost),
      note: isOptimised && d.meta?.status !== "Optimal" ? statusText(d) : undefined,
    },
    {
      label: "Cost per tonne SAF",
      value: `$${num(s.costPerTonne)}`,
      unit: "/t",
      ...costTrend(s.costPerTonne, ref, ref?.costPerTonne),
    },
    {
      label: "One-time CapEx",
      value: usdShort(s.capexOneTime ?? 0),
      ...costTrend(s.capexOneTime ?? 0, ref, ref?.capexOneTime),
    },
    {
      label: "Trucking",
      value: usdM(s.logistics),
      unit: "per year",
      ...costTrend(s.logistics, ref, ref?.logistics),
    },
    {
      label: "Refineries · depots",
      value: `${refineryUnits} · ${d.depots.length}`,
      unit: "sites",
      trendText: ref
        ? `${shortName(ref)}: ${ref.refineries} ${ref.refineries === 1 ? "refinery" : "refineries"} · ${ref.depotSites} depots`
        : "",
      trend: "neutral",
    },
  ];
}

/** "1 Large + 1 Small" -> 2. */
export function countUnits(units: string): number {
  return [...units.matchAll(/(\d+)\s+(Small|Large)/g)].reduce((t, m) => t + Number(m[1]), 0) || 1;
}
