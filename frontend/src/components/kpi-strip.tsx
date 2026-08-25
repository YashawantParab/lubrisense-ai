import Link from "next/link";

export interface KpiItem {
  label: string;
  value: React.ReactNode;
  href?: string;
  /** Tailwind text color class for the value — defaults to the neutral headline color.
   * Kept as an explicit class (not a `Tone`) since a KPI number itself isn't a status
   * pill — this only tints the digit, it never replaces a label with color alone. */
  valueClassName?: string;
}

/** Compact operational stat line (CLAUDE.md "charts support the decision, not the
 * product") — mirrors the Overview page's existing baseline-py stat-line pattern, kept
 * for the Organization Command Center rather than inventing a card-grid alternative. */
export function KpiStrip({ items }: { items: KpiItem[] }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-10 gap-y-3 border-y border-zinc-100 py-4 dark:border-zinc-800/70">
      {items.map((item) => {
        const inner = (
          <div className="flex items-baseline gap-2">
            <span
              className={`text-2xl font-semibold ${item.valueClassName ?? "text-zinc-900 dark:text-zinc-100"}`}
            >
              {item.value}
            </span>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">{item.label}</span>
          </div>
        );
        return item.href ? (
          <Link key={item.label} href={item.href} className="hover:opacity-80">
            {inner}
          </Link>
        ) : (
          <div key={item.label}>{inner}</div>
        );
      })}
    </div>
  );
}
