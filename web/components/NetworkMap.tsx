"use client";

// Leaflet touches `window`, so this file must only be loaded through
// next/dynamic({ ssr: false }); see NetworkMapLoader.tsx.
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useMemo, useState } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { Minus, Plus } from "lucide-react";
import type { Airport, Facility, Flow, Leg, Results } from "@/lib/types";
import { LEG_STYLE } from "@/lib/legs";
import { coords, num } from "@/lib/format";

const KALIMANTAN_CENTER: [number, number] = [-0.6, 113.6];

// lucide "plane" path, inlined because Leaflet divIcons take an HTML string.
const PLANE_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/></svg>';

type LayerKey = "farms" | "depots" | "refineries" | "airports" | "flows";

const LAYERS: { key: LayerKey; label: string; swatch: string }[] = [
  { key: "farms", label: "Biomass sites", swatch: "h-2.5 w-2.5 rounded-full bg-slate-400" },
  { key: "depots", label: "Depots", swatch: "h-2.5 w-2.5 bg-green-700" },
  { key: "refineries", label: "Refineries", swatch: "h-3 w-3 rounded-full bg-green-900" },
  { key: "airports", label: "Airports", swatch: "h-3 w-3 rounded-sm bg-[#1e3a5f]" },
  { key: "flows", label: "Flows", swatch: "h-0.5 w-4 bg-slate-600" },
];

interface NetworkMapProps {
  data: Results;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

/** Tooltip body shared by depots and refineries. */
function FacilityTip({ f, kind }: { f: Facility; kind: "Depot" | "Refinery" }) {
  return (
    <div className="space-y-0.5 text-xs">
      <p className="text-sm font-semibold">
        {kind} at {f.site ?? f.id}
      </p>
      <p className="text-slate-500">{coords(f.lat, f.lng)}</p>
      <p>
        Size: <b>{f.units ?? f.size}</b> · capacity {num(f.capacityKt)} kt{kind === "Refinery" ? " SAF/yr" : " biomass/yr"}
      </p>
      <p>
        Throughput: <b>{num(f.throughputKt, 1)} kt</b> biomass in
        {kind === "Refinery" && f.outputKt != null && <> · {num(f.outputKt, 1)} kt SAF out</>}
      </p>
      {f.utilisationPct != null && (
        <p>
          Utilisation: <b>{num(f.utilisationPct)}%</b>
        </p>
      )}
          </div>
  );
}

/** Custom +/- buttons at the bottom right, styled to match the dashboard. */
function ZoomButtons() {
  const map = useMap();
  const btn = "grid h-9 w-9 place-items-center bg-white text-slate-700 hover:bg-slate-50";
  return (
    <div className="absolute bottom-4 right-4 z-[1000] flex flex-col overflow-hidden rounded border border-slate-300">
      <button type="button" aria-label="Zoom in" className={btn} onClick={() => map.zoomIn()}>
        <Plus className="h-4 w-4" aria-hidden />
      </button>
      <span className="h-px bg-slate-200" aria-hidden />
      <button type="button" aria-label="Zoom out" className={btn} onClick={() => map.zoomOut()}>
        <Minus className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}

/** Clicking empty map clears the selection. */
function ClearOnMapClick({ onClear }: { onClear: () => void }) {
  useMapEvents({ click: onClear });
  return null;
}

export default function NetworkMap({ data, selectedId, onSelect }: NetworkMapProps) {
  const [visible, setVisible] = useState<Record<LayerKey, boolean>>({
    farms: true,
    depots: true,
    refineries: true,
    airports: true,
    flows: true,
  });

  // id -> [lat, lng] for every node, for flows that carry no road path.
  const nodes = useMemo(() => {
    const m = new Map<string, [number, number]>();
    for (const n of [...data.farms, ...data.depots, ...data.refineries, ...data.airports]) m.set(n.id, [n.lat, n.lng]);
    return m;
  }, [data]);

  // Line width scales with tonnage, relative to the busiest flow on the same leg.
  const maxByLeg = useMemo(() => {
    const m: Record<Leg, number> = { farm_depot: 1, depot_refinery: 1, refinery_airport: 1 };
    for (const f of data.flows) m[f.leg] = Math.max(m[f.leg], f.tonnes);
    return m;
  }, [data]);

  const maxSupply = useMemo(() => Math.max(1, ...data.farms.map((f) => f.supplyKt)), [data]);

  const isConnected = (f: Flow) => selectedId != null && (f.from === selectedId || f.to === selectedId);

  // Highlighted flows go last so they draw on top of the rest.
  const orderedFlows = data.flows
    .map((f, i) => ({ f, i, on: isConnected(f) }))
    .sort((a, b) => Number(a.on) - Number(b.on));

  const select = (id: string) => ({
    click: (e: L.LeafletMouseEvent) => {
      L.DomEvent.stopPropagation(e);
      onSelect(selectedId === id ? null : id);
    },
  });

  const squareIcon = (cls: string, s: number) =>
    L.divIcon({ className: "", html: `<div class="${cls}" style="width:${s}px;height:${s}px"></div>`, iconSize: [s, s] });

  const depotIcon = (d: Facility) =>
    squareIcon(`marker-depot${selectedId === d.id ? " is-selected" : ""}`, d.size === "Large" ? 11 : 8);

  const refineryIcon = (r: Facility) =>
    squareIcon(`marker-refinery${selectedId === r.id ? " is-selected" : ""}`, r.size === "Large" ? 18 : 14);

  const airportIcon = (a: Airport) =>
    L.divIcon({
      className: "",
      html: `<div class="marker-airport${selectedId === a.id ? " is-selected" : ""}"><span class="pin">${PLANE_SVG}</span><span class="label">${a.name}</span></div>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    });

  return (
    <div className="relative h-full min-h-[420px] overflow-hidden border border-slate-200">
      <MapContainer
        center={KALIMANTAN_CENTER}
        zoom={6}
        minZoom={5}
        zoomControl={false}
        scrollWheelZoom={false}
        className="h-full w-full"
        aria-label="Map of the SAF supply network in Kalimantan"
      >
        {/* Esri light-grey canvas: minimal, keyless basemap, with place names on a separate layer. */}
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
          attribution="Tiles &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors · routes: OSRM"
          maxNativeZoom={16}
        />
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
          maxNativeZoom={16}
        />
        <ClearOnMapClick onClear={() => onSelect(null)} />

        {visible.flows &&
          orderedFlows.map(({ f, i, on }) => {
            const a = nodes.get(f.from);
            const b = nodes.get(f.to);
            if (!a || !b || f.distanceKm === 0) return null; // co-located legs have nothing to draw
            const dim = selectedId != null && !on;
            const weight = 1 + 4.5 * Math.sqrt(f.tonnes / maxByLeg[f.leg]);
            return (
              <Polyline
                // Key includes the highlight state so Leaflet re-orders the line when it changes.
                key={`${i}-${on}`}
                positions={f.path ?? [a, b]}
                pathOptions={{
                  color: LEG_STYLE[f.leg].color,
                  weight: on ? weight + 2 : weight,
                  opacity: dim ? 0.08 : on ? 0.95 : 0.7,
                  lineCap: "round",
                  lineJoin: "round",
                }}
              >
                <Tooltip sticky className="saf-tooltip">
                  <div className="space-y-0.5 text-xs">
                    <p className="font-semibold">{LEG_STYLE[f.leg].label}</p>
                    <p>
                      {f.from} → {f.to}
                    </p>
                    <p>
                      {num(f.tonnes)} t/yr · {num(f.distanceKm)} road km · ${num(f.cost)}/yr
                    </p>
                  </div>
                </Tooltip>
              </Polyline>
            );
          })}

        {visible.farms &&
          data.farms.map((f) => (
            <CircleMarker
              key={f.id}
              center={[f.lat, f.lng]}
              radius={2.5 + 5 * Math.sqrt(f.supplyKt / maxSupply)}
              pathOptions={{
                color: selectedId === f.id ? "#334155" : "#ffffff",
                weight: selectedId === f.id ? 2 : 1,
                fillColor: "#a8a29e",
                fillOpacity: 0.9,
              }}
              eventHandlers={select(f.id)}
            >
              <Tooltip className="saf-tooltip">
                <div className="space-y-0.5 text-xs">
                  <p className="text-sm font-semibold">Biomass site {f.id}</p>
                  {f.name && <p>{f.name}</p>}
                  <p className="text-slate-500">{coords(f.lat, f.lng)}</p>
                  <p>
                    Supply: <b>{num(f.supplyKt, 1)} kt/yr</b>
                  </p>
                </div>
              </Tooltip>
            </CircleMarker>
          ))}

        {visible.depots &&
          data.depots.map((d) => (
            <Marker
              key={`${d.id}-${selectedId === d.id}`}
              position={[d.lat, d.lng]}
              icon={depotIcon(d)}
              eventHandlers={select(d.id)}
              title={`Depot at ${d.site ?? d.id}`}
              alt={`Depot at ${d.site ?? d.id}`}
            >
              <Tooltip className="saf-tooltip">
                <FacilityTip f={d} kind="Depot" />
              </Tooltip>
            </Marker>
          ))}

        {visible.refineries &&
          data.refineries.map((r) => (
            <Marker
              key={`${r.id}-${selectedId === r.id}`}
              position={[r.lat, r.lng]}
              icon={refineryIcon(r)}
              eventHandlers={select(r.id)}
              zIndexOffset={500}
              title={`Refinery at ${r.site ?? r.id}`}
              alt={`Refinery at ${r.site ?? r.id}`}
            >
              <Tooltip className="saf-tooltip">
                <FacilityTip f={r} kind="Refinery" />
              </Tooltip>
            </Marker>
          ))}

        {visible.airports &&
          data.airports.map((a) => (
            <Marker
              key={`${a.id}-${selectedId === a.id}`}
              position={[a.lat, a.lng]}
              icon={airportIcon(a)}
              eventHandlers={select(a.id)}
              zIndexOffset={1000}
              title={a.name}
              alt={a.name}
            >
              <Tooltip className="saf-tooltip" direction="top" offset={[0, -11]}>
                <div className="space-y-0.5 text-xs">
                  <p className="text-sm font-semibold">
                    {a.name} ({a.id})
                  </p>
                  <p className="text-slate-500">{coords(a.lat, a.lng)}</p>
                  <p>
                    Delivered: <b>{num(a.deliveredKt, 1)} kt</b> of {num(a.demandKt)} kt demand
                  </p>
                </div>
              </Tooltip>
            </Marker>
          ))}

        <ZoomButtons />
      </MapContainer>

      {/* Flow colour key, top left. */}
      <div className="pointer-events-none absolute left-4 top-4 z-[1000] space-y-1 rounded bg-white/95 px-2.5 py-2 text-[11px] text-slate-600 ring-1 ring-slate-200">
        {Object.values(LEG_STYLE).map((s) => (
          <p key={s.label} className="flex items-center gap-2">
            <span className="h-0.5 w-5" style={{ background: s.color }} aria-hidden />
            {s.label}
          </p>
        ))}
        <p className="pt-0.5 text-slate-500">Line width ∝ tonnes</p>
      </div>

      {/* Toggleable legend pill, bottom left. */}
      <div
        role="group"
        aria-label="Map layers"
        className="absolute bottom-4 left-4 z-[1000] flex max-w-[calc(100%-5.5rem)] flex-wrap items-center gap-0.5 rounded bg-white/95 p-1 ring-1 ring-slate-200"
      >
        {LAYERS.map((l) => (
          <button
            key={l.key}
            type="button"
            aria-pressed={visible[l.key]}
            onClick={() => setVisible((v) => ({ ...v, [l.key]: !v[l.key] }))}
            className={`flex items-center gap-1.5 rounded-sm px-2 py-1 text-xs ${
              visible[l.key] ? "text-slate-800" : "text-slate-400 line-through"
            }`}
          >
            <span className={l.swatch} aria-hidden />
            {l.label}
          </button>
        ))}
      </div>
    </div>
  );
}
