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

// Organization/site/fleet foregrounded as primary (Enterprise Experience Pass A §16),
// grouped into Performance/Execution (Pass B §21) so a flat 9-item list doesn't read as
// one undifferentiated block — labels are light-touch (smaller/lighter than the
// "ENGINEERING" master label below) since this is still the product's primary nav, not a
// secondary registry. Knowledge/Assistant/Metrics stay ungrouped: none belongs to either
// cluster, and a group of one item would be noise, not clarity.
const PRIMARY_GROUPS: { label: string | null; items: NavItem[] }[] = [
  {
    label: "Performance",
    items: [
      { href: "/performance/organization", label: "Organization" },
      { href: "/performance/sites", label: "Sites" },
      { href: "/fleet", label: "Fleet" },
    ],
  },
  {
    label: "Execution",
    items: [
      { href: "/incidents", label: "Incidents" },
      { href: "/maintenance", label: "Maintenance" },
      { href: "/action-readiness", label: "Action Readiness" },
    ],
  },
  {
    label: null,
    items: [
      { href: "/knowledge", label: "Knowledge" },
      { href: "/assistant", label: "Assistant" },
      { href: "/metrics", label: "Metrics" },
    ],
  },
];

// Grouped per the Engineering IA (data collection -> intelligence pipeline ->
// governance) rather than one flat list — a technical reviewer can find what they want
// without a business reviewer ever needing to.
const ENGINEERING_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Data & Sensing",
    items: [
      { href: "/hierarchy", label: "Asset Hierarchy" },
      { href: "/sensors", label: "Sensor Inventory" },
      { href: "/data-quality", label: "Data Quality" },
    ],
  },
  {
    label: "Intelligence Engineering",
    items: [
      { href: "/baselines", label: "Baselines" },
      { href: "/rules", label: "Rule Findings" },
      { href: "/features", label: "Features" },
      { href: "/ml", label: "ML Evidence" },
      { href: "/state-estimation", label: "Condition Estimation" },
      { href: "/intelligence", label: "Technical Provenance" },
    ],
  },
  {
    label: "Governance",
    items: [
      { href: "/configuration", label: "Configuration" },
      { href: "/audit", label: "Audit" },
      { href: "/system", label: "System Status" },
    ],
  },
];

function NavLink({
  item,
  active,
  onClick,
}: {
  item: NavItem;
  active: boolean;
  onClick?: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`block rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
        active ? "bg-sky-500/15 text-sky-300" : "text-slate-300 hover:bg-white/5 hover:text-white"
      }`}
    >
      {item.label}
    </Link>
  );
}

function EngineeringLink({
  item,
  active,
  onClick,
}: {
  item: NavItem;
  active: boolean;
  onClick?: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`block rounded-md px-3 py-1 text-[13px] transition-colors ${
        active ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
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
  if (readiness.data?.status === "ready")
    return <StatusPill tone="ok">All systems ready</StatusPill>;
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
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  return (
    <>
      <div className="px-4 py-5">
        <Link href="/performance/organization" className="block">
          <span className="text-sm font-semibold tracking-wide text-white">LubriSense AI</span>
          <span className="mt-0.5 block text-xs text-slate-400">
            Condition-driven lubrication intelligence
          </span>
        </Link>
      </div>
      <nav aria-label="Primary" className="flex flex-col gap-3 px-2">
        {PRIMARY_GROUPS.map((group, index) => (
          <div key={group.label ?? `group-${index}`} className="flex flex-col gap-0.5">
            {group.label && (
              <div className="px-2 pb-0.5 text-[10px] font-medium tracking-wide text-slate-500 uppercase">
                {group.label}
              </div>
            )}
            {group.items.map((item) => (
              <NavLink
                key={item.href}
                item={item}
                active={isActive(item.href)}
                onClick={onNavigate}
              />
            ))}
          </div>
        ))}
      </nav>

      <div className="mt-6 border-t border-white/10 pt-4">
        <div className="px-4 text-[11px] font-semibold tracking-wider text-slate-500 uppercase">
          Engineering
        </div>
        {ENGINEERING_GROUPS.map((group) => (
          <div key={group.label} className="mt-3">
            <div className="px-4 text-[10px] font-medium tracking-wide text-slate-600 uppercase">
              {group.label}
            </div>
            <nav aria-label={group.label} className="mt-1 flex flex-col gap-0.5 px-2">
              {group.items.map((item) => (
                <EngineeringLink
                  key={item.href}
                  item={item}
                  active={isActive(item.href)}
                  onClick={onNavigate}
                />
              ))}
            </nav>
          </div>
        ))}
        <div className="h-4" />
      </div>
    </>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 overflow-y-auto bg-slate-900 lg:flex lg:flex-col">
        <SidebarContent pathname={pathname} />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 flex lg:hidden">
          <div
            className="fixed inset-0 bg-black/50"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <aside className="relative z-50 w-64 overflow-y-auto bg-slate-900">
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
