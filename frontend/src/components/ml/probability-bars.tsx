import { failureLabelName } from "@/lib/ml-terminology";

/** Real class scores straight from `predict_proba` — sums to ~1 across the model's own
 * label schema, never a frontend-invented distribution. Deliberately never called
 * "probability" in copy: the training pipeline has no calibration step (no Platt/isotonic
 * scaling against a held-out set), so these are the model's raw relative scores, not a
 * validated probability of correctness. Sorted descending so the leading class reads
 * first. */
export function ProbabilityBars({
  probabilities,
  predictedClass,
}: {
  probabilities: Record<string, number>;
  predictedClass: string | null;
}) {
  const entries = Object.entries(probabilities).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      {entries.map(([label, value]) => (
        <div key={label} className="flex items-center gap-2 text-sm">
          <span
            className={`w-44 flex-none truncate ${
              label === predictedClass
                ? "font-medium text-zinc-900 dark:text-zinc-100"
                : "text-zinc-500 dark:text-zinc-400"
            }`}
          >
            {failureLabelName(label)}
          </span>
          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
            <div
              className={`h-full rounded-full ${
                label === predictedClass ? "bg-sky-500" : "bg-zinc-300 dark:bg-zinc-600"
              }`}
              style={{ width: `${Math.max(value * 100, value > 0 ? 1.5 : 0)}%` }}
            />
          </div>
          <span className="w-12 flex-none text-right text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
            {Math.round(value * 100)}%
          </span>
        </div>
      ))}
      <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-600">
        Classification scores from the model&rsquo;s own <code>predict_proba</code> — real model
        output, not an estimate, but not calibrated against a held-out set. Treat as a relative
        ranking across classes, not a validated probability of correctness.
      </p>
    </div>
  );
}
