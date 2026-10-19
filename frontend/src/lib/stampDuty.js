// NSW transfer (stamp) duty, 2025-26 thresholds incl. premium residential duty.
// Duty is per $100 or part thereof. Result is a suggestion — always editable in the UI.
export function calcStampDutyNSW(price) {
  const p = Number(price) || 0;
  if (p <= 0) return 0;
  const per100 = (over, rate) => Math.ceil(over / 100) * rate;
  if (p > 3721000) return Math.round(186667 + per100(p - 3721000, 7));
  if (p > 1240000) return Math.round(50250 + per100(p - 1240000, 5.5));
  if (p > 372000) return Math.round(11190 + per100(p - 372000, 4.5));
  if (p > 97000) return Math.round(1565 + per100(p - 97000, 3.5));
  if (p > 36000) return Math.round(497.5 + per100(p - 36000, 1.75));
  if (p > 17000) return Math.round(212.5 + per100(p - 17000, 1.5));
  return Math.max(10, Math.round(per100(p, 1.25)));
}
