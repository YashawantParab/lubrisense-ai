/**
 * One plain-English interpretation sentence per real `condition_type` — the same
 * evidence-language discipline CLAUDE.md's failure-mode catalog already requires
 * ("evidence is consistent with...", never a confirmed-fault claim), just phrased for a
 * reviewer instead of an engineer. This is what a reviewer reads first; the backend's own
 * `evidence_summary.what_is_happening`/`why` sentences (rule-finding identifiers,
 * standardized distances) stay real and available, just moved to an expandable
 * "Technical evidence" section (`EvidenceWhyDetails` in condition-evidence.tsx) rather
 * than leading the primary view.
 */
const CONDITION_TYPE_INTERPRETATION: Partial<Record<string, string>> = {
  NORMAL_OPERATION: "All monitored signals are within their expected operating range.",
  DEVELOPING_RESTRICTION_PATTERN:
    "Pressure is trending materially above this asset's normal operating range — consistent with a developing lubrication restriction.",
  DELIVERY_BLOCKAGE_PATTERN:
    "Evidence is consistent with a blockage somewhere in the lubrication delivery path.",
  POSSIBLE_LEAKAGE_PATTERN:
    "Reservoir level is falling faster than this asset's normal consumption rate — consistent with a possible lubricant leak.",
  PUMP_PERFORMANCE_DEGRADATION:
    "Pump current is trending materially above its expected baseline — consistent with declining pump performance.",
  LOW_LUBRICANT_AVAILABILITY:
    "Reservoir level has fallen below the configured safe-supply threshold.",
  BEARING_CONDITION_DEGRADATION:
    "Bearing temperature and/or vibration are trending above their expected baseline, alongside other lubrication-system evidence.",
  INDEPENDENT_BEARING_CONDITION:
    "Bearing temperature and/or vibration are trending above their expected baseline while lubrication-system signals remain normal — evidence does not point to a lubrication-related cause.",
  LUBRICATION_DELIVERY_DEGRADATION:
    "Lubrication delivery signals are trending outside their expected range.",
  SENSOR_OR_DATA_QUALITY_LIMITATION:
    "Enough of this asset's instrumentation is currently untrusted that a confident condition assessment isn't possible.",
  INSUFFICIENT_EVIDENCE:
    "Not enough recent trusted data has been gathered yet to assess this asset's condition.",
  AMBIGUOUS_CONDITION:
    "Multiple evidence sources point to different explanations — further inspection is needed to resolve which applies.",
};

export function conditionInterpretation(conditionType: string): string {
  return (
    CONDITION_TYPE_INTERPRETATION[conditionType] ??
    "Evidence is being synthesized for this condition — see technical evidence for detail."
  );
}
