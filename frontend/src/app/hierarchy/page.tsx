"use client";

import Link from "next/link";

import { DataState } from "@/components/data-state";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { toneForStatus } from "@/lib/status-tone";
import type {
  HierarchyCustomerAccount,
  HierarchyPlant,
  HierarchyProductionLine,
  HierarchySite,
} from "@/lib/api/asset-hierarchy-types";

function MachineRow({
  machine,
}: {
  machine: { id: string; name: string; asset_code: string; machine_type: string; status: string };
}) {
  return (
    <li>
      <Link
        href={`/machines/${machine.id}`}
        className="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800"
      >
        <span className="flex items-center gap-2 text-zinc-800 dark:text-zinc-200">
          <span className="font-mono text-xs text-zinc-400">{machine.asset_code}</span>
          {machine.name}
          <span className="text-xs text-zinc-400">({machine.machine_type})</span>
        </span>
        <StatusPill tone={toneForStatus(machine.status)}>{machine.status}</StatusPill>
      </Link>
    </li>
  );
}

function ProductionLineNode({ line }: { line: HierarchyProductionLine }) {
  return (
    <details className="ml-4 border-l border-zinc-200 pl-3 dark:border-zinc-800" open>
      <summary className="cursor-pointer select-none py-1 text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {line.name} <span className="text-xs text-zinc-400">({line.machines.length} machines)</span>
      </summary>
      <ul className="ml-2 space-y-0.5">
        {line.machines.map((machine) => (
          <MachineRow key={machine.id} machine={machine} />
        ))}
      </ul>
    </details>
  );
}

function PlantNode({ plant }: { plant: HierarchyPlant }) {
  return (
    <details className="ml-4 border-l border-zinc-200 pl-3 dark:border-zinc-800" open>
      <summary className="cursor-pointer select-none py-1 text-sm font-semibold text-zinc-800 dark:text-zinc-200">
        {plant.name} <span className="font-mono text-xs text-zinc-400">{plant.code}</span>
      </summary>
      {plant.production_lines.map((line) => (
        <ProductionLineNode key={line.id} line={line} />
      ))}
    </details>
  );
}

function SiteNode({ site }: { site: HierarchySite }) {
  return (
    <details className="ml-4 border-l border-zinc-200 pl-3 dark:border-zinc-800" open>
      <summary className="cursor-pointer select-none py-1 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        {site.name} <span className="font-mono text-xs text-zinc-400">{site.code}</span>
      </summary>
      {site.plants.map((plant) => (
        <PlantNode key={plant.id} plant={plant} />
      ))}
    </details>
  );
}

function CustomerNode({ customer }: { customer: HierarchyCustomerAccount }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
          {customer.name}
        </h2>
        <div className="flex items-center gap-2">
          <StatusPill tone="neutral">{customer.service_tier}</StatusPill>
          <StatusPill tone={toneForStatus(customer.commercial_status)}>
            {customer.commercial_status}
          </StatusPill>
        </div>
      </div>
      <div className="mt-2">
        {customer.sites.map((site) => (
          <SiteNode key={site.id} site={site} />
        ))}
      </div>
    </section>
  );
}

export default function HierarchyPage() {
  const hierarchy = useHierarchy();

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-12">
      <header>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">Asset Hierarchy</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Customer → Site → Plant → Production Line → Machine, live from{" "}
          <code className="font-mono text-xs">GET /api/v1/hierarchy</code>. Select a machine to
          inspect its bearings, lubrication system, and sensors.
        </p>
      </header>

      <DataState
        isPending={hierarchy.isPending}
        isError={hierarchy.isError}
        error={hierarchy.error}
        loadingLabel="Loading asset hierarchy…"
      >
        {hierarchy.data && hierarchy.data.customers.length === 0 && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No customers found for this tenant yet.
          </p>
        )}
        <div className="flex flex-col gap-4">
          {hierarchy.data?.customers.map((customer) => (
            <CustomerNode key={customer.id} customer={customer} />
          ))}
        </div>
      </DataState>
    </div>
  );
}
