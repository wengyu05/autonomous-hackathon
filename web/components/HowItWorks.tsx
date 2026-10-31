import type { Flow, Leg, Results } from "@/lib/types";
import { LEG_STYLE } from "@/lib/legs";
import { num, usdM } from "@/lib/format";

// Truck rates given in the organisers' brief (USD per tonne-km); shown here as text only.
const BRIEF_RATES: Record<Leg, string> = {
  farm_depot: "$0.10",
  depot_refinery: "$0.12",
  refinery_airport: "$0.08",
};

const h = "text-xs font-medium uppercase tracking-wide text-slate-500";
const p = "text-sm leading-relaxed text-slate-700";

/** Tonne-weighted average km and total cost of one leg. */
function legStats(flows: Flow[], leg: Leg) {
  const f = flows.filter((x) => x.leg === leg);
  const t = f.reduce((s, x) => s + x.tonnes, 0);
  return { km: t ? f.reduce((s, x) => s + x.tonnes * x.distanceKm, 0) / t : 0, cost: f.reduce((s, x) => s + x.cost, 0), kt: t / 1000 };
}

/** Plain-language reading of one refinery-mix result from the search log. */
function mixResult(result: string): string {
  if (result === "Optimal") return "solved: best layout for this mix found and proven";
  if (result.startsWith("Feasible")) return "solved until the time limit: good layout found, not fully proven";
  if (result === "ruled out") return "skipped: its refinery cost alone is higher than the best plan found";
  if (result.startsWith("not needed")) return "skipped: the best plan was already proven close enough";
  if (result.startsWith("not reached")) return "not reached before the time limit (counted by its cost floor)";
  return result;
}

/** "How it works" tab: how the solver chooses sites, sizes and routes, with the current plan's numbers. */
export default function HowItWorks({ data }: { data: Results }) {
  const m = data.meta;
  const isBaseline = (m?.scenario ?? "optimised") !== "optimised";
  const assume = (id: string) => m?.assumptions?.find((a) => a.ID === id)?.Value;
  const offshore = data.farms.filter((f) => f.offshore).length;
  const usedSites = new Set(data.flows.filter((f) => f.leg === "farm_depot").map((f) => f.from)).size;
  const legs = (Object.keys(LEG_STYLE) as Leg[]).map((leg) => ({ leg, ...legStats(data.flows, leg) }));
  const trucking = legs.reduce((s, l) => s + l.cost, 0) || 1;
  const refineries = data.refineries.map((r) => r.site ?? r.id).join(" and ");

  return (
    <div className="max-h-[640px] space-y-6 overflow-y-auto pr-1">
      {isBaseline && (
        <p className="border-l-2 border-amber-500 bg-amber-50 p-3 text-sm text-amber-900">
          The plan on the map is a <b>rule-of-thumb baseline</b>, not the solver&apos;s answer. It follows a fixed rule (
          {m?.scenario === "b1" ? "one central refinery at the middle of all the biomass" : "a refinery at every airport"}) and
          exists to show what the optimised plan saves. The steps below describe how the optimised plan is chosen.
        </p>
      )}

      <section className="space-y-2">
        <h3 className={h}>1 · What the solver decides</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>Where to build depots and refineries, and how many Small and Large units at each place.</li>
          <li>Which biomass sites to use, and how much from each (it only takes what the airports need).</li>
          <li>Which depot each biomass site trucks to, which refinery each depot trucks to, and which refinery supplies each airport.</li>
        </ul>
        <p className={p}>
          It decides all of these together in one model, so a refinery&apos;s location is chosen with its supply routes in mind.
        </p>
      </section>

      <section className="space-y-2">
        <h3 className={h}>2 · What it is trying to make as small as possible</h3>
        <p className={p}>
          <b>Total cost per year</b> = building cost spread over the plant life + fixed running cost + running cost per tonne + transport cost.
        </p>
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>
            <b>Building cost</b> (refineries $480M–$765M each, depots $2.25M–$4.5M) is spread over the years:{" "}
            {assume("A8") ?? "straight-line over 20 years, no interest"}.
          </li>
          <li>
            <b>Fixed running cost:</b> {assume("A7") ?? "5% of CapEx per year"}.
          </li>
          <li>
            <b>Running cost per tonne:</b> {assume("A7b") ?? "depots $5 Small / $4 Large, refineries $60 Small / $55 Large"}.
          </li>
          <li>
            <b>Transport:</b> tonnes × km × the brief&apos;s rate for that leg (barge to Tarakan at the truck rate) (
            {legs.map((l, i) => (
              <span key={l.leg}>
                {i > 0 && ", "}
                {LEG_STYLE[l.leg].label.toLowerCase()} {BRIEF_RATES[l.leg]}/t·km
              </span>
            ))}
            ).
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <h3 className={h}>3 · Rules every plan must follow</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>Each airport receives at least its SAF demand.</li>
          <li>No biomass site sends more than it produces.</li>
          <li>No depot or refinery takes in more biomass than its capacity (Small or Large, as given in the brief).</li>
          <li>
            Mass is conserved: depots pass biomass through; refineries turn biomass into SAF at{" "}
            {assume("A3") ?? "0.2 t SAF per t biomass"}.
          </li>
          <li>Facilities per site: {assume("A10") ?? "≤ 4 depots, ≤ 2 refineries"}.</li>
          <li>Nothing is built at the {offshore} biomass sites that sit in the sea; their biomass can still be used.</li>
        </ul>
      </section>

      <section className="space-y-2">
        <h3 className={h}>4 · How it picks the places</h3>
        <p className={p}>
          Facilities can only go on a list of candidate spots: every biomass site on land, the centres of 20 biomass clusters
          (any centre in the sea is dropped), and the 4 airports (refineries only). The solver compares every combination of
          these spots and keeps the cheapest.
        </p>
        {!isBaseline && data.refineries.length > 0 && (
          <p className={p}>
            In this plan it built refineries at <b>{refineries}</b>. Two effects of the brief&apos;s numbers explain the shape:
          </p>
        )}
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>
            <b>Refineries sit near the biomass, not near the airports.</b> A refinery turns 5 t of biomass into 1 t of SAF, so
            moving biomass far costs more than moving SAF far.
          </li>
          <li>
            <b>Depots sit next to refineries.</b> Depots don&apos;t reduce weight, and depot → refinery trucking ($0.12) costs
            more than biomass → depot ($0.10), so the cheapest place to pre-process is at the refinery.
            {!isBaseline && <> Here, biomass travels on average <b>{num(legs[1].km)} km</b> from depot to refinery.</>}
          </li>
          <li>
            <b>Large refineries are cheaper per tonne</b> to build ($704k vs $960k per kt of capacity) and to run ($55 vs $60
            per tonne of biomass), but one big site means longer trucking. The solver weighs both.
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <h3 className={h}>5 · How it picks the routes</h3>
        <p className={p}>
          Every possible route uses the organisers&apos; distance rule: great-circle distance × 1.3. The solver chooses how many tonnes go on each route, so biomass flows to whichever depot
          and refinery give the lowest total cost without breaking a capacity limit. The arrows on the map show the direction
          the trucks drive.
        </p>
        <div className="overflow-x-auto border border-slate-200">
          <table className="w-full text-sm">
            <caption className="sr-only">Trucking in this plan by leg</caption>
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                <th scope="col" className="px-3 py-2 font-medium">Leg</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">kt/yr</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Avg km</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Share of trucking</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {legs.map((l) => (
                <tr key={l.leg}>
                  <td className="px-3 py-2 text-slate-700">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-0.5 w-3" style={{ background: LEG_STYLE[l.leg].color }} aria-hidden />
                      {LEG_STYLE[l.leg].label}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-700">{num(l.kt)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-700">{num(l.km)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-700">{num((100 * l.cost) / trucking)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-slate-500">
          {num(usedSites)} of {data.farms.length} biomass sites are used; trucking totals {usdM(trucking)} a year.
        </p>
      </section>

      <section className="space-y-2">
        <h3 className={h}>6 · How it searches</h3>
        <p className={p}>
          This is an exact optimisation (a mixed-integer linear program, solved by {m?.solver ?? "HiGHS"}), not a rule of thumb
          or AI guess. Because refineries come in a few very expensive units, the search is split by refinery mix: each mix is
          either solved, or skipped once its building cost alone is higher than the best plan found.
        </p>
        {!!m?.mixSearch?.length && (
          <ul className="space-y-1 text-sm text-slate-700">
            {m.mixSearch.map((r) => (
              <li key={r.mix} className="flex gap-2">
                <span className="w-36 shrink-0 font-medium text-slate-900">{r.mix}</span>
                <span>{mixResult(r.result)}</span>
              </li>
            ))}
          </ul>
        )}
        <p className={p}>
          Result: <b>{m?.optimisedStatus ?? m?.status}</b>
          {(m?.optimisedGap ?? m?.gap) != null && (
            <>
              , proven within <b>{(((m?.optimisedGap ?? m?.gap) as number) * 100).toFixed(2)}%</b> of the cheapest possible plan
            </>
          )}
          .
        </p>
      </section>

      <section className="space-y-2">
        <h3 className={h}>7 · How you can check it</h3>
        <p className={p}>
          A separate checker, which shares no code with the solver, reloads the saved plan and recomputes every rule and the
          total cost: {m?.checksPassed ?? 0} of {m?.checksTotal ?? 0} checks pass (see the Checks tab). The Baselines tab
          compares the plan with two rule-of-thumb plans scored by the same cost function, and the Assumptions tab lists every
          number the brief did not give.
        </p>
      </section>
    </div>
  );
}
