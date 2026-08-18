interface DataStateProps {
  isPending: boolean;
  isError: boolean;
  error?: unknown;
  children: React.ReactNode;
  loadingLabel?: string;
}

export function DataState({
  isPending,
  isError,
  error,
  children,
  loadingLabel = "Loading…",
}: DataStateProps) {
  if (isPending) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">{loadingLabel}</p>
    );
  }
  if (isError) {
    return (
      <p className="py-8 text-center text-sm text-red-600 dark:text-red-400">
        {error instanceof Error ? error.message : "Something went wrong."}
      </p>
    );
  }
  return <>{children}</>;
}
