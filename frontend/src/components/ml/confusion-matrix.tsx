import { failureLabelName } from "@/lib/ml-terminology";
import type { ClassificationReport } from "@/lib/api/ml-types";

/** Real evaluation output (`test_report.confusion_matrix`), rows = actual class, columns =
 * predicted class — never synthesized. The diagonal is colored to make correct
 * classification visible at a glance; off-diagonal cells with real weight are the honest
 * "where does this model confuse one pattern with another" story. */
export function ConfusionMatrix({ report }: { report: ClassificationReport }) {
  const { labels, confusion_matrix: matrix } = report;
  const maxValue = Math.max(1, ...matrix.flat());
  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-xs">
        <thead>
          <tr>
            <th className="p-1 text-right align-bottom text-zinc-400 dark:text-zinc-600">
              Actual \ Predicted
            </th>
            {labels.map((label) => (
              <th
                key={label}
                className="max-w-16 min-w-12 p-1 text-center font-medium text-zinc-500 dark:text-zinc-400"
              >
                <span className="block truncate" title={failureLabelName(label)}>
                  {failureLabelName(label).split(" ")[0]}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map((rowLabel, i) => (
            <tr key={rowLabel}>
              <th className="p-1 text-right font-medium whitespace-nowrap text-zinc-500 dark:text-zinc-400">
                {failureLabelName(rowLabel)}
              </th>
              {labels.map((colLabel, j) => {
                const value = matrix[i]?.[j] ?? 0;
                const isDiagonal = i === j;
                const opacity = value === 0 ? 0 : 0.15 + 0.75 * (value / maxValue);
                return (
                  <td
                    key={colLabel}
                    className="p-1 text-center tabular-nums"
                    style={{
                      backgroundColor: isDiagonal
                        ? `rgba(16, 185, 129, ${opacity})`
                        : value > 0
                          ? `rgba(244, 63, 94, ${opacity})`
                          : undefined,
                    }}
                  >
                    {value || ""}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-zinc-400 dark:text-zinc-600">
        Rows are the true label from the evaluation dataset; columns are what the model predicted.
        Green diagonal = correct. Red off-diagonal = one pattern mistaken for another — real
        evaluation counts, not estimated.
      </p>
    </div>
  );
}

export function PerClassPerformance({ report }: { report: ClassificationReport }) {
  const { labels, precision, recall, f1, support } = report;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
            <th className="py-1.5 pr-4 font-medium">Class</th>
            <th className="py-1.5 pr-4 font-medium">Precision</th>
            <th className="py-1.5 pr-4 font-medium">Recall</th>
            <th className="py-1.5 pr-4 font-medium">F1</th>
            <th className="py-1.5 pr-4 font-medium">Evaluation samples</th>
          </tr>
        </thead>
        <tbody>
          {labels.map((label) => {
            const weak = (f1[label] ?? 0) < 0.2;
            return (
              <tr
                key={label}
                className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
              >
                <td className="py-1.5 pr-4 text-zinc-800 dark:text-zinc-200">
                  {failureLabelName(label)}
                </td>
                <td
                  className={`py-1.5 pr-4 tabular-nums ${weak ? "text-red-600 dark:text-red-400" : ""}`}
                >
                  {((precision[label] ?? 0) * 100).toFixed(0)}%
                </td>
                <td
                  className={`py-1.5 pr-4 tabular-nums ${weak ? "text-red-600 dark:text-red-400" : ""}`}
                >
                  {((recall[label] ?? 0) * 100).toFixed(0)}%
                </td>
                <td
                  className={`py-1.5 pr-4 tabular-nums ${weak ? "text-red-600 dark:text-red-400" : ""}`}
                >
                  {((f1[label] ?? 0) * 100).toFixed(0)}%
                </td>
                <td className="py-1.5 pr-4 tabular-nums text-zinc-500 dark:text-zinc-400">
                  {support[label] ?? 0}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-zinc-400 dark:text-zinc-600">
        Weak classes (F1 under 20%) are shown in red rather than hidden — this model does not
        reliably distinguish them yet.
      </p>
    </div>
  );
}
