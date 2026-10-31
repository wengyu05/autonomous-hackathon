export type Trend = "good" | "bad" | "neutral";

export interface KpiCardProps {
  label: string;
  value: string;
  unit?: string;
  /** Comparison line, e.g. "47.1% lower than B1". */
  trendText: string;
  trend: Trend;
  /** Optional caveat shown in amber under the value, e.g. the optimality gap. */
  note?: string;
}

const TREND = {
  good: "text-emerald-700",
  bad: "text-rose-700",
  neutral: "text-slate-500",
};

export default function KpiCard(p: KpiCardProps) {
  return (
    <article className="border-l-2 border-slate-200 pl-4">
      <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">{p.label}</h3>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">
        {p.value}
        {p.unit && <span className="ml-1 text-sm font-normal text-slate-500">{p.unit}</span>}
      </p>
      <p className={`mt-1 text-xs ${TREND[p.trend]}`}>{p.trendText}</p>
      {p.note && <p className="mt-0.5 text-xs text-amber-700">{p.note}</p>}
    </article>
  );
}
