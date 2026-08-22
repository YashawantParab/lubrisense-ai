import { SectionCard } from "@/components/section-card";

/**
 * Framing only — deliberately no invented numbers (no cost savings, uptime %, ROI, or
 * failure-reduction %). Every line states a structural property of condition-driven
 * monitoring vs. fixed-interval/threshold lubrication, not a claimed outcome.
 */
const VALUE_POINTS = [
  "Earlier visibility into lubrication delivery problems, before a fixed inspection interval would have caught them",
  "Fewer unnecessary interventions — action is recommended from evidence, not a calendar",
  "Faster troubleshooting through correlated evidence across rules, state estimation, and ML",
  "Higher trust in recommendations because data quality and provenance are explicit, not assumed",
  "Closed-loop learning — technician outcomes feed back into how future evidence is judged",
  "A path from scheduled/rule-based lubrication toward condition-driven action, with a human approving every step",
];

export function WhyConditionDriven() {
  return (
    <SectionCard title="Why condition-driven lubrication?">
      <ul className="grid gap-2.5 sm:grid-cols-2">
        {VALUE_POINTS.map((point) => (
          <li key={point} className="flex gap-2 text-sm text-zinc-700 dark:text-zinc-300">
            <span className="mt-1.5 h-1 w-1 flex-none rounded-full bg-sky-500" aria-hidden />
            {point}
          </li>
        ))}
      </ul>
      <p className="mt-3 border-t border-zinc-100 pt-2 text-xs text-zinc-400 dark:border-zinc-800 dark:text-zinc-600">
        Structural product claims, not measured customer outcomes — no cost, uptime, or
        failure-reduction figures are claimed anywhere in this platform.
      </p>
    </SectionCard>
  );
}
