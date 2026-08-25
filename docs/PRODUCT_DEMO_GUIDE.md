# Product Demo Guide

Internal reference for demonstrating LubriSense AI externally. Not shipped in the
product UI. Written after the Final Product Review + Demo Hardening pass — every claim
below was checked against the actual running product and real seeded data, not written
from memory of what the product is supposed to do.

## 30-second product explanation

> Industrial teams already collect lubrication and machine sensor data, but most of it
> sits in a historian, unused, until something breaks. LubriSense AI turns that data into
> a decision-support chain: it fuses physical rules, state estimation, and governed
> machine-learning evidence into a condition assessment, translates that into a
> prioritized recommended action with a clear human-approval boundary, and tracks the
> action through a real incident-and-maintenance workflow to a recorded outcome. Where a
> machine-power sensor exists, it extends that same evidence chain to energy — flagging
> abnormal contextual power demand, assessing whether lubrication is a plausible
> contributor, and, once a maintenance intervention is verified, estimating the CO2e
> impact of the qualified energy recovery. The goal is a better maintenance decision,
> made earlier, with more confidence, with less manual effort — not a bigger dashboard.

## 2-minute product story

**SENSE** — Real (synthetic-demo) telemetry from pressure, flow, vibration, bearing
temperature, and machine-power sensors, organized under a real industrial asset hierarchy
(Organization → Site → Area → Machine → Bearing → Lubrication System).

**TRUST** — Every signal is evaluated for data quality before it's allowed to influence a
decision (Data Quality page): trusted, confidence-reducing, assessment-blocking, or
action-blocking. A blocked or low-confidence signal is never silently treated as if it
were healthy.

**UNDERSTAND** — Physical rules and state estimation (a Kalman-filtered latent condition
estimate — state estimation, not automatically "AI") produce the first layer of evidence;
governed ML evidence (anomaly detection, failure-pattern classification) adds a second,
clearly-labeled layer, gated by model maturity, data quality, and experimental-vs-governed
status.

**PREDICT** — Prognostics/ML evidence contribute a forecast and pattern evidence, but this
does not mean every operational decision is ML-driven — Decision Intelligence synthesizes
all evidence sources, weighted by their own governance, into one recommendation.

**DECIDE** — Decision Intelligence turns fused evidence into a recommended action,
priority, and window, with an explicit confidence and a stated risk-if-deferred — a
synthesis layer, not a single model's raw output.

**ACT / AUTHORIZE** — Action Readiness makes the human-control boundary explicit for every
asset: Monitoring Only, Human Action Required, Assessment Blocked, or Data Limited. There
is no physical actuation anywhere in this platform, and no UI state claims otherwise.

**VERIFY** — Incidents and maintenance cases carry a real workflow (acknowledge →
investigate → plan → complete), ending in a technician-recorded outcome classification
(confirmed / not confirmed / missed / inconclusive) — completion is never treated as
automatic success. Where a machine-power sensor exists, the same discipline extends to
energy: a completed intervention's pre/post residual is compared under a comparability
gate, and only a qualified recovery ever gets an avoided-energy figure or a downstream
carbon estimate.

**LEARN** — Recent Outcomes (organization, site, and machine level) surface what actually
happened — condition resolved, maintenance completed, energy recovery qualified, carbon
estimate produced — as a real, typed feed, not an inferred summary.

## Recommended 5–8 minute demo flow

Route through the real, seeded product — no separate demo-only page exists or should be
built. Reseed the hosted demo shortly before presenting (see the pre-demo checklist) so
every step below reflects a fresh, coherent story rather than hours-stale telemetry.

| # | Page | Point at | Say | Caveat if asked |
|---|------|----------|-----|------|
| 1 | `/performance/organization` (root `/`) | Header, KPI strip, Fleet Reliability State bar | "This is the organization command center — every number here is a real aggregate over the live fleet, not a mock. Reliability comes first: attention and critical-attention counts dominate the top of the page." | The 24-asset fleet is synthetic demonstration data, not a live customer deployment. |
| 2 | Same page, scroll to Priority Attention | The top attention entry (Kiln ID Fan IDF-01, after a fresh reseed) | "This is the platform's own deterministic priority ranking — reliability and safety evidence always outranks an energy signal, never the reverse." | Priority is categorical (Critical/High/Attention/Monitor), never a fabricated numeric score. |
| 3 | `/machines/<IDF-01>` | Current condition band, then Energy & Efficiency section | "The condition assessment says Independent Bearing Condition, driven by rule and state-estimate evidence. Below, the Energy & Efficiency section shows this same asset is drawing more power than expected — and the attribution panel separately says lubrication is a *possible*, not proven, contributor." | No avoided energy or CO2e is shown here — there's no completed intervention yet to verify. |
| 4 | Same page, Machine/Decision/Workflow Intelligence row | Decision Intelligence panel | "The recommended action — inspect the bearing — comes from fused evidence, gated by confidence, with an explicit 'human review required' flag." | ML evidence here is one input among several, not the sole driver — see the ML Intelligence page if asked. |
| 5 | `/action-readiness` (or the readiness badge on the same machine) | The "Human approval required" pill | "This is the actual control boundary in the product today — every action is a human physical-presence step, never an automated command. No physical lubrication control exists anywhere in this platform." | This is a deliberate, explicit boundary, not a current limitation to apologize for. |
| 6 | `/machines/<BE-201>` | Case journey (Verified), then Energy & Efficiency → Energy Outcome panel | "This asset had a real incident, a real maintenance intervention, and a verified outcome. The energy panel shows a qualified recovery — about 1.1 kWh, observed under comparable operating conditions." | Point out the pre-attribution badge reads "No Evidence" — the interface deliberately does not claim lubrication caused this recovery, only that performance improved after the intervention. |
| 7 | Same section, Carbon panel | The CO2e figure | "Because the recovery qualified and a site emission factor is configured, the platform estimates the CO2e impact — an operational estimate, not a certified or audited figure." | The emission factor itself is a labeled demo estimate, not a jurisdiction-validated factor. |
| 8 | *(optional)* `/data-quality` or `/ml` | Machines-affected list, or the ML pipeline diagram | "Data Quality is a product decision gate, not just a sensor dashboard — it explains exactly what's blocked and why. ML Intelligence shows the same discipline: predictions are evidence, gated by maturity, never a standalone maintenance decision." | Skip if time-constrained — steps 1-7 already carry the core story. |
| 9 | Back to `/performance/organization`, Recent Outcomes | The typed outcome feed | "This is the closed loop, end to end — condition identified, decision made, action taken, outcome verified, energy and carbon quantified where qualified." | — |

## Claims and boundaries (what this product does and does not claim)

- **Does** claim: real evidence fusion (rules + state estimation + governed ML), a
  deterministic decision/priority synthesis, a real incident/maintenance workflow with
  recorded outcomes, and — where a power sensor and a qualified outcome exist — an
  observed energy recovery and a downstream operational CO2e estimate.
- **Does not** claim: proven lubrication causality for any energy change (attribution is
  evidence-strength language — No Evidence/Possible/Moderate/Strong — never a percentage
  of the deviation itself), annualized or projected savings, certified/audited carbon
  reduction, autonomous or automatic physical control, field-validated accuracy, or that
  ML alone drives operational decisions.
- Every "verified"/"qualified" label in the UI traces to a real backend field
  (`EnergyOutcomeVerification.energy_outcome_status`, technician
  `feedback_classification`, etc.) — never a frontend-invented status.

## Likely questions and answers

**Why did you build this?**
Lubrication-related failures are a real, common, and often preventable class of
industrial downtime, and most connected-monitoring products stop at "here's a chart" —
this explores what a full decision-and-workflow chain looks like on top of that data,
from physical evidence through to a verified maintenance outcome.

**What problem does it solve?**
The gap between "we have sensor data" and "someone made a better maintenance decision
because of it, and we can show that it happened."

**Why isn't this simply condition monitoring?**
Condition monitoring stops at "here's a chart" or "here's an alert." This adds a decision
layer (recommended action, priority, confidence, risk-if-deferred), a workflow layer
(incident → maintenance → recorded outcome), and — where the sensor exists — an energy/
carbon layer downstream of a *qualified* outcome, not a raw reading.

**Why combine rules, physics, and ML rather than just using ML?**
Rules and state estimation are cheap, explainable, and don't need training data — they
carry the load wherever the physics is well-understood. ML adds value specifically where
patterns are multivariable or not visible from individual thresholds, and its influence is
capped by data quality and model maturity so it never has more authority than the evidence
backing it.

**Why isn't ML currently driving all decisions?**
Because it shouldn't, until it's validated for that. This platform's own governance model
(experimental vs. staging vs. production-lifecycle models, `EXPERIMENTAL_EVIDENCE` role)
keeps unvalidated model output visible as evidence without letting it manufacture a
diagnosis on its own — a deliberate design boundary, not a missing feature.

**Why does data quality matter this much?**
Because a decision is only as trustworthy as the sensor evidence behind it. The platform
gates condition assessment, ML inference, and action readiness on real per-sensor trust
categories, and a blocked or degraded signal is always shown as such, never silently
treated as healthy.

**How do you prevent false actions?**
There is no automated action to prevent — every recommended action requires explicit human
review and execution. The "false action" risk this platform actually manages is a false
*recommendation*, which is why evidence, confidence, and data-quality gating exist before a
recommendation is ever surfaced.

**What does Action Readiness mean?**
A categorical, deterministic statement of where an asset sits between passive monitoring
and a human-executed action today: monitoring only, human action required, or blocked
(by insufficient evidence or missing data) — never a numeric score, never an automation
claim.

**Why no physical closed-loop actuation?**
That would require validated actuator interfaces, safety interlocks, actuation-feedback
confirmation, and a cybersecurity/functional-safety review this reference implementation
was never scoped to include. The architecture is built so that boundary could be extended
later behind an explicit, governed interface — it is not implemented today, and the
product never implies otherwise.

**Why energy intelligence?**
Because lubrication condition and mechanical friction genuinely can show up as elevated
power draw, and a platform already ingesting the right sensor data is well-positioned to
surface that — carefully, without overclaiming causality it can't prove.

**Can you prove lubrication caused the energy difference?**
No — and the product doesn't claim to. It reports an evidence-strength attribution level
(No Evidence/Possible/Moderate/Strong) with explicit supporting *and* contradicting
evidence, and a completed intervention's outcome is described as "energy performance
improved under comparable operation," not "lubrication caused a recovery," unless the
historical pre-intervention attribution genuinely supported that stronger claim.

**What does the CO2e number mean?**
An operational estimate: qualified observed avoided energy (kWh) × a configured site
emission factor (kg CO2e/kWh), shown with its method and provenance. It is not a
certified, audited, or jurisdiction-validated carbon accounting figure.

**Why synthetic data?**
To demonstrate the architecture's behavior — including honest edge cases like insufficient
evidence, data-quality blocking, and inconclusive outcomes — without needing a live
customer deployment first. Every synthetic scenario is labeled as such (see "Field-readiness
boundary" below).

**What would be required for field deployment?**
See the dedicated section below — real telemetry, baseline commissioning, model and sensor
validation, a cybersecurity review, machine-specific safety review, and outcome validation,
among others.

**How would this integrate with an enterprise EAM/APM/CMMS environment?**
The maintenance workflow already models a CMMS draft/adapter boundary conceptually (a
governed, replaceable integration point rather than a hard dependency on one vendor) —
production integration would mean implementing that adapter against a specific target
system's API and auth model, which is a real but well-scoped integration project, not an
architecture change.

**What would you validate first with customers?**
Whether the condition/decision layer's recommendations match what an experienced
technician would actually flag, using the customer's own real telemetry and real failure
history — before extending validation to the energy/carbon layer, which has a smaller,
newer evidence base.

**How would you commercialize it?**
As a connected-reliability capability layered onto an industrial customer's existing
lubrication/condition-monitoring hardware investment, priced around the maintenance
decisions and downtime it helps avoid — the energy/carbon layer as a natural expansion
for customers who already have machine-power instrumentation, not a separate product.

## Field-readiness boundary

Present as: **a working industrial AI reference product / architecture demonstration.**
Never as: a field-validated production solution for real machinery.

Field deployment would require, at minimum:
- Real customer telemetry (replacing the synthetic simulator)
- Baseline/context commissioning against real operating history
- Model validation against real, labeled failure history
- Sensor and hardware validation (installation, calibration, protocol integration)
- A cybersecurity review of the full data path
- Machine-specific safety/interlock review before any actuation boundary is ever extended
- Integration with the customer's actual maintenance system (CMMS/EAM/APM)
- Operational acceptance testing with real technicians
- Governance sign-off (who owns model retraining, threshold changes, emission-factor
  updates)
- Outcome validation — confirming the energy/carbon evidence chain holds up against real,
  independently-metered results, not just synthetic scenarios

## Pre-demo checklist

1. Confirm the deployment is on the latest commit (`git log -1`).
2. Reseed the hosted demo (`uv run python scripts/seed_hosted_demo.py`) — not hours
   before; telemetry data-quality staleness detection is real and will degrade the
   flagship IDF-01/BE-201 story if the seed is too old. A few minutes to roughly half a
   day ahead is a safe window in the current architecture; verify by loading Organization
   and confirming IDF-01 and BE-201 show their expected story states (below) rather than
   `DATA_LIMITED`.
3. Hit `/health` and `/ready` on the backend — confirm both are healthy before opening
   the browser.
4. Open `/performance/organization` (or root `/`) — confirm it loads, shows a non-zero
   asset count, and the KPI strip renders real numbers (not a loading spinner stuck open).
5. Open the IDF-01 machine page — confirm it shows an elevated-energy / attribution
   story (not `DATA_LIMITED`/`AMBIGUOUS_CONDITION`, which means the seed is stale or too
   fresh — see step 2).
6. Open the BE-201 machine page — confirm the Energy & Efficiency section shows
   `QUALIFIED_RECOVERY` and a real CO2e figure (not `INSUFFICIENT_DATA`).
7. Open `/data-quality` — confirm it renders a real trust summary, not an empty state.
8. Open `/system` — confirm all systems read ready.
9. Run one incognito/private-window smoke test of the same root URL, to catch anything
   that depended on stale browser-local state (role selection, cached queries).

## Known, disclosed limitations for a live demo

- Telemetry/condition state is time-sensitive relative to reseed timing (see checklist
  step 2) — this is real, honest staleness/settling behavior, not a bug, but it means
  "reseed and immediately screen-share with no verification" is not safe.
- Synthetic scenarios use fictional site/company names and demo-scale numbers throughout
  (Ridgeline/Harborview/Millbrook/Eastgate/Dornbach) — confirmed zero real-company
  references anywhere in the repository (see hygiene scan results in the review report).
