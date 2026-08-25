import { RelativeTime } from "@/components/relative-time";
import { humanize } from "@/lib/terminology";
import type { CarbonImpactEstimate, EnergyOutcomeVerification } from "@/lib/api/energy-types";

interface Stage {
  key: string;
  label: string;
  headline: string;
  iso: string | null;
}

/**
 * The energy half of the closed-loop story (task §12) — Condition/Decision/Maintenance
 * are already the existing `CaseWorkflow` stepper at the top of this page; this picks up
 * where that leaves off (Outcome verification → Energy recovery → Carbon estimate),
 * reusing its exact dot/line visual language rather than a new one. Never shows a stage
 * as reached without a real persisted timestamp behind it.
 */
export function EnergyOutcomeJourney({
  outcome,
  carbon,
}: {
  outcome: EnergyOutcomeVerification;
  carbon: CarbonImpactEstimate | null;
}) {
  const qualified =
    outcome.energy_outcome_status === "QUALIFIED_RECOVERY" ||
    outcome.energy_outcome_status === "PROBABLE_RECOVERY";

  const stages: Stage[] = [
    {
      key: "outcome",
      label: "Outcome verification",
      headline: humanize(outcome.energy_outcome_status),
      iso: outcome.created_at,
    },
    {
      key: "recovery",
      label: "Energy recovery",
      headline: qualified
        ? `~${outcome.estimated_avoided_energy_kwh?.toFixed(1) ?? "—"} kWh qualified`
        : "Not qualified",
      iso: qualified ? outcome.created_at : null,
    },
    {
      key: "carbon",
      label: "Carbon estimate",
      headline:
        carbon?.estimated_co2e_kg !== null && carbon?.estimated_co2e_kg !== undefined
          ? `${carbon.estimated_co2e_kg.toFixed(2)} kg CO2e`
          : carbon
            ? humanize(carbon.estimate_status)
            : "Not eligible",
      iso:
        carbon?.estimated_co2e_kg !== null && carbon?.estimated_co2e_kg !== undefined
          ? carbon.created_at
          : null,
    },
  ];

  return (
    <ol className="flex flex-wrap items-start gap-x-1 gap-y-4">
      {stages.map((stage, index) => {
        const reached = Boolean(stage.iso);
        return (
          <li key={stage.key} className="flex flex-1 items-start last:flex-none">
            {index > 0 && (
              <span
                className={`mt-[7px] h-px min-w-[10px] flex-1 ${
                  reached ? "bg-sky-300 dark:bg-sky-800" : "bg-zinc-200 dark:bg-zinc-800"
                }`}
                aria-hidden
              />
            )}
            <div className="flex w-28 shrink-0 flex-col items-center gap-1 px-1.5 text-center">
              <span
                className={`h-2.5 w-2.5 rounded-full ${reached ? "bg-sky-500" : "bg-zinc-200 dark:bg-zinc-700"}`}
                aria-hidden
              />
              <span
                className={`text-[11px] font-semibold tracking-wide uppercase ${
                  reached ? "text-zinc-500 dark:text-zinc-400" : "text-zinc-300 dark:text-zinc-700"
                }`}
              >
                {stage.label}
              </span>
              <span
                className={`text-xs leading-snug ${
                  reached ? "text-zinc-700 dark:text-zinc-300" : "text-zinc-300 dark:text-zinc-700"
                }`}
              >
                {stage.headline}
              </span>
              {reached && (
                <RelativeTime
                  iso={stage.iso}
                  className="text-[10px] text-zinc-400 dark:text-zinc-600"
                />
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
