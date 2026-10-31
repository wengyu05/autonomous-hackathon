// Client for the FastAPI solver backend (api.py at the project root).

import type { Distances } from "./types";

/** Where api.py runs. Override with NEXT_PUBLIC_API_URL. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const START_COMMAND = ".venv/bin/uvicorn api:app --port 8000";

/** True when the backend answers /api/health. */
export async function solverOnline(): Promise<boolean> {
  try {
    const r = await fetch(`${API_URL}/api/health`, { cache: "no-store" });
    return r.ok;
  } catch {
    return false;
  }
}

/**
 * Re-plans for new airport demand. The backend writes outputs/, reruns the baselines and the
 * independent checks, fetches road shapes for new routes, and rewrites web/public/data/*.json,
 * so the caller only needs to reload those files. Throws with the backend's message on failure.
 */
export async function solve(demandKt: Record<string, number>, timeLimitS: number, distances: Distances): Promise<void> {
  let r: Response;
  try {
    r = await fetch(`${API_URL}/api/solve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ demandKt, timeLimitS, distances, fetchRoutes: true, writeStatic: true }),
    });
  } catch {
    throw new Error(`The solver is offline. Start it from the project folder with: ${START_COMMAND}`);
  }
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    throw new Error(body?.detail ?? `The solver returned HTTP ${r.status}.`);
  }
}
