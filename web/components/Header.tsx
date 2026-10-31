"use client";

import { useState } from "react";
import { ChevronDown, Download, Search, X } from "lucide-react";
import type { ScenarioOption } from "@/lib/types";

interface HeaderProps {
  scenarios: ScenarioOption[];
  scenarioId: string;
  onScenarioChange: (id: string) => void;
  /** URL of the JSON currently shown, offered as a download. */
  file: string;
  query: string;
  onQueryChange: (q: string) => void;
  /** One factual line under the title, e.g. demand and solver status. */
  subtitle?: string;
}

/** Page title plus search, scenario selector and download pills. */
export default function Header(p: HeaderProps) {
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <header className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 sm:text-2xl">
          SAF Supply Chain Report: Kalimantan
        </h1>
        {p.subtitle && <p className="mt-1 text-sm text-slate-500">{p.subtitle}</p>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {/* Search filters the facility and flow tables by ID. */}
        {searchOpen ? (
          <div className="flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white pl-3 pr-1">
            <Search className="h-4 w-4 text-slate-400" aria-hidden />
            <label htmlFor="table-search" className="sr-only">
              Filter tables by site ID
            </label>
            <input
              id="table-search"
              autoFocus
              value={p.query}
              onChange={(e) => p.onQueryChange(e.target.value)}
              placeholder="Filter by site ID"
              className="w-40 bg-transparent text-sm outline-none placeholder:text-slate-400"
            />
            <button
              type="button"
              aria-label="Close search"
              onClick={() => {
                p.onQueryChange("");
                setSearchOpen(false);
              }}
              className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>
        ) : (
          <button
            type="button"
            aria-label="Search tables"
            onClick={() => setSearchOpen(true)}
            className="grid h-9 w-9 place-items-center rounded-md text-slate-600 hover:bg-slate-100"
          >
            <Search className="h-5 w-5" aria-hidden />
          </button>
        )}

        {/* Scenario selector: each option loads a different JSON file. */}
        <div className="relative">
          <label htmlFor="scenario" className="sr-only">
            Scenario
          </label>
          <select
            id="scenario"
            value={p.scenarioId}
            onChange={(e) => p.onScenarioChange(e.target.value)}
            className="h-9 appearance-none rounded-md border border-slate-200 bg-white pl-4 pr-9 text-sm font-medium text-slate-700 hover:border-slate-400"
          >
            {p.scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <ChevronDown
            className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
            aria-hidden
          />
        </div>

        <a
          href={p.file}
          download
          className="flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 hover:border-slate-400"
        >
          <Download className="h-4 w-4" aria-hidden />
          Download data
        </a>
      </div>
    </header>
  );
}
