/**
 * Shared number formatting for Lubrication Efficiency Intelligence fields. The backend
 * already computes every `*_pct` field as a percentage value, not a fraction
 * (`backend/app/energy/domain/residual.py`: `residual_pct = (residual_kw /
 * expected_power_kw) * 100.0`) — these helpers must NOT multiply by 100 again. A first
 * draft of the Machine Energy & Efficiency surface did exactly that (turning IDF-01's
 * real +13.7% into a displayed +1372.0%/-160.7%-shaped bug), caught by comparing the
 * rendered page against the raw API response during manual verification.
 */

export function formatKw(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(2)} kW`;
}

export function formatPct(value: number | null): string {
  return value === null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}
