"use client";

import { useEffect, useState } from "react";
import type { Distances, Results, ScenarioOption } from "./types";

/** Each distance mode's plans live in their own folder, written by src/export_web.py. */
const BASE: Record<Distances, string> = { official: "/data", roads: "/data/roads" };

// Fallback when scenarios.json is missing: just the default results file.
const defaultScenarios = (d: Distances): ScenarioOption[] => [
  { id: "optimised", label: "Optimised plan", file: `${BASE[d]}/results.json` },
];

/**
 * Loads the scenario list for the chosen distance mode, then the selected scenario's JSON whenever
 * either choice changes. `reload()` fetches the files again, e.g. after a solve has rewritten them.
 */
export function useResults(distances: Distances) {
  const DEFAULT_SCENARIOS = defaultScenarios(distances);
  const [scenarios, setScenarios] = useState<ScenarioOption[]>(DEFAULT_SCENARIOS);
  const [scenarioId, setScenarioId] = useState(DEFAULT_SCENARIOS[0].id);
  const [data, setData] = useState<Results | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  // Switching distance mode keeps the plan choice (optimised, b1, b2): both modes have the same three.
  useEffect(() => {
    const fallback = defaultScenarios(distances);
    fetch(`${BASE[distances]}/scenarios.json`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : fallback))
      .then((list: ScenarioOption[]) => setScenarios(list.length ? list : fallback))
      .catch(() => setScenarios(fallback));
  }, [distances, version]);

  const file = scenarios.find((s) => s.id === scenarioId)?.file ?? DEFAULT_SCENARIOS[0].file;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(version ? `${file}?v=${version}` : file, { cache: "no-store" })
      .then((r) => {
        if (!r.ok)
          throw new Error(
            distances === "roads"
              ? "No real-road plan saved yet. Build one with: .venv/bin/python -m src.pipeline --distances roads"
              : `Could not load ${file} (HTTP ${r.status})`,
          );
        return r.json();
      })
      .then((d: Results) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setData(null); // never show the other mode's plan under this mode's label
        setError(e.message);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [file, version, distances]);

  const reload = () => setVersion((v) => v + 1);
  return { scenarios, scenarioId, setScenarioId, data, error, loading, file, reload };
}
