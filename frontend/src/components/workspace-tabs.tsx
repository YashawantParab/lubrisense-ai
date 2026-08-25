"use client";

/**
 * Shared tab-bar chrome for the mature-workspace surfaces (Organization, Site Detail, ML
 * Intelligence — Enterprise Product Rebuild Pass 2 §2/§4/§8) — one visual language for
 * "this page is a workspace with views," not a bespoke tab implementation per page. Purely
 * presentational; each caller owns its own active-tab state (usually URL-synced via
 * `?view=`) and passes it in.
 */
export interface WorkspaceTab {
  key: string;
  label: string;
  /** Optional small badge count shown after the label (e.g. an attention count). */
  count?: number;
}

export function WorkspaceTabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: (Omit<WorkspaceTab, "key"> & { key: T })[];
  active: T;
  onChange: (key: T) => void;
}) {
  return (
    <div
      role="tablist"
      className="flex flex-wrap gap-1 border-b border-zinc-200 dark:border-zinc-800"
    >
      {tabs.map((tab) => {
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.key)}
            className={`-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? "border-sky-600 text-sky-700 dark:border-sky-400 dark:text-sky-400"
                : "border-transparent text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
            }`}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span
                className={`rounded-full px-1.5 py-0.5 text-[11px] font-semibold ${
                  isActive
                    ? "bg-sky-100 text-sky-700 dark:bg-sky-500/20 dark:text-sky-300"
                    : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
                }`}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
