// Semantic tones for the whole product (docs: industrial design language) —
// ok=recovered/confirmed, warn=developing concern, error=high-severity actionable,
// info=analytical/evidence/monitoring context, neutral=structural/inactive.
const TONE_CLASSES = {
  ok: "bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/30",
  warn: "bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/30",
  error:
    "bg-red-50 text-red-700 ring-red-600/20 dark:bg-red-500/10 dark:text-red-400 dark:ring-red-500/30",
  info: "bg-sky-50 text-sky-700 ring-sky-600/20 dark:bg-sky-500/10 dark:text-sky-400 dark:ring-sky-500/30",
  neutral:
    "bg-zinc-100 text-zinc-600 ring-zinc-500/20 dark:bg-zinc-500/10 dark:text-zinc-400 dark:ring-zinc-500/30",
} as const;

export function StatusPill({
  tone,
  children,
  size = "md",
}: {
  tone: keyof typeof TONE_CLASSES;
  children: React.ReactNode;
  /** "lg" for a primary severity/condition chip that should read as a headline element,
   * not a secondary label — used sparingly (hero cards, page status strips). */
  size?: "md" | "lg";
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ring-1 ring-inset ${TONE_CLASSES[tone]} ${
        size === "lg" ? "px-3 py-1 text-sm font-semibold" : "px-2.5 py-1 text-xs"
      }`}
    >
      {children}
    </span>
  );
}
