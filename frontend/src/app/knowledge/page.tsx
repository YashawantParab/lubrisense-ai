"use client";

import { useState } from "react";
import Link from "next/link";

import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { useAskKnowledge, useDocuments } from "@/hooks/use-knowledge";
import { humanize } from "@/lib/terminology";

const STATUS_FILTERS = ["", "DRAFT", "REVIEW", "APPROVED", "RETIRED"];

function statusTone(value: string): "ok" | "warn" | "error" | "neutral" {
  if (value === "APPROVED") return "ok";
  if (value === "REVIEW") return "warn";
  if (value === "RETIRED") return "neutral";
  return "warn";
}

export default function KnowledgePage() {
  usePageTitle("Knowledge");
  const [statusFilter, setStatusFilter] = useState("");
  const documents = useDocuments(statusFilter || undefined);
  const [query, setQuery] = useState("");
  const ask = useAskKnowledge();

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Approved Knowledge Base"
        description="Only APPROVED documents are ever used for a cited answer — DRAFT/REVIEW/RETIRED documents are structurally excluded from retrieval."
      />

      <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Ask a question
          </h2>
          <Link
            href="/assistant"
            className="text-xs text-sky-600 hover:underline dark:text-sky-400"
          >
            Ask about a specific machine or incident instead →
          </Link>
        </div>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. What should I inspect for a developing restriction?"
            className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          />
          <button
            type="button"
            disabled={!query || ask.isPending}
            onClick={() => ask.mutate(query)}
            className="rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {ask.isPending ? "Asking…" : "Ask"}
          </button>
        </div>

        {ask.data && (
          <div className="mt-4 space-y-3">
            <div className="flex items-center gap-2">
              <StatusPill tone={ask.data.status === "INSUFFICIENT" ? "warn" : "ok"}>
                {humanize(ask.data.status)}
              </StatusPill>
            </div>
            <p className="whitespace-pre-line text-sm text-zinc-700 dark:text-zinc-300">
              {ask.data.text}
            </p>
            {ask.data.citations.length > 0 && (
              <div>
                <h3 className="mb-1 text-xs font-semibold text-zinc-500 dark:text-zinc-400">
                  Approved knowledge cited
                </h3>
                <ul className="space-y-1 text-xs text-zinc-600 dark:text-zinc-400">
                  {ask.data.citations.map((c) => (
                    <li key={c.chunk_id}>
                      {c.document_title} v{c.document_version} — {c.section} (
                      {c.document_type})
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Documents
          </h2>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-900"
          >
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>
                {s || "All statuses"}
              </option>
            ))}
          </select>
        </div>

        <DataState
          isPending={documents.isPending}
          isError={documents.isError}
          error={documents.error}
          loadingLabel="Loading documents…"
        >
          {(documents.data ?? []).length === 0 ? (
            <EmptyState
              title="No documents match this filter"
              description="Try a different status filter."
            />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                    <th className="px-4 py-2 font-medium">Title</th>
                    <th className="px-4 py-2 font-medium">Type</th>
                    <th className="px-4 py-2 font-medium">Version</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Scope</th>
                  </tr>
                </thead>
                <tbody>
                  {(documents.data ?? []).map((doc) => (
                    <tr
                      key={doc.id}
                      className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                    >
                      <td className="px-4 py-2 text-zinc-900 dark:text-zinc-100">{doc.title}</td>
                      <td className="px-4 py-2 text-xs text-zinc-700 dark:text-zinc-300">
                        {humanize(doc.document_type)}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs text-zinc-700 dark:text-zinc-300">
                        {doc.version}
                      </td>
                      <td className="px-4 py-2">
                        <StatusPill tone={statusTone(doc.status)}>{humanize(doc.status)}</StatusPill>
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {doc.tenant_id ? "Tenant" : "Global"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataState>
      </section>
    </div>
  );
}
