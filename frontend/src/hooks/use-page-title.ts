"use client";

import { useEffect } from "react";

/** Sets `document.title` for one client page (Phase 29 brief §29.13 — "no generic
 * 'Next.js App' title"). App Router's `metadata` export requires a server component,
 * which every page in this app deliberately isn't (all data-fetching here is client
 * -side React Query, matching the rest of the codebase) — this is the pragmatic
 * client-side equivalent, restoring the layout's default title on unmount. */
export function usePageTitle(title: string): void {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · LubriSense AI`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
