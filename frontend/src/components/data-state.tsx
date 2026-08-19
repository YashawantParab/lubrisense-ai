import { ApiError } from "@/lib/api/client";

interface DataStateProps {
  isPending: boolean;
  isError: boolean;
  error?: unknown;
  children: React.ReactNode;
  loadingLabel?: string;
  onRetry?: () => void;
  /** Skeleton to render instead of the default text spinner while pending — use for
   * content-shaped loading (tables, cards) rather than a lone centered line. */
  skeleton?: React.ReactNode;
}

function readableMessage(error: unknown): string {
  if (error instanceof ApiError) {
    // ApiError.message is already the backend's clean, human-readable message (never a
    // stack trace or raw Pydantic/FastAPI validation detail — see app.core.errors on the
    // backend) — safe to show directly (Phase 29 brief §29.3).
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong loading this data.";
}

export function DataState({
  isPending,
  isError,
  error,
  children,
  loadingLabel = "Loading…",
  onRetry,
  skeleton,
}: DataStateProps) {
  if (isPending) {
    if (skeleton) return <>{skeleton}</>;
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-sm text-zinc-500 dark:text-zinc-400">
        <span
          aria-hidden
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-500 dark:border-zinc-700 dark:border-t-zinc-400"
        />
        <span>{loadingLabel}</span>
      </div>
    );
  }
  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-6 py-8 text-center dark:border-red-900/50 dark:bg-red-950/30">
        <p className="text-sm text-red-700 dark:text-red-400">{readableMessage(error)}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 dark:border-red-800 dark:bg-zinc-900 dark:text-red-400 dark:hover:bg-red-950/50"
          >
            Retry
          </button>
        )}
      </div>
    );
  }
  return <>{children}</>;
}
