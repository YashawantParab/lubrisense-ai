const TIER_CLASSES = {
  // Supporting evidence / standard content — the default, used everywhere today.
  standard: "border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900",
  // Operational conclusion / decision — one visual step up, for the handful of cards
  // that ARE the answer to "what should I do", not supporting material.
  elevated:
    "border-zinc-200 bg-white shadow-sm ring-1 ring-zinc-900/[0.02] dark:border-zinc-800 dark:bg-zinc-900 dark:ring-white/[0.02]",
} as const;

export function SectionCard({
  title,
  actions,
  children,
  className = "",
  tier = "standard",
}: {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  tier?: keyof typeof TIER_CLASSES;
}) {
  return (
    <section className={`rounded-lg border p-4 ${TIER_CLASSES[tier]} ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && (
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{title}</h2>
          )}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}
