"""Reduced-order physical models: reservoir, pump, circuit, bearing, lubrication cycle, and
machine operating profile. Every equation here is intentionally simple, explainable, and
configurable — see docs/SIMULATOR.md §5-§10 for the equations and their rationale. None of
this represents proprietary real-world engineering models (Phase 3 brief §9)."""

from __future__ import annotations
