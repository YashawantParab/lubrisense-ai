import { StatusPill } from "@/components/status-pill";
import {
  actionReadinessStateTone,
  capabilityLevelTone,
  commissioningStatusTone,
  compatibilityTone,
  confidenceTone,
  customerStatusTone,
  dataTrustCategoryTone,
  energyBucketTone,
  feedbackTone,
  humanize,
  incidentStateTone,
  maintenanceOutcomeBucketTone,
  maintenanceStateTone,
  modelStatusTone,
  portfolioOutcomeTone,
  portfolioPriorityTone,
  priorityTone,
  provenanceTone,
  qualityLabel,
  qualityTone,
  severityTone,
} from "@/lib/terminology";

export function SeverityBadge({ value }: { value: string }) {
  return <StatusPill tone={severityTone(value)}>{humanize(value)}</StatusPill>;
}

export function ConfidenceBadge({ value }: { value: string }) {
  return <StatusPill tone={confidenceTone(value)}>confidence: {humanize(value)}</StatusPill>;
}

export function PriorityBadge({ value }: { value: string }) {
  return <StatusPill tone={priorityTone(value)}>{humanize(value)}</StatusPill>;
}

export function QualityBadge({ value }: { value: string }) {
  return <StatusPill tone={qualityTone(value)}>{qualityLabel(value)}</StatusPill>;
}

export function IncidentStateBadge({ value }: { value: string }) {
  return <StatusPill tone={incidentStateTone(value)}>{humanize(value)}</StatusPill>;
}

export function MaintenanceStateBadge({ value }: { value: string }) {
  return <StatusPill tone={maintenanceStateTone(value)}>{humanize(value)}</StatusPill>;
}

export function FeedbackBadge({ value }: { value: string }) {
  return <StatusPill tone={feedbackTone(value)}>{humanize(value)}</StatusPill>;
}

export function CustomerStatusBadge({ value }: { value: string }) {
  return <StatusPill tone={customerStatusTone(value)}>{humanize(value)}</StatusPill>;
}

export function ProvenanceBadge({ value }: { value: string }) {
  return <StatusPill tone={provenanceTone(value)}>{humanize(value)}</StatusPill>;
}

export function HumanReviewBadge() {
  return <StatusPill tone="warn">Human review required</StatusPill>;
}

export function CommissioningStatusBadge({ value }: { value: string }) {
  return <StatusPill tone={commissioningStatusTone(value)}>{humanize(value)}</StatusPill>;
}

export function CapabilityLevelBadge({ value }: { value: string }) {
  return <StatusPill tone={capabilityLevelTone(value)}>{humanize(value)}</StatusPill>;
}

export function CompatibilityBadge({ value }: { value: string }) {
  return <StatusPill tone={compatibilityTone(value)}>{humanize(value)}</StatusPill>;
}

export function ModelStatusBadge({ value }: { value: string }) {
  return <StatusPill tone={modelStatusTone(value)}>{humanize(value)}</StatusPill>;
}

// --- Portfolio Intelligence (organization/site/area performance, ADR-177) ----------

export function PortfolioPriorityBadge({ value }: { value: string }) {
  return <StatusPill tone={portfolioPriorityTone(value)}>{humanize(value)}</StatusPill>;
}

export function ActionReadinessStateBadge({ value }: { value: string }) {
  return <StatusPill tone={actionReadinessStateTone(value)}>{humanize(value)}</StatusPill>;
}

export function EnergyBucketBadge({ value }: { value: string }) {
  return <StatusPill tone={energyBucketTone(value)}>{humanize(value)}</StatusPill>;
}

export function MaintenanceOutcomeBadge({ value }: { value: string }) {
  return <StatusPill tone={maintenanceOutcomeBucketTone(value)}>{humanize(value)}</StatusPill>;
}

export function DataTrustCategoryBadge({ value }: { value: string }) {
  return <StatusPill tone={dataTrustCategoryTone(value)}>{humanize(value)}</StatusPill>;
}

export function PortfolioOutcomeBadge({ value }: { value: string }) {
  return <StatusPill tone={portfolioOutcomeTone(value)}>{humanize(value)}</StatusPill>;
}
