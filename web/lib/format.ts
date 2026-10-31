// Number formatting shared by every component.

/** USD as millions, e.g. 489_925_811 -> "$489.9M". */
export function usdM(v: number, digits = 1): string {
  return `$${(v / 1e6).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}M`;
}

/** Plain USD with thousands separators. */
export function usd(v: number): string {
  return `$${Math.round(v).toLocaleString("en-US")}`;
}

export function num(v: number, digits = 0): string {
  // Values that round to zero print as 0, never "-0" (solver noise like -1e-9).
  if (Math.abs(v) < 0.5 * 10 ** -digits) v = 0;
  return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Signed percentage change from `base` to `value`, e.g. -47.1. */
export function pctChange(value: number, base: number): number {
  return base === 0 ? 0 : ((value - base) / base) * 100;
}

export function coords(lat: number, lng: number): string {
  return `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
}
