"use client";

// Leaflet touches `window`, so this file must only be loaded through
// next/dynamic({ ssr: false }); see NetworkMapLoader.tsx.
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { Fragment, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMapEvents } from "react-leaflet";
import type { Facility, Flow, Leg, Results } from "@/lib/types";
import { LEG_STYLE } from "@/lib/legs";
import { coords, num } from "@/lib/format";

const KALIMANTAN_CENTER: [number, number] = [-0.5, 113.4];
const INK = "#0b0b0b";
const INK_2 = "#52514e";
const CRITICAL = "#d03b2f";
/** One direction arrow per this many km of route, and at least one per route. */
const ARROW_SPACING_KM = 120;

type LayerKey = Leg | "farms" | "depots" | "refineries" | "airports";

// Same groups as the Streamlit map's layer control.
const LAYERS: { key: LayerKey; label: string }[] = [
  { key: "farm_depot", label: `Routes: ${LEG_STYLE.farm_depot.label}` },
  { key: "depot_refinery", label: `Routes: ${LEG_STYLE.depot_refinery.label}` },
  { key: "refinery_airport", label: `Routes: ${LEG_STYLE.refinery_airport.label}` },
  { key: "farms", label: "Biomass sites (80)" },
  { key: "depots", label: "Depots" },
  { key: "refineries", label: "Refineries" },
  { key: "airports", label: "Airports (4)" },
];

interface NetworkMapProps {
  data: Results;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

/** Site name without the D-/R- prefix the JSON uses for depot and refinery IDs. */
const siteOf = (id: string) => id.replace(/^[DR]-/, "");

/** "1 Large + 1 Small" -> 2. */
function unitCount(units?: string): number {
  return [...(units ?? "").matchAll(/(\d+)\s+(Small|Large)/g)].reduce((t, m) => t + Number(m[1]), 0) || 1;
}

function km(a: [number, number], b: [number, number]): number {
  const r = Math.PI / 180;
  const h = Math.sin(((b[0] - a[0]) * r) / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(((b[1] - a[1]) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}

/** Screen heading (degrees clockwise from north) of a segment on a Web Mercator map. */
function heading(a: [number, number], b: [number, number]): number {
  const y = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
  return (Math.atan2(((b[1] - a[1]) * Math.PI) / 180, y(b[0]) - y(a[0])) * 180) / Math.PI;
}

/** Evenly spaced points along a path, each with the direction of travel at that point. */
function arrowsAlong(path: [number, number][]): { at: [number, number]; deg: number }[] {
  const seg = path.slice(1).map((p, i) => km(path[i], p));
  const total = seg.reduce((t, d) => t + d, 0);
  if (total < 1) return [];
  const n = Math.max(1, Math.floor(total / ARROW_SPACING_KM));
  const out: { at: [number, number]; deg: number }[] = [];
  for (let k = 0; k < n; k++) {
    let want = ((k + 0.5) * total) / n;
    let i = 0;
    while (i < seg.length - 1 && want > seg[i]) want -= seg[i++];
    const t = seg[i] > 0 ? want / seg[i] : 0;
    const [a, b] = [path[i], path[i + 1]];
    out.push({ at: [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])], deg: heading(a, b) });
  }
  return out;
}

/** Folium-style map pin: a coloured teardrop with a white Font Awesome icon. `dx` shifts it sideways in pixels. */
const pinIcon = (colour: "gray" | "black" | "red", icon: string, selected: boolean, dx = 0) =>
  L.divIcon({
    className: "",
    html: `<div class="pin-marker pin-${colour}${selected ? " is-selected" : ""}"><i class="fa fa-${icon}"></i></div>`,
    iconSize: [30, 30],
    iconAnchor: [15 - dx, 36],
  });

/** A refinery built at an airport shares its coordinates; its pin moves left so the airport pin doesn't hide it. */
const AT_AIRPORT_DX = -17;

const arrowIcon = (colour: string, deg: number) =>
  L.divIcon({
    className: "",
    html: `<div class="route-arrow" style="color:${colour};transform:rotate(${deg.toFixed(1)}deg)"></div>`,
    iconSize: [10, 9],
    iconAnchor: [5, 4.5],
  });

function FacilityTip({ f, kind }: { f: Facility; kind: "Depot" | "Refinery" }) {
  return (
    <>
      <b>
        {kind} · {f.site ?? siteOf(f.id)}
      </b>
      <br />
      {f.units ?? f.size} ({num(f.capacityKt)} kt{kind === "Refinery" ? " capacity" : ""})
      <br />
      {kind === "Refinery" ? (
        <>
          {num(f.throughputKt, 1)} kt biomass in → {num(f.outputKt ?? 0, 1)} kt SAF
          <br />
          {num(f.utilisationPct ?? 0)}% used
        </>
      ) : (
        <>
          {num(f.throughputKt, 1)} kt in · {num(f.utilisationPct ?? 0)}% used
        </>
      )}
      <br />
      {coords(f.lat, f.lng)}
    </>
  );
}

/** Clicking empty map clears the selection. */
function ClearOnMapClick({ onClear }: { onClear: () => void }) {
  useMapEvents({ click: onClear });
  return null;
}

export default function NetworkMap({ data, selectedId, onSelect }: NetworkMapProps) {
  const [visible, setVisible] = useState<Record<LayerKey, boolean>>(
    Object.fromEntries(LAYERS.map((l) => [l.key, true])) as Record<LayerKey, boolean>,
  );
  const [layersOpen, setLayersOpen] = useState(false);

  // id -> [lat, lng] for every node, for flows that carry no road path.
  const nodes = useMemo(() => {
    const m = new Map<string, [number, number]>();
    for (const n of [...data.farms, ...data.depots, ...data.refineries, ...data.airports]) m.set(n.id, [n.lat, n.lng]);
    return m;
  }, [data]);

  // As in the Streamlit map: line width scales with kt against the busiest flow on any leg.
  const maxTonnes = useMemo(() => Math.max(1, ...data.flows.map((f) => f.tonnes)), [data]);

  const used = useMemo(() => {
    const m = new Map<string, number>();
    for (const f of data.flows) if (f.leg === "farm_depot") m.set(f.from, (m.get(f.from) ?? 0) + f.tonnes / 1000);
    return m;
  }, [data]);

  const delivered = useMemo(() => new Map(data.airports.map((a) => [a.id, a.deliveredKt])), [data]);

  const routes = useMemo(
    () =>
      data.flows
        .map((f, i) => {
          const a = nodes.get(f.from);
          const b = nodes.get(f.to);
          if (!a || !b || f.distanceKm === 0) return null; // co-located: no truck leg to draw
          const path = f.path ?? [a, b];
          return { f, i, path, arrows: arrowsAlong(path) };
        })
        .filter((r): r is { f: Flow; i: number; path: [number, number][]; arrows: { at: [number, number]; deg: number }[] } => r !== null),
    [data, nodes],
  );

  const isConnected = (f: Flow) => selectedId != null && (f.from === selectedId || f.to === selectedId);
  const select = (id: string) => ({
    click: (e: L.LeafletMouseEvent) => {
      L.DomEvent.stopPropagation(e);
      onSelect(selectedId === id ? null : id);
    },
  });

  return (
    <div className="relative h-full w-full overflow-hidden border border-slate-200">
      <MapContainer center={KALIMANTAN_CENTER} zoom={6} minZoom={4} className="h-full w-full" aria-label="Map of the SAF supply network in Kalimantan">
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution={`&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors${data.flows.some((f) => f.path) ? " · routes: OSRM" : ""}`}
          maxZoom={19}
        />
        <ClearOnMapClick onClear={() => onSelect(null)} />

        {routes.map(({ f, i, path, arrows }) => {
          if (!visible[f.leg]) return null;
          const { color, label } = LEG_STYLE[f.leg];
          const on = isConnected(f);
          const dim = selectedId != null && !on;
          const weight = 1.5 + 6 * Math.sqrt(f.tonnes / maxTonnes);
          return (
            <Fragment key={`${i}-${on}`}>
              <Polyline positions={path} pathOptions={{ color, weight: on ? weight + 2 : weight, opacity: dim ? 0.1 : 0.8 }}>
                <Tooltip sticky className="saf-tooltip">
                  <b>{label}</b>
                  <br />
                  {siteOf(f.from)} → {siteOf(f.to)}
                  <br />
                  {num(f.tonnes / 1000, 1)} kt/yr · {num(f.distanceKm)} km
                  <br />${num(f.cost / 1e6, 2)}M/yr · {num(f.trucksLarge ?? 0)} large-truck trips/yr
                </Tooltip>
              </Polyline>
              {!dim &&
                arrows.map((a, k) => (
                  <Marker key={k} position={a.at} icon={arrowIcon(color, a.deg)} interactive={false} keyboard={false} />
                ))}
            </Fragment>
          );
        })}

        {visible.farms &&
          data.farms.map((s) => {
            const u = used.get(s.id) ?? 0;
            return (
              <CircleMarker
                key={s.id}
                center={[s.lat, s.lng]}
                radius={3 + Math.sqrt(s.supplyKt) * 0.55}
                pathOptions={{
                  color: s.offshore ? CRITICAL : INK_2,
                  weight: s.offshore ? 2 : 1,
                  fillColor: INK_2,
                  fillOpacity: u > 0 ? 0.85 : 0.12,
                }}
                eventHandlers={select(s.id)}
              >
                <Tooltip className="saf-tooltip">
                  <b>{s.id}</b> · {s.name?.split(",")[0]}
                  <br />
                  {num(s.supplyKt, 1)} kt/yr available
                  <br />
                  {u > 0 ? `Used: ${num(u, 1)} kt` : "Not used in this plan"}
                  {s.offshore && (
                    <>
                      <br />
                      <b style={{ color: CRITICAL }}>In the sea ({num(s.coastKm ?? 0)} km off the coast): supply only</b>
                    </>
                  )}
                </Tooltip>
              </CircleMarker>
            );
          })}

        {visible.depots &&
          data.depots.map((d) => {
            const side = Math.round((6 + 2 * unitCount(d.units)) * 1.25);
            return (
              <Marker
                key={`${d.id}-${selectedId === d.id}`}
                position={[d.lat, d.lng]}
                icon={L.divIcon({
                  className: "",
                  html: `<div class="depot-diamond${selectedId === d.id ? " is-selected" : ""}" style="width:${side}px;height:${side}px"></div>`,
                  iconSize: [side, side],
                  iconAnchor: [side / 2, side / 2],
                })}
                eventHandlers={select(d.id)}
                title={`Depot at ${d.site ?? siteOf(d.id)}`}
                alt={`Depot at ${d.site ?? siteOf(d.id)}`}
              >
                <Tooltip className="saf-tooltip">
                  <FacilityTip f={d} kind="Depot" />
                </Tooltip>
              </Marker>
            );
          })}

        {visible.refineries &&
          data.refineries.map((r) => (
            <Marker
              key={`${r.id}-${selectedId === r.id}`}
              position={[r.lat, r.lng]}
              icon={pinIcon(
                "black",
                "industry",
                selectedId === r.id,
                visible.airports && data.airports.some((a) => km([a.lat, a.lng], [r.lat, r.lng]) < 0.5) ? AT_AIRPORT_DX : 0,
              )}
              eventHandlers={select(r.id)}
              zIndexOffset={500}
              title={`Refinery at ${r.site ?? siteOf(r.id)}`}
              alt={`Refinery at ${r.site ?? siteOf(r.id)}`}
            >
              <Tooltip className="saf-tooltip" direction="top" offset={[0, -30]}>
                <FacilityTip f={r} kind="Refinery" />
              </Tooltip>
            </Marker>
          ))}

        {visible.airports &&
          data.airports.map((a) => (
            <Marker
              key={`${a.id}-${selectedId === a.id}`}
              position={[a.lat, a.lng]}
              icon={pinIcon(a.island ? "red" : "gray", "plane", selectedId === a.id)}
              eventHandlers={select(a.id)}
              zIndexOffset={1000}
              title={a.name}
              alt={a.name}
            >
              <Tooltip className="saf-tooltip" direction="top" offset={[0, -30]}>
                <b>
                  {a.name} ({a.id})
                </b>
                <br />
                {a.city}
                <br />
                {num(delivered.get(a.id) ?? 0, 1)} kt SAF/yr delivered
                {a.island && (
                  <>
                    <br />
                    <b style={{ color: CRITICAL }}>
                      On an island: SAF arrives by barge,
                      <br />
                      at the truck rate per t·km.
                    </b>
                  </>
                )}
              </Tooltip>
            </Marker>
          ))}
      </MapContainer>

      {/* Layer switch, top right, like the Streamlit map's layer control. */}
      <div className="absolute right-3 top-3 z-[1000]">
        <button
          type="button"
          aria-label="Map layers"
          aria-expanded={layersOpen}
          onClick={() => setLayersOpen((o) => !o)}
          className="grid h-11 w-11 place-items-center rounded border-2 border-black/20 bg-white text-slate-500 hover:bg-slate-50"
        >
          <i className="fa fa-layer-group" aria-hidden />
        </button>
        {layersOpen && (
          <div className="mt-1 w-64 space-y-1 rounded border-2 border-black/20 bg-white p-2.5 text-xs text-slate-900">
            {LAYERS.map((l) => (
              <label key={l.key} className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={visible[l.key]}
                  onChange={() => setVisible((v) => ({ ...v, [l.key]: !v[l.key] }))}
                  className="accent-brand"
                />
                {l.label}
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Legend, bottom left, matching the Streamlit map. */}
      <div className="pointer-events-none absolute bottom-6 left-2.5 z-[1000] rounded-md bg-white/95 px-2.5 py-1.5 text-[11.5px] leading-[1.55] text-slate-900 shadow">
        {Object.values(LEG_STYLE).map((s) => (
          <p key={s.label} className="flex items-center">
            <span className="mr-1.5 inline-block h-1 w-[18px] rounded-sm" style={{ background: s.color }} aria-hidden />
            {s.label}
          </p>
        ))}
        <p className="text-slate-500">{data.flows.some((f) => f.path) ? "Road routes" : "Straight lines (great-circle × 1.3)"} · width ∝ kt/yr · arrows show truck direction</p>
        <p>
          <i className="fa fa-industry" aria-hidden /> Refinery&nbsp;&nbsp;
          <span className="mx-1 inline-block h-2 w-2 rotate-45 border-2" style={{ borderColor: INK }} aria-hidden /> Depot&nbsp;&nbsp;
          <i className="fa fa-plane" aria-hidden /> Airport
        </p>
        <p className="flex items-center gap-1">
          <span className="inline-block h-[9px] w-[9px] rounded-full" style={{ background: INK_2 }} aria-hidden />
          Biomass used&nbsp;
          <span className="inline-block h-[9px] w-[9px] rounded-full border" style={{ borderColor: INK_2 }} aria-hidden />
          unused&nbsp;
          <span className="inline-block h-[9px] w-[9px] rounded-full border-2" style={{ borderColor: CRITICAL }} aria-hidden />
          in the sea
        </p>
      </div>
    </div>
  );
}
