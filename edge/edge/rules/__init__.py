"""Local, deterministic edge rules — NOT the Phase 9 rules engine (Phase 5 brief §16-§17;
ADR-049)."""

from edge.rules.engine import LocalRuleEngine

__all__ = ["LocalRuleEngine"]
