"use client";

import { useEffect, useState } from "react";
import type { Results, ScenarioOption } from "./types";

// Fallback when scenarios.json is missing: just the default results file.
const DEFAULT_SCENARIOS: ScenarioOption[] = [{ id: "optimised", label: "Optimised plan", file: "/data/results.json" }];

/**
 * Loads the scenario list once, then the selected scenario's JSON whenever the choice changes.
 * `reload()` fetches the files again, e.g. after a solve has rewritten them.
 */
export function useResults() {
  const [scenarios, setScenarios] = useState<ScenarioOption[]>(DEFAULT_SCENARIOS);
  const [scenarioId, setScenarioId] = useState(DEFAULT_SCENARIOS[0].id);
  const [data, setData] = useState<Results | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    fetch("/data/scenarios.json")
      .then((r) => (r.ok ? r.json() : DEFAULT_SCENARIOS))
      .then((list: ScenarioOption[]) => {
        if (list.length) {
          setScenarios(list);
          setScenarioId(list[0].id);
        }
      })
      .catch(() => setScenarios(DEFAULT_SCENARIOS));
  }, []);

  const file = scenarios.find((s) => s.id === scenarioId)?.file ?? DEFAULT_SCENARIOS[0].file;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(version ? `${file}?v=${version}` : file, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`Could not load ${file} (HTTP ${r.status})`);
        return r.json();
      })
      .then((d: Results) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [file, version]);

  const reload = () => setVersion((v) => v + 1);
  return { scenarios, scenarioId, setScenarioId, data, error, loading, file, reload };
}
