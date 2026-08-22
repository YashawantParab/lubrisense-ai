import Link from "next/link";

import { SectionCard } from "@/components/section-card";

/**
 * A compact explainer, not a live progress tracker — the eight steps below map directly
 * onto real backend concepts (not invented ones): `MachineStatus`
 * (REGISTERED → COMMISSIONING → BASELINING → MONITORED,
 * `backend/app/domain/enums.py`), the real commissioning-session wizard at
 * `/configuration/commission` (add sensors → assign gateway → validate → complete), the
 * `CapabilityLevel` a machine earns from which sensor types are actually mapped
 * (`backend/app/commissioning/policy.py`), baseline readiness, and this platform's own
 * data-trust and action-readiness gates. No step here claims an automated capability that
 * isn't implemented.
 */
const STEPS: { title: string; detail: string }[] = [
  { title: "Connect asset", detail: "Register the machine and assign it to a gateway." },
  {
    title: "Map sensors",
    detail: "Add each sensor and its type — capability level is derived from what's mapped.",
  },
  {
    title: "Verify signal quality",
    detail: "Commissioning validation checks units and plausibility before data is trusted.",
  },
  {
    title: "Establish contextual baseline",
    detail: "The machine enters Baselining while normal-operating-range statistics accumulate.",
  },
  {
    title: "Confirm operating context",
    detail: "Commissioning is marked complete and the machine is promoted to Monitored.",
  },
  {
    title: "Enable condition assessment",
    detail: "Condition Intelligence starts producing real assessments once evidence exists.",
  },
  {
    title: "Enable decision recommendations",
    detail: "Decision Intelligence turns a sufficiently-confident condition into a recommendation.",
  },
  {
    title: "Evaluate action readiness",
    detail: "The recommendation is gated into a readiness mode — never executed automatically.",
  },
];

export function CommissioningJourney() {
  return (
    <SectionCard
      title="How assets become decision-ready"
      actions={
        <Link
          href="/configuration/commission"
          className="text-xs text-sky-600 hover:underline dark:text-sky-400"
        >
          Commission an asset →
        </Link>
      }
    >
      <p className="mb-4 text-xs text-zinc-500 dark:text-zinc-400">
        A machine doesn&rsquo;t become trustworthy the moment sensors are wired up — it earns
        recommendations in stages, each gated on real evidence.
      </p>
      <ol className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((step, i) => (
          <li key={step.title} className="flex gap-2.5">
            <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-zinc-100 text-[11px] font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
              {i + 1}
            </span>
            <div>
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{step.title}</p>
              <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-4 border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
        <span className="font-medium text-zinc-700 dark:text-zinc-300">Monitored</span> means
        commissioning is complete, not that a recommendation is trustworthy yet —{" "}
        <span className="font-medium text-zinc-700 dark:text-zinc-300">decision-ready</span>{" "}
        additionally requires a sufficient baseline and trusted data, and{" "}
        <span className="font-medium text-zinc-700 dark:text-zinc-300">action-ready</span>{" "}
        additionally requires the condition itself to be confidently actionable — see{" "}
        <Link href="/action-readiness" className="text-sky-600 hover:underline dark:text-sky-400">
          Action Readiness
        </Link>
        .
      </p>
    </SectionCard>
  );
}
