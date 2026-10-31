import type { Results } from "@/lib/types";
import { usd } from "@/lib/format";
import { DataTable } from "./Tables";

// The annual items charted in the Streamlit app, in its order.
const CHARTED = [
  "CapEx annualised",
  "OpEx",
  "Logistics: biomass to depot",
  "Logistics: depot to refinery",
  "Logistics: refinery to airport",
  "Sea surcharge (Tarakan)",
];

/** Costs tab: bar chart of the annual cost items plus the full breakdown table (optimised plan only). */
export default function CostChart({ data }: { data: Results }) {
  const items = data.summary.costItems;
  if ((data.meta?.scenario ?? "optimised") !== "optimised" || !items) {
    return (
      <p className="rounded-lg bg-[#e8f0fb] px-4 py-3 text-sm text-[#1d4f91]">
        The detailed cost breakdown is for the optimised plan. Baseline totals are in the Baselines tab.
      </p>
    );
  }
  const bars = CHARTED.map((k) => ({ k, v: items.find((i) => i.item === k)?.usd ?? 0 }));
  const top = Math.max(1, ...bars.map((b) => b.v));

  return (
    <div className="space-y-4">
      <figure aria-label="Annual cost by item, USD million per year" className="space-y-1.5">
        {bars.map((b) => (
          <div key={b.k} className="grid grid-cols-[200px_1fr_64px] items-center gap-2 text-sm">
            <span className="truncate text-ink-2">{b.k}</span>
            <span className="h-4 rounded-r bg-[#eef1ef]">
              <span className="block h-full rounded-r bg-[#2a78d6]" style={{ width: `${(100 * b.v) / top}%` }} />
            </span>
            <span className="text-right tabular-nums text-ink-2">${(b.v / 1e6).toFixed(1)}M</span>
          </div>
        ))}
        <figcaption className="pt-1 text-center text-xs text-ink-2">USD million per year</figcaption>
      </figure>
      <DataTable
        caption="Cost breakdown"
        rows={items}
        columns={[
          { label: "Item", cell: (r) => r.item },
          { label: "USD", numeric: true, cell: (r) => (r.basis === "USD/t" ? `$${r.usd.toFixed(2)}` : usd(r.usd)) },
          { label: "Basis", cell: (r) => r.basis },
        ]}
      />
    </div>
  );
}
