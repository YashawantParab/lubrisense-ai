const STEPS = [
  "Review the assets needing attention above",
  "Open a machine and inspect its condition",
  "Inspect the evidence and telemetry behind it",
  "Review the recommended action",
  "Check Action Readiness for that recommendation",
  "Follow the incident and maintenance outcome",
  "Ask the Assistant why the decision was made",
];

/** Compact, no modal, no forced onboarding — a reviewer can ignore this entirely. */
export function ReviewerWalkthrough() {
  return (
    <section className="rounded-lg border border-dashed border-zinc-200 px-4 py-3 dark:border-zinc-800">
      <p className="text-xs font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
        New here? Recommended walkthrough
      </p>
      <ol className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-xs text-zinc-600 dark:text-zinc-400">
        {STEPS.map((step, i) => (
          <li key={step} className="flex items-center gap-2">
            <span>
              <span className="text-zinc-400 dark:text-zinc-600">{i + 1}.</span> {step}
            </span>
            {i < STEPS.length - 1 && <span className="text-zinc-300 dark:text-zinc-700">→</span>}
          </li>
        ))}
      </ol>
    </section>
  );
}
