"""Render the checked-in Phase 10 feature catalog from the runtime registry."""

from __future__ import annotations

from app.features.definitions import FEATURE_DEFINITIONS


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_feature_catalog() -> str:
    lines = [
        "# Feature Catalog — Phase 10",
        "",
        (
            "This catalog is generated from `app.features.definitions.FEATURE_DEFINITIONS`. "
            "Regenerate it with `python -m app.features.definitions.render_catalog`."
        ),
        "",
        (
            "| Name | Version | Group | Type | Unit | Window | Source | Context | "
            "Quality requirement | Description | Feature sets |"
        ),
        "|---|---|---|---|---|---:|---|---|---|---|---|",
    ]
    for definition in FEATURE_DEFINITIONS:
        window = (
            "current/as-of"
            if definition.window_seconds is None
            else f"{definition.window_seconds}s"
        )
        values = (
            f"`{definition.name}`",
            definition.version,
            definition.group.value,
            definition.data_type.value,
            definition.unit,
            window,
            ", ".join(definition.source_measurements) or "metadata",
            ", ".join(definition.context_requirements) or "none",
            definition.quality_requirement,
            definition.description,
            ", ".join(definition.feature_sets),
        )
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    lines.extend(
        [
            "",
            "All definitions use machine entity scope, explicit semantic versions, and preserve "
            "unavailable values as missing rather than filling them with zero.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_feature_catalog(), end="")
