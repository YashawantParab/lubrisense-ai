"use client";

/**
 * Shared "clean headline, raw evidence behind a toggle" pattern for condition/incident
 * evidence — used by the Overview priority card, incident detail, and machine detail.
 *
 * The backend's own evidence sentences (ConditionEvidenceSummary.what_is_happening/why)
 * are real, honest, and useful for engineering traceability, but they're authored as
 * literal rule-finding/state-estimate description strings (rule ids in SCREAMING_SNAKE_
 * CASE, scientific-notation standardized distances) — appropriate as technical detail,
 * not as the first sentence a reviewer reads. This composes a primary summary purely from
 * already-structured, already-vetted fields (condition type, evidence-source counts) and
 * moves the raw sentences into a collapsed "Technical evidence" section, mirroring the
 * same pattern applied to State Estimation's Kalman-filter detail.
 */

interface EvidenceIds {
  rule_finding_ids: string[];
  ml_result_ids: string[];
  state_estimate_ids: string[];
}

export function evidenceBackingLine(ids: EvidenceIds): string {
  const parts: string[] = [];
  const n = (count: number, singular: string, plural: string) =>
    `${count} ${count === 1 ? singular : plural}`;
  if (ids.rule_finding_ids.length > 0) {
    parts.push(n(ids.rule_finding_ids.length, "rule finding", "rule findings"));
  }
  if (ids.state_estimate_ids.length > 0) {
    parts.push(n(ids.state_estimate_ids.length, "sensor-trend estimate", "sensor-trend estimates"));
  }
  if (ids.ml_result_ids.length > 0) {
    parts.push(n(ids.ml_result_ids.length, "ML model result", "ML model results"));
  }
  if (parts.length === 0) return "No independent evidence sources contributed to this assessment.";
  return `Backed by ${parts.join(", ")}.`;
}

export function EvidenceWhyDetails({
  why,
  children,
}: {
  why: string[];
  children?: React.ReactNode;
}) {
  if (why.length === 0 && !children) return null;
  return (
    <details className="mt-3 border-t border-zinc-100 pt-3 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
      <summary className="cursor-pointer text-xs font-medium text-sky-600 select-none dark:text-sky-400">
        Technical evidence
      </summary>
      <div className="mt-2 space-y-3">
        {why.length > 0 && (
          <div>
            <p className="font-medium text-zinc-700 dark:text-zinc-300">Raw evidence sentences</p>
            <ul className="mt-1 list-inside list-disc space-y-1">
              {why.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        {children}
      </div>
    </details>
  );
}
