"use client";

import Link from "next/link";
import { useMemo } from "react";

import { AttributionPanel } from "@/components/energy/attribution-panel";
import { EnergyOutcomeJourney } from "@/components/energy/energy-outcome-journey";
import { EnergyOutcomePanel } from "@/components/energy/energy-outcome-panel";
import { EnergyPowerChart } from "@/components/energy/energy-power-chart";
import { MachineCarbonPanel } from "@/components/energy/machine-carbon-panel";
import { MachineEnergyCurrent } from "@/components/energy/machine-energy-current";
import { OpportunityStatePanel } from "@/components/energy/opportunity-state-panel";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import type { TelemetryStoryMarker } from "@/components/telemetry-chart";
import {
  useEnergyAssessmentHistory,
  useFleetLatestAttribution,
  useFleetLatestCarbon,
  useFleetLatestEnergyAssessment,
  useFleetLatestEnergyOutcome,
} from "@/hooks/use-energy";

const NO_OPPORTUNITY_STATUSES = new Set([
  "WITHIN_EXPECTED_RANGE",
  "INSUFFICIENT_BASELINE",
  "INSUFFICIENT_DATA",
  "DATA_QUALITY_LIMITED",
]);

/**
 * The Machine Detail "Energy & Efficiency" surface (Enterprise Experience Pass B §5) —
 * uses only real, already-persisted fleet-latest energy/attribution/outcome/carbon rows
 * (never the backend's compute-on-GET single-machine endpoints — see `hooks/use-energy.ts`),
 * filtered to this one machine. Shows only what exists: no assessment renders an honest
 * empty state, an opportunity with no completed intervention never shows avoided energy or
 * a CO2e figure, and a qualified outcome is the only path that reaches either.
 */
export function MachineEnergySection({
  machineId,
  conditionType,
  maintenanceStateLabel,
  storyMarkers,
}: {
  machineId: string;
  conditionType?: string | null;
  maintenanceStateLabel?: string | null;
  storyMarkers?: TelemetryStoryMarker[];
}) {
  const fleetAssessment = useFleetLatestEnergyAssessment();
  const fleetAttribution = useFleetLatestAttribution();
  const fleetOutcome = useFleetLatestEnergyOutcome();
  const fleetCarbon = useFleetLatestCarbon();
  const history = useEnergyAssessmentHistory(machineId);

  const assessment = useMemo(
    () => (fleetAssessment.data ?? []).find((a) => a.machine_id === machineId) ?? null,
    [fleetAssessment.data, machineId],
  );
  const attribution = useMemo(
    () => (fleetAttribution.data ?? []).find((a) => a.machine_id === machineId) ?? null,
    [fleetAttribution.data, machineId],
  );
  const outcome = useMemo(
    () => (fleetOutcome.data ?? []).find((o) => o.machine_id === machineId) ?? null,
    [fleetOutcome.data, machineId],
  );
  const carbon = useMemo(
    () =>
      outcome
        ? ((fleetCarbon.data ?? []).find((c) => c.energy_outcome_verification_id === outcome.id) ??
          null)
        : null,
    [fleetCarbon.data, outcome],
  );

  return (
    <DataState
      isPending={fleetAssessment.isPending}
      isError={fleetAssessment.isError}
      error={fleetAssessment.error}
      loadingLabel="Loading energy assessment…"
    >
      {!assessment ? (
        <EmptyState
          title="No energy assessment available for this asset"
          description="Energy assessment requires a commissioned machine-power sensor — not every asset in this fleet has one."
        />
      ) : (
        <div className="flex flex-col gap-6">
          <MachineEnergyCurrent assessment={assessment} />

          <DataState isPending={history.isPending} isError={false}>
            <EnergyPowerChart history={history.data ?? []} storyMarkers={storyMarkers} />
          </DataState>

          {attribution && (
            <div className="border-t border-zinc-100 pt-4 dark:border-zinc-800">
              <AttributionPanel attribution={attribution} />
            </div>
          )}

          {outcome ? (
            <div className="flex flex-col gap-4 border-t border-zinc-100 pt-4 dark:border-zinc-800">
              <EnergyOutcomeJourney outcome={outcome} carbon={carbon} />
              <EnergyOutcomePanel outcome={outcome} />
              {carbon && <MachineCarbonPanel estimate={carbon} />}
            </div>
          ) : (
            !NO_OPPORTUNITY_STATUSES.has(assessment.status) && (
              <div className="border-t border-zinc-100 pt-4 dark:border-zinc-800">
                <OpportunityStatePanel
                  energyStatus={assessment.status}
                  attributionLevel={attribution?.attribution_level}
                  conditionType={conditionType}
                  maintenanceStateLabel={maintenanceStateLabel}
                />
              </div>
            )
          )}

          <Link
            href={`/data-quality?machine=${machineId}`}
            className="text-xs text-sky-600 hover:underline dark:text-sky-400"
          >
            Review the power sensor&rsquo;s data quality →
          </Link>
        </div>
      )}
    </DataState>
  );
}
