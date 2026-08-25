import { AttributionLevelBadge, EnergyAssessmentStatusBadge } from "@/components/badges";
import { humanize } from "@/lib/terminology";

/**
 * An active energy opportunity (task §9, an IDF-01-shaped case) — no maintenance
 * intervention has happened yet, so there is no outcome to verify. Explicitly never shows
 * avoided energy, a CO2e estimate, or "savings" language; those only ever appear once a
 * qualified outcome exists (`QualifiedOutcomePanel`).
 */
export function OpportunityStatePanel({
  energyStatus,
  attributionLevel,
  conditionType,
  maintenanceStateLabel,
}: {
  energyStatus: string;
  attributionLevel?: string;
  conditionType?: string | null;
  /** A human-readable maintenance/intervention state, if any case is open — plain text
   * so this component doesn't need to know the full `MaintenanceState` vocabulary. */
  maintenanceStateLabel?: string | null;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-lg bg-amber-50/60 p-4 dark:bg-amber-500/[0.06]">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-semibold tracking-wide text-amber-700 uppercase dark:text-amber-400">
          Active opportunity
        </p>
        <EnergyAssessmentStatusBadge value={energyStatus} />
        {attributionLevel && attributionLevel !== "NO_EVIDENCE" && (
          <AttributionLevelBadge value={attributionLevel} />
        )}
      </div>
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Contextual energy demand</dt>
          <dd className="font-medium text-zinc-900 dark:text-zinc-100">{humanize(energyStatus)}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Attribution-supported</dt>
          <dd className="font-medium text-zinc-900 dark:text-zinc-100">
            {attributionLevel && attributionLevel !== "NO_EVIDENCE" ? "Yes" : "Not yet"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Outcome</dt>
          <dd className="font-medium text-zinc-900 dark:text-zinc-100">Not yet verified</dd>
        </div>
        {conditionType && (
          <div>
            <dt className="text-xs text-zinc-500 dark:text-zinc-400">Relevant condition</dt>
            <dd className="font-medium text-zinc-900 dark:text-zinc-100">
              {humanize(conditionType)}
            </dd>
          </div>
        )}
        <div>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">Maintenance / intervention</dt>
          <dd className="font-medium text-zinc-900 dark:text-zinc-100">
            {maintenanceStateLabel ?? "None opened yet"}
          </dd>
        </div>
      </dl>
      <p className="text-[11px] text-zinc-400 italic dark:text-zinc-600">
        No maintenance intervention has been completed yet — no avoided energy or carbon estimate
        applies until a qualified outcome exists.
      </p>
    </div>
  );
}
