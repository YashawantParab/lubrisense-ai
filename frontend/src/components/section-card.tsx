// Industrial open-composition language: `open` (the default) is a plain section with a
// top divider and no enclosing box — grouping comes from typography/spacing, not a white
// tile with a gray border. `standard`/`elevated` remain for genuine callouts (dense
// tables, a hero panel, the flagship case) that actually benefit from a contained surface
// — used sparingly and only where a page explicitly opts in.
const TIER_CLASSES = {
  open: "border-0 border-t border-zinc-100 bg-transparent p-0 pt-5 dark:border-zinc-800/70",
  standard: "rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900",
  elevated:
    "rounded-lg border border-zinc-200 bg-white p-4 shadow-sm ring-1 ring-zinc-900/[0.02] dark:border-zinc-800 dark:bg-zinc-900 dark:ring-white/[0.02]",
  // Full-bleed tinted band — visual grouping without a hard-edged box; for a section that
  // should read as a distinct zone (e.g. an intelligence panel) without becoming a tile.
  band: "rounded-xl bg-zinc-50/70 p-5 dark:bg-zinc-900/40",
} as const;

export function SectionCard({
  title,
  actions,
  children,
  className = "",
  tier = "open",
}: {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  tier?: keyof typeof TIER_CLASSES;
}) {
  return (
    <section className={`${TIER_CLASSES[tier]} ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && (
            <h2 className="text-[13px] font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
              {title}
            </h2>
          )}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}
