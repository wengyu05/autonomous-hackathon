export interface KpiCardProps {
  label: string;
  value: string;
  /** Optional comparison pill under the value, e.g. "▲ $175.6M more than optimised". */
  delta?: string;
}

/** One headline number, styled like a Streamlit st.metric. */
export default function KpiCard(p: KpiCardProps) {
  return (
    <article>
      <h3 className="text-sm text-ink-2">{p.label}</h3>
      <p className="mt-1 text-[1.75rem] leading-tight tabular-nums text-ink">{p.value}</p>
      {p.delta && (
        <p className="mt-1 inline-block rounded-full bg-critical-soft px-2 text-xs text-critical">{p.delta}</p>
      )}
    </article>
  );
}
