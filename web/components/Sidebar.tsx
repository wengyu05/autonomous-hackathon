"use client";

import { useState } from "react";
import { Factory, LayoutDashboard, Map, PieChart, Route, type LucideIcon } from "lucide-react";

interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
}

// Each item jumps to a section of the single-page report.
const NAV: NavItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "network", label: "Network map", icon: Map },
  { id: "costs", label: "Cost breakdown", icon: PieChart },
  { id: "facilities", label: "Facilities", icon: Factory },
  { id: "flows", label: "Flows", icon: Route },
];

/**
 * Narrow icon rail. On md+ screens it sits on the left; on mobile it becomes a
 * horizontal bar above the content.
 */
export default function Sidebar() {
  const [active, setActive] = useState("overview");

  return (
    <nav
      aria-label="Main"
      className="flex shrink-0 items-center gap-4 border-b border-slate-200 px-4 py-2 md:sticky md:top-0 md:h-screen md:w-16 md:flex-col md:border-b-0 md:border-r md:px-0 md:py-5"
    >
      <span className="text-sm font-bold tracking-wide text-brand">SAF</span>
      <div className="flex items-center gap-1 overflow-x-auto md:mt-6 md:flex-col">
        {NAV.map(({ id, label, icon: Icon }) => (
          <a
            key={id}
            href={`#${id}`}
            onClick={() => setActive(id)}
            aria-label={label}
            aria-current={active === id ? "page" : undefined}
            title={label}
            className={`grid h-10 w-10 place-items-center rounded-md ${
              active === id ? "bg-slate-100 text-slate-900" : "text-slate-400 hover:text-slate-700"
            }`}
          >
            <Icon className="h-[18px] w-[18px]" aria-hidden />
          </a>
        ))}
      </div>
    </nav>
  );
}
