"use client";

import dynamic from "next/dynamic";

// Leaflet needs `window`, so the map is only ever rendered in the browser.
const NetworkMap = dynamic(() => import("./NetworkMap"), {
  ssr: false,
  loading: () => (
    <div className="grid h-full min-h-[420px] place-items-center rounded-lg border border-line bg-white text-sm text-ink-2">
      Loading map…
    </div>
  ),
});

export default NetworkMap;
