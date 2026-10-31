"use client";

import { Cell, Pie, PieChart, Tooltip } from "recharts";
import type { Flow, Leg, Summary } from "@/lib/types";
import { LEG_STYLE } from "@/lib/legs";
import { usdM } from "@/lib/format";

interface CostChartProps {
  summary: Summary;
  flows: Flow[];
}

/** Donut of annual cost (CapEx, fixed OpEx, variable OpEx, logistics) plus logistics split by leg. */
export default function CostChart({ summary, flows }: CostChartProps) {
  const slices = [
    { name: "CapEx (annualised)", value: summary.capex, color: "#14532d" },
    { name: "Fixed OpEx", value: summary.opex, color: "#86b08f" },
    { name: "Variable OpEx", value: summary.variableOpex ?? 0, color: "#c9a227" },
    { name: "Logistics", value: summary.logistics, color: "#94a3b8" },
  ];
  const byLeg = (Object.keys(LEG_STYLE) as Leg[]).map((leg) => ({
    leg,
    value: flows.filter((f) => f.leg === leg).reduce((t, f) => t + f.cost, 0),
  }));
  const legTotal = byLeg.reduce((t, l) => t + l.value, 0) || 1;

  return (
    <div className="grid gap-6 sm:grid-cols-[200px_1fr] sm:items-center">
      <div className="relative mx-auto h-[200px] w-[200px]" role="img" aria-label={`Annual cost ${usdM(summary.totalCost)}: ${slices.map((s) => `${s.name} ${usdM(s.value)}`).join(", ")}`}>
        {/* Fixed size: the donut column is always 200px wide. */}
        <PieChart width={200} height={200}>
            <Pie data={slices} dataKey="value" nameKey="name" innerRadius={58} outerRadius={84} paddingAngle={0} stroke="none" isAnimationActive={false}>
              {slices.map((s) => (
                <Cell key={s.name} fill={s.color} />
              ))}
            </Pie>
            <Tooltip formatter={(v) => usdM(Number(v))} />
        </PieChart>
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <p className="text-xs text-slate-500">per year</p>
            <p className="text-lg font-semibold text-slate-900">{usdM(summary.totalCost)}</p>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <ul className="space-y-2">
          {slices.map((s) => (
            <li key={s.name} className="flex items-center justify-between gap-3 text-sm">
              <span className="flex items-center gap-2 text-slate-700">
                <span className="h-2.5 w-2.5" style={{ background: s.color }} aria-hidden />
                {s.name}
              </span>
              <span className="tabular-nums text-slate-900">
                {usdM(s.value)}
                <span className="ml-2 text-xs text-slate-500">{((s.value / summary.totalCost) * 100).toFixed(0)}%</span>
              </span>
            </li>
          ))}
        </ul>

        <div>
          <p className="mb-1.5 text-xs font-medium text-slate-500">Logistics by leg</p>
          <div className="flex h-2 overflow-hidden bg-slate-100">
            {byLeg.map((l) => (
              <div key={l.leg} style={{ width: `${(l.value / legTotal) * 100}%`, background: LEG_STYLE[l.leg].color }} />
            ))}
          </div>
          <ul className="mt-2 space-y-1">
            {byLeg.map((l) => (
              <li key={l.leg} className="flex justify-between text-xs text-slate-600">
                <span>{LEG_STYLE[l.leg].label}</span>
                <span className="tabular-nums">{usdM(l.value)}</span>
              </li>
            ))}
          </ul>
        </div>

        {summary.capexOneTime != null && (
          <p className="text-xs text-slate-500">
            One-time construction: <b className="text-slate-700">{usdM(summary.capexOneTime, 0)}</b>, spread over the
            20-year plant life (straight-line) as annualised CapEx.
          </p>
        )}
      </div>
    </div>
  );
}
