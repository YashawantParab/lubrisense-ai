"""LubriSense AI — physics-informed industrial simulator.

Produces DEMO / SYNTHETIC ENGINEERING DATA for a centralized lubrication system and the
machine it protects. See docs/SIMULATOR.md and docs/SYNTHETIC_DATA_MODEL.md for the
physical abstraction, equations, and the ground-truth/observed-telemetry separation this
package enforces.

Nothing in this package should be presented as a validated industrial specification.
"""

from __future__ import annotations

__version__ = "0.1.0"

#: Bumped when `simulator/scenarios/*` (progression/lifecycle/effects semantics) changes in
#: a way that could change existing scenario output — independent of `__version__`, which
#: tracks the simulator as a whole (Phase 4 brief §21, docs/SCENARIO_ENGINE.md).
__scenario_engine_version__ = "1.0.0"
