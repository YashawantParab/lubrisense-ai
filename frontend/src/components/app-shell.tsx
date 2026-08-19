"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { useBackendReadiness } from "@/hooks/use-backend-status";
import { useAuth } from "@/lib/auth/context";
import { ALL_ROLES, ROLE_LABELS } from "@/lib/permissions";
import type { DemoRole } from "@/lib/api/auth-types";

interface NavItem {
  href: string;
  label: string;
}

const PRIMARY_NAV: NavItem[] = [
  { href: "/overview", label: "Overview" },
  { href: "/fleet", label: "Fleet" },
  { href: "/incidents", label: "Incidents" },
  { href: "/maintenance", label: "Maintenance" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/assistant", label: "Assistant" },
  { href: "/metrics", label: "Metrics" },
];

const SECONDARY_NAV: NavItem[] = [
  { href: "/configuration", label: "Configuration" },
  { href: "/audit", label: "Audit" },
  { href: "/hierarchy", label: "Asset Hierarchy" },
  { href: "/sensors", label: "Sensor Inventory" },
  { href: "/data-quality", label: "Data Quality" },
  { href: "/baselines", label: "Baselines" },
  { href: "/rules", label: "Rule Findings" },
  { href: "/features", label: "Features" },
  { href: "/ml", label: "ML" },
  { href: "/state-estimation", label: "State Estimation" },
  { href: "/intelligence", label: "Intelligence (raw)" },
  { href: "/system", label: "System Status" },
];

function NavLink({ item, active, onClick }: { item: NavItem; active: boolean; onClick?: () => void }) {
  return (
    <Link
      href={item.href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`block rounded-md px-3 py-1.5 text-sm transition-colors ${
        active
          ? "bg-sky-50 font-medium text-sky-700 dark:bg-sky-500/10 dark:text-sky-400"
          : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
      }`}
    >
      {item.label}
    </Link>
  );
}

function SystemStatusDot() {
  const readiness = useBackendReadiness();
  if (readiness.isPending) return <StatusPill tone="neutral">Checking</StatusPill>;
  if (readiness.isError) return <StatusPill tone="error">Backend unreachable</StatusPill>;
  if (readiness.data?.status === "ready") return <StatusPill tone="ok">All systems ready</StatusPill>;
  return <StatusPill tone="warn">Degraded</StatusPill>;
}

function RoleSwitcher() {
  const { role, displayName, switchRole, isLoading } = useAuth();
  return (
    <label className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
      <span className="hidden sm:inline">Demo identity</span>
      <select
        value={role}
        disabled={isLoading}
        onChange={(event) => switchRole(event.target.value as DemoRole)}
        className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-800 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
        aria-label="Switch demo role"
      >
        {ALL_ROLES.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABELS[r]}
          </option>
        ))}
      </select>
      <span className="hidden text-zinc-400 md:inline">({displayName})</span>
    </label>
  );
}

function SidebarContent({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <>
      <div className="px-4 py-4">
        <Link href="/overview" className="block">
          <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">LubriSense AI</span>
          <span className="block text-xs text-zinc-500 dark:text-zinc-400">
            Condition-driven lubrication
          </span>
        </Link>
      </div>
      <nav aria-label="Primary" className="flex flex-col gap-0.5 px-2">
        {PRIMARY_NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            active={pathname === item.href || pathname.startsWith(`${item.href}/`)}
            onClick={onNavigate}
          />
        ))}
      </nav>
      <div className="mt-6 px-4 text-xs font-medium uppercase tracking-wide text-zinc-400 dark:text-zinc-600">
        System
      </div>
      <nav aria-label="Secondary" className="mt-1 flex flex-col gap-0.5 px-2 pb-4">
        {SECONDARY_NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            active={pathname === item.href || pathname.startsWith(`${item.href}/`)}
            onClick={onNavigate}
          />
        ))}
      </nav>
    </>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 border-r border-zinc-200 bg-white lg:flex lg:flex-col dark:border-zinc-800 dark:bg-zinc-900">
        <SidebarContent pathname={pathname} />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 flex lg:hidden">
          <div
            className="fixed inset-0 bg-black/30"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <aside className="relative z-50 w-64 overflow-y-auto border-r border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <SidebarContent pathname={pathname} onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-zinc-200 bg-white px-4 py-2.5 dark:border-zinc-800 dark:bg-zinc-900">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 lg:hidden dark:text-zinc-400 dark:hover:bg-zinc-800"
            aria-label="Open navigation menu"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
              <path
                d="M3 5h14M3 10h14M3 15h14"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <div className="flex items-center gap-3">
            <SystemStatusDot />
          </div>
          <RoleSwitcher />
        </header>
        <main className="flex-1 bg-zinc-50 dark:bg-zinc-950">{children}</main>
      </div>
    </div>
  );
}
