/**
 * Contextualizes a generic `RecommendedAction` enum value with the specific lubricated
 * component a machine's own name already carries (`equipment.ts`'s `componentFromName`) —
 * one central table, not per-page string substitution. The underlying action code/policy
 * (`backend/app/domain/enums.py`'s `RecommendedAction`, `decision_intelligence_v1.yaml`'s
 * condition→action map) is never touched; this only changes how the same nine fixed
 * values are worded when a machine's component context is available. When no template
 * exists for an action, or no component context is available (every non-curated
 * machine), callers get back the same plain `humanize(action)` text as before — never a
 * fabricated sentence.
 */

import { humanize } from "@/lib/terminology";

const ACTION_CONTEXT_TEMPLATE: Partial<Record<string, (component: string) => string>> = {
  INSPECT_LUBRICATION_PATH: (c) => `Inspect the lubrication path serving the ${c}.`,
  INSPECT_DISTRIBUTOR: (c) => `Inspect the distributor supplying the ${c}.`,
  CHECK_RESERVOIR: (c) => `Verify reservoir level and lubricant supply feeding the ${c}.`,
  CHECK_PUMP: (c) => `Inspect lubrication pump performance feeding the ${c}.`,
  INSPECT_BEARING: (c) => `Inspect the ${c} for temperature/vibration response.`,
  VERIFY_SENSOR: (c) => `Inspect sensor connectivity on the ${c}.`,
  REQUEST_ADDITIONAL_MEASUREMENT: (c) => `Request additional measurement coverage on the ${c}.`,
};

export function recommendedActionDisplay(
  action: string,
  component: string | null | undefined,
): string {
  const template = ACTION_CONTEXT_TEMPLATE[action];
  if (!template || !component) return humanize(action);
  return template(component.toLowerCase());
}
