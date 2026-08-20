import { StatusPill } from "@/components/status-pill";
import {
  capabilityLevelTone,
  commissioningStatusTone,
  compatibilityTone,
  confidenceTone,
  customerStatusTone,
  feedbackTone,
  humanize,
  incidentStateTone,
  maintenanceStateTone,
  modelStatusTone,
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
