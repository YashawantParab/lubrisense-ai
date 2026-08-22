import { humanizeFeatureName, signalGroupFor } from "@/lib/ml-terminology";
import type { FeatureContribution } from "@/lib/api/ml-types";

/** A real z-score against a training distribution can legitimately be enormous when that
 * feature's training-time variance was tiny (e.g. RPM held near-constant across every
 * training scenario) — the underlying number is genuine, not a bug, but printing
 * "+2039.360σ" reads as broken rather than "extreme" to a reviewer. Past this magnitude the
 * honest thing to show is the qualitative fact (far outside the training range), not a
 * false-precision decimal a statistics-literate reviewer would otherwise (reasonably)
 * assume is a rendering error. */
const EXTREME_Z_SCORE = 20;

/** `resultKind` controls the framing, not just the label — this distinction is load-bearing
 * (CLAUDE.md / brief §11): classification contributions are real per-instance feature
 * ablation (removing this feature measurably changed the predicted-class probability, a
 * genuine causal-adjacent signal for *this one prediction*), while anomaly contributions
 * are a z-score deviation from the model's training distribution — a legitimate but weaker
 * "this reading is unusual" signal, never claimed as the model's own attribution (Isolation
 * Forest has none). Never call the anomaly list "contribution". */
export function FeatureEvidence({
  contributions,
  resultKind,
}: {
  contributions: FeatureContribution[];
  resultKind: "ANOMALY" | "CLASSIFICATION";
}) {
  if (contributions.length === 0) return null;
  const isClassification = resultKind === "CLASSIFICATION";
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {isClassification
          ? "Signals contributing to this result"
          : "Signals most deviated from healthy training behavior"}
      </p>
      <ul className="flex flex-col divide-y divide-zinc-100 dark:divide-zinc-800">
        {contributions.map((c) => (
          <li key={c.feature} className="flex items-center justify-between gap-3 py-1.5 text-sm">
            <div className="min-w-0">
              <p className="truncate text-zinc-800 dark:text-zinc-200">
                {humanizeFeatureName(c.feature)}
              </p>
              <p className="text-xs text-zinc-400 dark:text-zinc-600">
                {signalGroupFor(c.feature)}
              </p>
            </div>
            <span
              className={`flex-none font-mono text-xs tabular-nums ${
                c.magnitude >= 0
                  ? "text-amber-600 dark:text-amber-400"
                  : "text-sky-600 dark:text-sky-400"
              }`}
            >
              {!isClassification && Math.abs(c.magnitude) >= EXTREME_Z_SCORE
                ? `far outside training range (${c.magnitude >= 0 ? "+" : "-"}${Math.round(Math.abs(c.magnitude))}σ)`
                : `${c.magnitude >= 0 ? "+" : ""}${c.magnitude.toFixed(3)}${isClassification ? "" : "σ"}`}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-zinc-400 dark:text-zinc-600">
        {isClassification
          ? "Magnitude is the real probability shift measured when this feature is removed from the model's input for this one prediction — the model's own contribution, not a raw reading."
          : "Magnitude is this reading's real z-score against the healthy training distribution — how unusual the value is, not a model-attributed cause."}
      </p>
    </div>
  );
}
