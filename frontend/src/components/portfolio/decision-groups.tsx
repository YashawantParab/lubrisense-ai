import Link from "next/link";

import type { KpiItem } from "@/components/kpi-strip";

/**
 * Organization Home's decision summary (Enterprise Product Rebuild Pass 2 §2) — three
 * coherent groups instead of one flat KPI strip, so a reader's eye lands on "what kind of
 * decision is this" before "what's the number." Reliability/Risk is visually dominant
 * (accent border, first, largest numbers) — CO2e never gets that treatment, per the
 * standing "carbon is never a hero metric" rule.
 */
export interface DecisionGroupProps {
  title: string;
  items: KpiItem[];
  dominant?: boolean;
}

function DecisionGroup({ title, items, dominant }: DecisionGroupProps) {
  return (
    <div
      className={`flex flex-col gap-3 rounded-lg border p-4 ${
        dominant
          ? "border-zinc-300 bg-white dark:border-zinc-700 dark:bg-zinc-900"
          : "border-zinc-200 bg-zinc-50/50 dark:border-zinc-800 dark:bg-zinc-900/40"
      }`}
    >
      <h3
        className={`text-xs font-semibold tracking-wide uppercase ${
          dominant ? "text-zinc-700 dark:text-zinc-300" : "text-zinc-500 dark:text-zinc-400"
        }`}
      >
        {title}
      </h3>
      <div className="flex flex-wrap gap-x-8 gap-y-3">
        {items.map((item) => {
          const inner = (
            <div className="flex items-baseline gap-2">
              <span
                className={`font-semibold ${dominant ? "text-3xl" : "text-2xl"} ${
                  item.valueClassName ?? "text-zinc-900 dark:text-zinc-100"
                }`}
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
    </div>
  );
}

export function DecisionGroups({
  reliability,
  maintenance,
  efficiency,
}: {
  reliability: KpiItem[];
  maintenance: KpiItem[];
  efficiency: KpiItem[];
}) {
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <div className="lg:col-span-1">
        <DecisionGroup title="Reliability / Risk" items={reliability} dominant />
      </div>
      <DecisionGroup title="Maintenance Execution" items={maintenance} />
      <DecisionGroup title="Efficiency / Outcomes" items={efficiency} />
    </div>
  );
}
