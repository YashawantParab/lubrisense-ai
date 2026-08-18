import Link from "next/link";

const LINKS = [
  { href: "/", label: "Platform Status" },
  { href: "/hierarchy", label: "Asset Hierarchy" },
  { href: "/sensors", label: "Sensor Inventory" },
  { href: "/data-quality", label: "Data Quality" },
  { href: "/baselines", label: "Baselines" },
  { href: "/rules", label: "Rule Findings" },
];

export function TopNav() {
  return (
    <nav className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-3">
        <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          LubriSense AI
        </span>
        <div className="flex gap-4">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-sm text-zinc-600 hover:text-sky-600 dark:text-zinc-400 dark:hover:text-sky-400"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
