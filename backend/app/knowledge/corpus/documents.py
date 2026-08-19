"""The synthetic demo knowledge corpus (Phase 18 brief §18.4) — ~15 small, high-quality,
clearly-generic documents, never hundreds of junk pages. Every document is synthetic
reference material for this platform's own demo lubrication-system model
(docs/DOMAIN_MODEL.md), not a real vendor manual — see CLAUDE.md "Synthetic ranges must
be explicitly labelled as demo assumptions" applied here to procedures rather than
numeric ranges.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CorpusEntry:
    document_key: str
    title: str
    document_type: str
    version: str
    source_name: str
    content: str


_SAFETY_PREAMBLE = (
    "This is a generic demo reference document for a synthetic reference platform. It "
    "is not a substitute for site-specific lockout/tagout procedures, local safety "
    "regulations, or manufacturer documentation for real equipment."
)

CORPUS: list[CorpusEntry] = [
    CorpusEntry(
        document_key="lubrication-path-inspection",
        title="Lubrication Path Inspection Procedure",
        document_type="SERVICE_PROCEDURE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content=f"""# Lubrication Path Inspection Procedure

## Purpose

Generic inspection steps for a suspected lubrication-delivery problem (developing
restriction, delivery blockage, or possible leakage evidence from the platform's
condition intelligence). Applies to a centralized lubrication system: reservoir, pump,
controller, main line, distributor, circuit, lubrication point.

## Safety

{_SAFETY_PREAMBLE} Do not open a pressurized line. Follow site lockout/tagout procedure
before any physical contact with moving equipment.

## Inspection steps

Visually inspect accessible lubrication lines for kinks, crushing, or visible damage
along the delivery path. Verify reservoir lubricant level and availability. Inspect for
obvious leakage at fittings, connections, and the distributor housing. Verify
delivery-path condition where it is safe to access, without disassembling pressurized
components. Record all observations, including a clean result — a normal finding is
still useful evidence.

## When to escalate

If the delivery path appears fully blocked, or if pressure/flow evidence suggests a
confirmed blockage rather than a developing restriction, escalate to a distributor-level
inspection (see the distributor restriction/blockage inspection procedure) rather than
continuing routine inspection alone.
""",
    ),
    CorpusEntry(
        document_key="distributor-restriction-inspection",
        title="Distributor Restriction and Blockage Inspection",
        document_type="TROUBLESHOOTING_GUIDE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content=f"""# Distributor Restriction and Blockage Inspection

## Purpose

Focused troubleshooting for a distributor suspected of a developing restriction or a
confirmed blockage pattern — evidence typically seen as elevated pressure alongside a
cross-signal restriction pattern in the platform's rule findings.

## Safety

{_SAFETY_PREAMBLE}

## Inspection steps

Visually inspect the distributor housing and every outlet for visible damage. Check
each outlet for a blocked or partially blocked opening — a partially blocked outlet is a
common, generic finding consistent with a developing restriction pattern. Verify
piston/valve movement where it can be safely observed without disassembly. Inspect
connected downstream lines for restriction, kinking, or damage. Record all observations,
even if no issue is found — a confirmed-clear distributor is still useful evidence
supporting a different root cause.

## Distinguishing restriction from blockage

A developing restriction pattern is evidence consistent with a gradually worsening
partial obstruction. A confirmed blockage pattern (critical severity) indicates delivery
has very likely stopped at that point in the circuit. Treat a confirmed blockage as
higher urgency than a developing restriction.
""",
    ),
    CorpusEntry(
        document_key="leakage-inspection",
        title="Lubricant Leakage Inspection",
        document_type="TROUBLESHOOTING_GUIDE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content=f"""# Lubricant Leakage Inspection

## Purpose

Inspection guidance when evidence is consistent with possible leakage — typically an
abnormal reservoir depletion rate relative to its expected baseline.

## Safety

{_SAFETY_PREAMBLE}

## Inspection steps

Inspect all accessible fittings, seals, and connections along the delivery path for
visible lubricant accumulation or seepage. Check the reservoir seal and fill point for
leakage. Inspect the distributor housing and outlet seals. Record the location, severity
(minor seepage vs. active dripping/flow), and any housekeeping/environmental concern.

## Risk if deferred

Continued lubricant loss may reduce delivery effectiveness at downstream lubrication
points and increases housekeeping/environmental concern the longer it continues
unaddressed.
""",
    ),
    CorpusEntry(
        document_key="pump-performance-inspection",
        title="Pump Performance Inspection",
        document_type="SERVICE_PROCEDURE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content=f"""# Pump Performance Inspection

## Purpose

Inspection steps when evidence indicates pump-performance degradation — for example,
pump current or runtime deviating from its expected baseline.

## Safety

{_SAFETY_PREAMBLE}

## Inspection steps

Inspect pump operating status and any local indicators (run lights, fault indicators).
Record observed pump condition — unusual noise, vibration, or elevated temperature where
it can be safely assessed. Verify pump current and runtime against applicable local
indicators. Record all observations, even a normal finding.

## Risk if deferred

Continued pump degradation may further reduce delivery pressure or flow and increases
the risk of unplanned pump failure the longer it goes unaddressed.
""",
    ),
    CorpusEntry(
        document_key="reservoir-low-level-handling",
        title="Reservoir Low-Level and Depletion Handling",
        document_type="OPERATING_GUIDE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content=f"""# Reservoir Low-Level and Depletion Handling

## Purpose

Generic operating guidance for low or abnormally depleting reservoir lubricant level.

## Safety

{_SAFETY_PREAMBLE}

## Steps

Confirm the reservoir level against its expected operating range. Check for signs of
abnormal depletion or contamination. Verify the refill mechanism and access point are
unobstructed before refilling. Record the observed level and any refill performed.

## Risk if deferred

Continued depletion may lead to lubrication starvation at downstream points if the
reservoir is not replenished in time.
""",
    ),
    CorpusEntry(
        document_key="bearing-condition-inspection",
        title="Bearing Condition Inspection",
        document_type="SERVICE_PROCEDURE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content=f"""# Bearing Condition Inspection

## Purpose

Inspection guidance when state-estimation evidence indicates bearing-condition
degradation, independent of the lubrication-delivery system.

## Safety

{_SAFETY_PREAMBLE}

## Inspection steps

Inspect accessible bearing condition for visible wear or damage. Record temperature and
vibration observations where instrumentation is available. Check for unusual noise
during normal operation, if it is safe to observe. Record all observations, even a
normal finding.

## Independence from lubrication delivery

Bearing-condition degradation evidence is treated as independent of lubrication-delivery
evidence unless a specific lubrication-related contribution is separately confirmed — do
not assume a lubrication cause without supporting evidence.
""",
    ),
    CorpusEntry(
        document_key="sensor-verification",
        title="Sensor Verification Procedure",
        document_type="TROUBLESHOOTING_GUIDE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content=f"""# Sensor Verification Procedure

## Purpose

Verification steps when a sensor or data-quality limitation is preventing a reliable
condition assessment.

## Safety

{_SAFETY_PREAMBLE}

## Steps

Verify the sensor is physically connected and powered. Check for visible sensor damage
or miswiring. Confirm recent readings are actually reaching the platform (not stale or
missing). Record all observations, even if no issue is found.

## Why this matters

A data-quality limitation is a statement about instrumentation trust, not about machine
condition — the underlying condition genuinely cannot be assessed until data quality is
verified and recovers.
""",
    ),
    CorpusEntry(
        document_key="data-quality-troubleshooting",
        title="Communication and Data-Quality Troubleshooting",
        document_type="TROUBLESHOOTING_GUIDE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content=f"""# Communication and Data-Quality Troubleshooting

## Purpose

Guidance for communication loss, sensor dropout, or sensor drift affecting data quality.

## Safety

{_SAFETY_PREAMBLE}

## Steps

Check gateway connectivity and communication status. Verify sensor firmware/reporting
interval is behaving as expected. For suspected drift, compare current readings against
a recent known-good baseline where available. Record findings and whether communication
was restored.

## Escalation

If communication loss or drift persists after basic verification, treat the affected
sensors as untrusted for condition assessment until resolved — see the sensor
verification procedure.
""",
    ),
    CorpusEntry(
        document_key="maintenance-safety-boundary",
        title="Generic Maintenance Safety Boundary",
        document_type="SAFETY_NOTE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content=f"""# Generic Maintenance Safety Boundary

## Scope

{_SAFETY_PREAMBLE}

## Boundary

No inspection or maintenance action described in this reference library authorizes
bypassing lockout/tagout, disabling a safety interlock, or operating equipment outside
its normal, authorized operating envelope. All physical maintenance actions require
human execution and human judgment on-site — no automated system in this platform issues
a physical control command.

## Escalation

If an inspection reveals a condition outside normal safety boundaries, stop the
inspection and escalate through the site's standard safety escalation path rather than
continuing.
""",
    ),
    CorpusEntry(
        document_key="fault-code-reference",
        title="Lubrication System Fault Pattern Reference",
        document_type="FAULT_CODE_REFERENCE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content="""# Lubrication System Fault Pattern Reference

## Cross-signal restriction pattern

A cross-signal restriction pattern means multiple independent signals (for example
pressure and flow) jointly indicate a developing restriction, which is stronger evidence
than a single-signal deviation alone.

## Cycle completion failure

A cycle completion failure means a lubrication cycle did not confirm completion within
its expected window — evidence consistent with a delivery-path problem, not on its own
proof of a specific cause.

## Reservoir depletion abnormal

Reservoir depletion abnormal means the reservoir is depleting faster than its expected
baseline rate — evidence consistent with possible leakage, not automatically proof of a
leak without physical confirmation.

## Pump current above baseline

Pump current above baseline means observed pump current has deviated materially from
its expected contextual baseline — evidence consistent with pump-performance
degradation.
""",
    ),
    CorpusEntry(
        document_key="lubrication-system-component-reference",
        title="Lubrication System Component Reference",
        document_type="COMPONENT_REFERENCE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content="""# Lubrication System Component Reference

## Reservoir

Holds the lubricant supply for the system. Refilled periodically; depletion rate is
tracked against an expected baseline.

## Pump

Draws lubricant from the reservoir and delivers it under pressure into the main
lubrication line. Pump current and runtime are tracked against expected baselines.

## Controller

Manages lubrication cycle timing and monitors cycle completion.

## Distributor

Divides the main line's flow into individual circuits, each feeding one or more
lubrication points. A common location for developing restrictions or blockages.

## Circuit and lubrication point

A circuit carries lubricant from the distributor to one or more lubrication points, each
typically feeding a bearing.
""",
    ),
    CorpusEntry(
        document_key="service-case-distributor-blockage",
        title="Synthetic Service Case: Distributor Outlet Partially Blocked",
        document_type="SERVICE_CASE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content="""# Synthetic Service Case: Distributor Outlet Partially Blocked

## Summary

A developing restriction pattern was flagged for a conveyor's lubrication-delivery
system, based on a cross-signal pressure/flow deviation. This is a synthetic demo case,
not a real service record.

## What was found

On inspection, the technician found a partially blocked distributor outlet. The finding
was recorded as PARTIALLY_CONFIRMED.

## What was done

The technician cleaned the affected distributor outlet. The action was recorded as
CLEANED.

## Outcome

The case was closed with feedback classification TRUE_POSITIVE. This is one synthetic
example, not a guarantee that every developing restriction pattern has the same root
cause.
""",
    ),
    CorpusEntry(
        document_key="service-case-reservoir-leak",
        title="Synthetic Service Case: Reservoir Fitting Leak",
        document_type="SERVICE_CASE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content="""# Synthetic Service Case: Reservoir Fitting Leak

## Summary

A possible-leakage pattern was flagged based on abnormal reservoir depletion. This is a
synthetic demo case, not a real service record.

## What was found

On inspection, the technician found minor seepage at a reservoir fitting. The finding
was recorded as CONFIRMED.

## What was done

The technician tightened and resealed the fitting. The action was recorded as
ADJUSTMENT_RECOMMENDED, followed by a refill action recorded as REFILLED.

## Outcome

The case was closed with feedback classification TRUE_POSITIVE.
""",
    ),
    CorpusEntry(
        document_key="service-case-pump-degradation",
        title="Synthetic Service Case: Pump Current Deviation, No Fault Found",
        document_type="SERVICE_CASE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content="""# Synthetic Service Case: Pump Current Deviation, No Fault Found

## Summary

A pump-performance-degradation pattern was flagged based on pump current deviating from
baseline. This is a synthetic demo case, not a real service record.

## What was found

On inspection, the technician found no visible pump issue and normal operating sound.
The finding was recorded as NOT_CONFIRMED.

## What was done

No physical action was required. The action was recorded as NO_ACTION_REQUIRED.

## Outcome

The case was closed with feedback classification FALSE_POSITIVE. The original evidence
and assessment were preserved, not erased, even though no fault was confirmed.
""",
    ),
    CorpusEntry(
        document_key="service-case-sensor-fault",
        title="Synthetic Service Case: Loose Sensor Connector",
        document_type="SERVICE_CASE",
        version="1.0.0",
        source_name="LubriSense Demo Reference Library",
        content="""# Synthetic Service Case: Loose Sensor Connector

## Summary

A sensor/data-quality limitation was flagged after a pressure sensor's readings became
unusable. This is a synthetic demo case, not a real service record.

## What was found

On inspection, the technician found a loose sensor connector. The finding was recorded
as CONFIRMED.

## What was done

The technician reseated the connector. The action was recorded as INSPECTED.

## Outcome

The case was closed with feedback classification TRUE_POSITIVE, and data quality
recovered on the next reporting cycle.
""",
    ),
]
