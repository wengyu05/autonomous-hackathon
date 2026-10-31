import type { Results } from "@/lib/types";

/** Title, one-line description and the solver status banner, as at the top of the Streamlit app. */
export default function Header({ data }: { data: Results }) {
  const m = data.meta;
  // The banner always describes the optimised solve, whichever plan the map shows.
  const status = m?.optimisedStatus ?? m?.status ?? "n/a";
  const gap = m?.optimisedGap ?? m?.gap;
  const secs = m?.optimisedSolveTimeS ?? m?.solveTimeS;
  const optimal = status === "Optimal" && m?.verified;
  const demand = Object.entries(m?.demandKt ?? {})
    .map(([k, v]) => `${k} ${v}`)
    .join(" · ");

  return (
    <header>
      <h1 className="text-[2.6rem] font-bold leading-tight tracking-tight text-ink">Kalimantan SAF Planner</h1>
      <p className="mt-3 text-base text-ink">
        Where to build biomass depots and SAF refineries, and how to truck everything along real roads to
        Kalimantan&apos;s four international airports at the lowest annual cost.
      </p>
      <p
        role="status"
        className={`mt-4 rounded-lg px-4 py-3.5 text-base ${optimal ? "bg-ok text-ok-ink" : "bg-warn text-warn-ink"}`}
      >
        <span aria-hidden>{optimal ? "✅" : "⏱️"}</span> <b>{status}</b>
        {gap != null && <> · within {(gap * 100).toFixed(2)}% of the best possible plan</>}
        {secs != null && <> · solved in {Math.round(secs)} s</>}
        {m?.checksTotal ? <> · independent check {m.checksPassed}/{m.checksTotal} pass</> : null}
        {demand && <> · demand {demand} kt SAF/yr</>}
      </p>
    </header>
  );
}
