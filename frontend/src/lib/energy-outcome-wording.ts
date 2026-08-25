import type { EnergyOutcomeVerification } from "@/lib/api/energy-types";

/**
 * The exact claim-hierarchy wording rule from task §10 — because `EnergyOutcomeVerification
 * .lubrication_association_status` already encodes exactly what the backend is entitled to
 * claim (`app.energy.domain.outcome`'s temporal-integrity policy — a good post-maintenance
 * outcome can never retroactively upgrade what the platform believed *before* the
 * intervention), this function only ever restates that status in prose. It never infers a
 * stronger claim from the residual numbers themselves — a BE-201-shaped case (qualified
 * recovery, `NO_EVIDENCE` pre-attribution) must read as "improved... under comparable
 * operation," never "lubrication saved X kWh."
 */
export function associationWording(outcome: EnergyOutcomeVerification): string {
  switch (outcome.lubrication_association_status) {
    case "LUBRICATION_ASSOCIATED_RECOVERY":
      return "Energy performance improved following intervention under comparable operation, with evidence consistent with a lubrication-related contribution both before and after the intervention.";
    case "QUALIFIED_ENERGY_RECOVERY":
      return "Energy performance improved following intervention under comparable operation.";
    case "OBSERVED_ENERGY_CHANGE":
      return "An energy change was observed following intervention, but the comparison does not yet meet the bar for a qualified recovery.";
    case "NOT_APPLICABLE":
    default:
      return "No energy-recovery claim applies to this outcome.";
  }
}
